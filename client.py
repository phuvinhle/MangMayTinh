import sys
import os
from pathlib import Path

# --- DLL FIX FOR WINDOWS ---
if sys.platform == "win32":
    executable_path = Path(sys.executable).parent
    possible_bin_paths = [
        executable_path / "Lib" / "site-packages" / "PyQt5" / "Qt5" / "bin",
        executable_path.parent / "Lib" / "site-packages" / "PyQt5" / "Qt5" / "bin",
        executable_path / "site-packages" / "PyQt5" / "Qt5" / "bin"
    ]
    for p in possible_bin_paths:
        if p.exists():
            os.add_dll_directory(str(p))
            os.environ["PATH"] = str(p) + os.pathsep + os.environ["PATH"]
            break

# Linux Fix
if sys.platform == "linux":
    os.environ["QT_QPA_PLATFORM"] = "xcb"

import socket
import ssl
import struct
import cv2
import json
import time
import logging
import numpy as np
import threading
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

# --- LOGGING CONFIG ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class NumericItem(QTableWidgetItem):
    """Custom table item for proper numerical sorting using raw data."""
    def __init__(self, text, sort_val):
        super().__init__(text)
        self.sort_val = sort_val
    def __lt__(self, other):
        if isinstance(other, NumericItem): return self.sort_val < other.sort_val
        return super().__lt__(other)

def recv_all(sock, n):
    data = b""
    while len(data) < n:
        try:
            packet = sock.recv(n - len(data))
            if not packet: return None
            data += packet
        except: return None
    return data

class RemoteBase(QMainWindow):
    _is_disconnecting = False

    def __init__(self, ip, pwd, controller=None):
        super().__init__()
        self.ip, self.pwd, self.controller = ip, pwd, controller
        self.target_res = (1280, 720)
        self.cmd_s = None
        if not self.init_cmd(): raise ConnectionError(f"Connection to {ip} failed")

    @pyqtSlot()
    def handle_disconnect(self):
        if not RemoteBase._is_disconnecting:
            RemoteBase._is_disconnecting = True
            QMessageBox.warning(None, "Connection Lost", f"Lost connection to server {self.ip}. Closing session.")
            if self.controller: self.controller.close_all_session()
            else: self.close()
            QTimer.singleShot(2000, lambda: setattr(RemoteBase, '_is_disconnecting', False))

    def init_cmd(self):
        try:
            raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            raw.settimeout(10)
            raw.connect((self.ip, 9999))
            ctx = ssl._create_unverified_context()
            ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
            self.cmd_s = ctx.wrap_socket(raw, server_hostname=self.ip)
            self.cmd_s.sendall(self.pwd.encode())
            h = recv_all(self.cmd_s, 4)
            if not h: return False
            sz = struct.unpack("!I", h)[0]
            data = json.loads(recv_all(self.cmd_s, sz).decode())
            if data.get('status') == "OK":
                self.target_res = (data['w'], data['h']); return True
            return False
        except socket.timeout:
            QMessageBox.critical(None, "Timeout", "Connection timed out. Please check server status."); return False
        except Exception as e:
            logging.error(f"Init Error: {e}"); return False

    def send_safe_cmd(self, data):
        try:
            p = json.dumps(data).encode('utf-8')
            self.cmd_s.sendall(struct.pack("!I", len(p)) + p); return True
        except:
            self.handle_disconnect(); return False

    def recv_json(self):
        try:
            h = recv_all(self.cmd_s, 4)
            if not h: return None
            sz = struct.unpack("!I", h)[0]
            data = recv_all(self.cmd_s, sz)
            return json.loads(data.decode()) if data else None
        except socket.timeout:
            QMessageBox.warning(self, "Timeout", "Server response timed out."); return None
        except:
            self.handle_disconnect(); return None

class LiveControl(RemoteBase):
    def __init__(self, ip, pwd, controller=None):
        super().__init__(ip, pwd, controller)
        self.setWindowTitle(f"Live Control - {ip}"); self.resize(1000, 750)
        self.view = QLabel("Loading Stream..."); self.view.setAlignment(Qt.AlignCenter)
        self.view.setStyleSheet("background: black;"); self.setCentralWidget(self.view)
        self.send_safe_cmd({"type": "STREAM_CTRL", "active": True, "mode": "SCREEN"})
        self.active = True
        threading.Thread(target=self.stream_loop, daemon=True).start()

    def stream_loop(self):
        try:
            raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            raw.connect((self.ip, 9998))
            ctx = ssl._create_unverified_context()
            ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
            s = ctx.wrap_socket(raw, server_hostname=self.ip)
            while self.active:
                h = recv_all(s, 4)
                if not h: break
                sz = struct.unpack("!I", h)[0]
                b = recv_all(s, sz)
                if not b: break
                img = cv2.imdecode(np.frombuffer(b, np.uint8), 1)
                if img is not None:
                    qi = QImage(img.data, img.shape[1], img.shape[0], img.shape[1]*3, QImage.Format_RGB888).rgbSwapped()
                    pix = QPixmap.fromImage(qi).scaled(self.view.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    QMetaObject.invokeMethod(self.view, "setPixmap", Qt.QueuedConnection, Q_ARG(QPixmap, pix))
            s.close()
        except: pass
        finally:
            if self.active: QMetaObject.invokeMethod(self, "handle_disconnect", Qt.QueuedConnection)

    def mousePressEvent(self, ev):
        p = self.view.mapFromParent(ev.pos())
        if self.view.rect().contains(p) and self.view.pixmap():
            pm = self.view.pixmap()
            ox, oy = (self.view.width()-pm.width())/2, (self.view.height()-pm.height())/2
            rx, ry = p.x()-ox, p.y()-oy
            if 0 <= rx <= pm.width() and 0 <= ry <= pm.height():
                fx, fy = int(rx * self.target_res[0]/pm.width()), int(ry * self.target_res[1]/pm.height())
                self.send_safe_cmd({"type": "MOUSE", "x": fx, "y": fy, "btn": "right" if ev.button()==Qt.RightButton else "left"})

    def closeEvent(self, ev):
        self.active = False; self.send_safe_cmd({"type": "STREAM_CTRL", "active": False}); super().closeEvent(ev)

class ProcessManager(RemoteBase):
    def __init__(self, ip, pwd, controller=None):
        super().__init__(ip, pwd, controller)
        self.setWindowTitle(f"Processes - {ip}"); self.resize(700, 500)
        wid = QWidget(); self.setCentralWidget(wid); layout = QVBoxLayout(wid)
        
        # Search row with REFRESH button
        search_layout = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText("Search process name (Local Filter)...")
        self.search.textChanged.connect(self.local_filter)
        
        self.btn_refresh = QPushButton("REFRESH")
        self.btn_refresh.setFixedWidth(100); self.btn_refresh.clicked.connect(self.refresh_all)
        
        search_layout.addWidget(self.search); search_layout.addWidget(self.btn_refresh)
        layout.addLayout(search_layout)

        self.table = QTableWidget(0, 4); self.table.setHorizontalHeaderLabels(["PID", "Name", "CPU", "MEM"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows); self.table.setSortingEnabled(True)
        layout.addWidget(self.table)

        btns = QHBoxLayout()
        self.auto_cb = QCheckBox("Auto-sync (5s)"); self.auto_cb.setChecked(True)
        b2 = QPushButton("KILL PROCESS"); b2.clicked.connect(self.kill)
        b2.setStyleSheet("background-color: #f44336; color: white; font-weight: bold;")
        btns.addWidget(self.auto_cb); btns.addStretch(); btns.addWidget(b2)
        layout.addLayout(btns)
        
        self.timer = QTimer(self); self.timer.timeout.connect(self.auto_load)
        self.timer.start(5000)
        self.full_data = [] # Cache for local filtering
        self.load()

    def refresh_all(self):
        self.search.clear()
        self.load()

    def auto_load(self):
        if self.auto_cb.isChecked() and self.isVisible(): self.load()

    def local_filter(self):
        """Filter data instantly without network request."""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        txt = self.search.text().lower()
        for p in self.full_data:
            if not txt or txt in p['name'].lower():
                r = self.table.rowCount(); self.table.insertRow(r)
                self.table.setItem(r, 0, NumericItem(str(p['pid']), int(p['pid'])))
                self.table.setItem(r, 1, QTableWidgetItem(p['name']))
                self.table.setItem(r, 2, NumericItem(f"{p['cpu_percent']}%", float(p['cpu_percent'])))
                self.table.setItem(r, 3, NumericItem(f"{round(p['memory_percent'],1)}%", float(p['memory_percent'])))
        self.table.setSortingEnabled(True)

    def load(self):
        """Fetch fresh data from server."""
        selected_pid = None; curr = self.table.currentRow()
        if curr >= 0: selected_pid = self.table.item(curr, 0).text()
        scroll_pos = self.table.verticalScrollBar().value()
        
        self.send_safe_cmd({"type": "LIST_PROCS"})
        data = self.recv_json()
        if data:
            self.full_data = data
            self.local_filter() # Render with current search text
            
            if selected_pid:
                for i in range(self.table.rowCount()):
                    if self.table.item(i, 0).text() == selected_pid: self.table.setCurrentCell(i, 0); break
            self.table.verticalScrollBar().setValue(scroll_pos)

    def kill(self):
        row = self.table.currentRow()
        if row >= 0:
            name, pid = self.table.item(row, 1).text(), int(self.table.item(row, 0).text())
            if QMessageBox.question(self, "Confirm", f"Kill process {name} (PID: {pid})?") == QMessageBox.Yes:
                self.send_safe_cmd({"type": "KILL_PROC", "pid": pid}); time.sleep(0.5); self.load()

    def closeEvent(self, ev): self.timer.stop(); super().closeEvent(ev)

    def kill(self):
        row = self.table.currentRow()
        if row >= 0:
            name, pid = self.table.item(row, 1).text(), int(self.table.item(row, 0).text())
            if QMessageBox.question(self, "Confirm", f"Kill process {name} (PID: {pid})?") == QMessageBox.Yes:
                self.send_safe_cmd({"type": "KILL_PROC", "pid": pid}); time.sleep(0.5); self.load()

    def closeEvent(self, ev): self.timer.stop(); super().closeEvent(ev)

class FileExplorer(RemoteBase):
    def __init__(self, ip, pwd, controller=None):
        super().__init__(ip, pwd, controller)
        self.setWindowTitle(f"Files - {ip}"); self.resize(800, 600)
        wid = QWidget(); self.setCentralWidget(wid); layout = QVBoxLayout(wid)
        self.path = QLineEdit("/"); layout.addWidget(self.path)
        self.table = QTableWidget(0, 3); self.table.setHorizontalHeaderLabels(["Name", "Type", "Size"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.itemDoubleClicked.connect(self.dive); layout.addWidget(self.table)
        btn = QPushButton("DOWNLOAD"); btn.clicked.connect(self.download); layout.addWidget(btn); self.load()

    def load(self):
        self.send_safe_cmd({"type": "LIST_FILES", "path": self.path.text()})
        data = self.recv_json()
        if data:
            self.table.setRowCount(0); r = self.table.rowCount(); self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem("..")); self.table.setItem(r, 1, QTableWidgetItem("Folder"))
            for f in data:
                r = self.table.rowCount(); self.table.insertRow(r)
                self.table.setItem(r, 0, QTableWidgetItem(f['name'])); self.table.setItem(r, 1, QTableWidgetItem("Folder" if f['is_dir'] else "File")); self.table.setItem(r, 2, QTableWidgetItem(str(f['size'])))

    def dive(self, item):
        name = self.table.item(item.row(), 0).text()
        if name == "..": self.path.setText(str(Path(self.path.text()).parent))
        else: self.path.setText(str(Path(self.path.text()) / name))
        self.load()

    def download(self):
        row = self.table.currentRow()
        if row < 0: return
        name = self.table.item(row, 0).text()
        full_path = str(Path(self.path.text())/name)
        if self.send_safe_cmd({"type": "DOWNLOAD", "path": full_path}):
            h = recv_all(self.cmd_s, 8)
            if not h: return
            sz = struct.unpack("!Q", h)[0]
            if sz > 0:
                lp, _ = QFileDialog.getSaveFileName(self, "Save File", name if "." in name else name+".zip")
                if lp:
                    progress = QProgressDialog(f"Downloading {name}...", "Cancel", 0, 100, self)
                    progress.setWindowModality(Qt.WindowModal); progress.show()
                    old_timeout = self.cmd_s.gettimeout(); self.cmd_s.settimeout(0.1)
                    try:
                        with open(lp, "wb") as f:
                            rem = sz
                            while rem > 0:
                                if progress.wasCanceled(): break
                                try:
                                    chunk = self.cmd_s.recv(min(rem, 65536))
                                    if not chunk: break
                                    f.write(chunk); rem -= len(chunk); progress.setValue(int((sz - rem) * 100 / sz))
                                except socket.timeout: pass
                                QApplication.processEvents()
                        if not progress.wasCanceled(): QMessageBox.information(self, "Done", "Download Completed")
                    finally: self.cmd_s.settimeout(old_timeout); progress.close()
            else: QMessageBox.warning(self, "Error", "File not found or empty.")

class SystemApps(RemoteBase):
    def __init__(self, ip, pwd, controller=None):
        super().__init__(ip, pwd, controller)
        self.setWindowTitle(f"System Apps - {ip}"); self.resize(600, 500)
        wid = QWidget(); self.setCentralWidget(wid); layout = QVBoxLayout(wid)
        
        # Search row with REFRESH button (ProcessManager Style)
        search_layout = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText("Enter app name to filter...")
        self.search.textChanged.connect(self.update_table) # Local filter as you type

        self.btn_refresh = QPushButton("REFRESH")
        self.btn_refresh.setFixedWidth(70); self.btn_refresh.clicked.connect(self.refresh_all)

        search_layout.addWidget(self.search); search_layout.addWidget(self.btn_refresh)
        layout.addLayout(search_layout)
        self.table = QTableWidget(0, 2); self.table.setHorizontalHeaderLabels(["Name", "Type"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows); self.table.setSortingEnabled(True)
        layout.addWidget(self.table)

        btns = QHBoxLayout()
        self.btn_start = QPushButton("START APPLICATION")
        self.btn_start.setFixedHeight(40); self.btn_start.clicked.connect(self.start_app)
        self.btn_start.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        btns.addStretch(); btns.addWidget(self.btn_start)
        layout.addLayout(btns)
        
        self.full_data = []
        self.load()

    def refresh_all(self):
        self.search.clear()
        self.load()

    def load(self):
        self.send_safe_cmd({"type": "LIST_APPS"})
        data = self.recv_json()
        if data:
            self.full_data = data
            self.update_table()

    def update_table(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        search_txt = self.search.text().lower()
        for app in self.full_data:
            if not search_txt or search_txt in app['name'].lower():
                r = self.table.rowCount(); self.table.insertRow(r)
                self.table.setItem(r, 0, QTableWidgetItem(app['name']))
                self.table.setItem(r, 1, QTableWidgetItem(app.get('type', 'App')))
                self.table.item(r, 0).setData(Qt.UserRole, app['exec'])
        self.table.setSortingEnabled(True)

    def start_app(self):
        row = self.table.currentRow()
        if row >= 0:
            name = self.table.item(row, 0).text()
            exe = self.table.item(row, 0).data(Qt.UserRole)
            self.send_safe_cmd({"type": "START_APP", "exec": exe})
            QMessageBox.information(self, "Info", f"Request to start {name} sent.")

class ActivityLogs(RemoteBase):
    def __init__(self, ip, pwd, controller=None):
        super().__init__(ip, pwd, controller)
        self.setWindowTitle(f"Activity Logs - {ip}"); self.resize(500, 400)
        wid = QWidget(); self.setCentralWidget(wid); layout = QVBoxLayout(wid)
        self.logs_area = QTextEdit(); self.logs_area.setReadOnly(True); layout.addWidget(self.logs_area)
        btns = QHBoxLayout(); b1 = QPushButton("REFRESH"); b1.clicked.connect(self.load); b2 = QPushButton("SAVE AS TXT")
        b2.clicked.connect(self.save_logs); btns.addWidget(b1); btns.addWidget(b2); layout.addLayout(btns); self.load()

    def load(self):
        self.send_safe_cmd({"type": "GET_LOGS"})
        h = recv_all(self.cmd_s, 4)
        if h:
            sz = struct.unpack("!I", h)[0]; data = recv_all(self.cmd_s, sz).decode('utf-8')
            if data: self.logs_area.append(data)

    def save_logs(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Logs", "activity_logs.txt", "*.txt")
        if path:
            with open(path, "w") as f: f.write(self.logs_area.toPlainText())
            QMessageBox.information(self, "Done", "Logs saved successfully.")

class MediaManager(RemoteBase):
    def __init__(self, ip, pwd, controller=None):
        super().__init__(ip, pwd, controller)
        self.setWindowTitle(f"Media Manager - {ip}"); self.setFixedSize(300, 250)
        wid = QWidget(); self.setCentralWidget(wid); layout = QVBoxLayout(wid)
        b1 = QPushButton("CAPTURE SCREEN"); b1.clicked.connect(lambda: self.capture("SCREEN"))
        b2 = QPushButton("CAPTURE WEBCAM"); b2.clicked.connect(lambda: self.capture("WEBCAM"))
        self.rec_btn = QPushButton("START RECORDING"); self.rec_btn.clicked.connect(self.toggle_record)
        self.is_recording = False
        for b in [b1, b2, self.rec_btn]: b.setFixedHeight(40); layout.addWidget(b)

    def capture(self, mode):
        if self.send_safe_cmd({"type": "SCREENSHOT", "mode": mode}):
            h = recv_all(self.cmd_s, 4)
            if not h: return
            sz = struct.unpack("!I", h)[0]
            if sz > 0:
                path, _ = QFileDialog.getSaveFileName(self, f"Save {mode}", f"{mode.lower()}_{int(time.time())}.jpg", "*.jpg")
                if path:
                    progress = QProgressDialog(f"Downloading {mode}...", "Cancel", 0, 100, self)
                    progress.setWindowModality(Qt.WindowModal); progress.show()
                    old_timeout = self.cmd_s.gettimeout(); self.cmd_s.settimeout(0.1)
                    try:
                        with open(path, "wb") as f:
                            rem = sz
                            while rem > 0:
                                if progress.wasCanceled(): break
                                try:
                                    chunk = self.cmd_s.recv(min(rem, 131072))
                                    if not chunk: break
                                    f.write(chunk); rem -= len(chunk); progress.setValue(int((sz - rem) * 100 / sz))
                                except socket.timeout: pass
                                QApplication.processEvents()
                        if not progress.wasCanceled(): QMessageBox.information(self, "Done", f"{mode} captured and saved.")
                    finally: self.cmd_s.settimeout(old_timeout); progress.close()
            else: QMessageBox.warning(self, "Error", "Failed to capture. Check if webcam is available.")

    def toggle_record(self):
        if not self.is_recording:
            if self.send_safe_cmd({"type": "REC_START"}): self.is_recording = True; self.rec_btn.setText("STOP & DOWNLOAD")
        else:
            self.send_safe_cmd({"type": "REC_STOP"})
            progress = QProgressDialog("Server is finalizing video file...", "Cancel", 0, 0, self)
            progress.setWindowTitle("Processing"); progress.setWindowModality(Qt.WindowModal); progress.setRange(0, 0); progress.show(); QApplication.processEvents()
            old_timeout = self.cmd_s.gettimeout(); self.cmd_s.settimeout(0.1); h = b""
            try:
                while len(h) < 8:
                    if progress.wasCanceled(): break
                    try:
                        chunk = self.cmd_s.recv(8 - len(h))
                        if not chunk: break
                        h += chunk
                    except socket.timeout: pass
                    QApplication.processEvents()
            finally: self.cmd_s.settimeout(old_timeout)
            if progress.wasCanceled() or len(h) < 8: progress.close(); self.is_recording = False; self.rec_btn.setText("START RECORDING"); return
            sz = struct.unpack("!Q", h)[0]
            if sz > 0:
                path, _ = QFileDialog.getSaveFileName(self, "Save Video", f"record_{int(time.time())}.mp4", "*.mp4")
                if path:
                    progress.setLabelText("Downloading Video Record..."); progress.setRange(0, 100); progress.setValue(0); self.cmd_s.settimeout(0.1)
                    try:
                        with open(path, "wb") as f:
                            rem = sz
                            while rem > 0:
                                if progress.wasCanceled(): break
                                try:
                                    chunk = self.cmd_s.recv(min(rem, 131072))
                                    if not chunk: break
                                    f.write(chunk); rem -= len(chunk); progress.setValue(int((sz - rem) * 100 / sz))
                                except socket.timeout: pass
                                QApplication.processEvents()
                        if not progress.wasCanceled(): QMessageBox.information(self, "Done", "Video downloaded.")
                    finally: self.cmd_s.settimeout(old_timeout); progress.close()
                else: progress.close()
            else: progress.close(); QMessageBox.warning(self, "Info", "No video data recorded or file is empty.")
            self.is_recording = False; self.rec_btn.setText("START RECORDING")

class ControlMenu(RemoteBase):
    def __init__(self, ip, pwd):
        super().__init__(ip, pwd)
        self.ip, self.pwd, self.child_windows = ip, pwd, []
        self.setWindowTitle(f"SERVER: {ip}"); self.setFixedSize(320, 580)
        wid = QWidget(); self.setCentralWidget(wid); layout = QVBoxLayout(wid)
        info = QLabel(f"Connected to: {ip}"); info.setAlignment(Qt.AlignCenter); info.setStyleSheet("font-weight: bold; color: green;"); layout.addWidget(info)
        opts = [("LIVE CONTROL", self.open_live), ("PROCESSES", self.open_procs), ("SYSTEM APPS", self.open_apps), ("FILES", self.open_files), ("MEDIA / RECORD", self.open_media), ("ACTIVITY LOGS", self.open_logs), ("POWER OPTIONS", self.open_power)]
        for name, func in opts:
            b = QPushButton(name); b.setFixedHeight(50); b.clicked.connect(func); layout.addWidget(b)
            
    def open_live(self): w = LiveControl(self.ip, self.pwd, self); w.show(); self.child_windows.append(w)
    def open_procs(self): w = ProcessManager(self.ip, self.pwd, self); w.show(); self.child_windows.append(w)
    def open_apps(self): w = SystemApps(self.ip, self.pwd, self); w.show(); self.child_windows.append(w)
    def open_files(self): w = FileExplorer(self.ip, self.pwd, self); w.show(); self.child_windows.append(w)
    def open_logs(self): w = ActivityLogs(self.ip, self.pwd, self); w.show(); self.child_windows.append(w)
    def open_media(self): w = MediaManager(self.ip, self.pwd, self); w.show(); self.child_windows.append(w)
    def close_all_session(self):
        for w in self.child_windows:
            try: w.close()
            except: pass
        self.close()
    def closeEvent(self, ev): self.close_all_session(); super().closeEvent(ev)
    def open_power(self):
        m = QMessageBox(self); m.setWindowTitle("Power Options"); m.setText(f"Choose an action for server {self.ip}")
        btn_shut, btn_re = m.addButton("SHUTDOWN", QMessageBox.ActionRole), m.addButton("RESTART", QMessageBox.ActionRole)
        m.addButton("CANCEL", QMessageBox.RejectRole); m.exec_()
        if m.clickedButton() == btn_shut: self.power_cmd("SHUTDOWN")
        elif m.clickedButton() == btn_re: self.power_cmd("RESTART")
    def power_cmd(self, p_type):
        try:
            raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM); raw.connect((self.ip, 9999))
            ctx = ssl._create_unverified_context(); s = ctx.wrap_socket(raw, server_hostname=self.ip)
            s.sendall(self.pwd.encode()); recv_all(s, 4); cmd = json.dumps({"type": p_type}).encode(); s.sendall(struct.pack("!I", len(cmd)) + cmd)
            QMessageBox.information(self, "Success", f"Sent {p_type} command to server."); self.close()
        except: QMessageBox.critical(self, "Error", "Failed to send power command.")

class Dashboard(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Control Server - Multi Management"); self.resize(400, 500)
        self.sessions, self.db_path = [], Path("servers.json")
        layout = QVBoxLayout(self); layout.addWidget(QLabel("<b>ADD NEW SERVER</b>"))
        self.ip_input, self.pwd_input = QLineEdit("192.168.1.25"), QLineEdit()
        self.pwd_input.setPlaceholderText("Password"); self.pwd_input.setEchoMode(QLineEdit.Password)
        btn_add = QPushButton("CONNECT & SAVE"); btn_add.setFixedHeight(40); btn_add.clicked.connect(self.connect_new)
        layout.addWidget(self.ip_input); layout.addWidget(self.pwd_input); layout.addWidget(btn_add)
        layout.addWidget(QLabel("<br><b>SAVED SERVERS (Multi-control)</b>"))
        self.list = QListWidget(); self.list.itemDoubleClicked.connect(self.connect_saved); layout.addWidget(self.list)
        btn_del = QPushButton("REMOVE SELECTED"); btn_del.clicked.connect(self.remove_saved); layout.addWidget(btn_del); self.load_db()

    def load_db(self):
        self.list.clear()
        if self.db_path.exists():
            with open(self.db_path, "r") as f: self.saved_servers = json.load(f); [self.list.addItem(ip) for ip in self.saved_servers]
        else: self.saved_servers = {}
    def save_db(self):
        with open(self.db_path, "w") as f: json.dump(self.saved_servers, f)
    def connect_new(self):
        ip, pwd = self.ip_input.text(), self.pwd_input.text()
        if ip and pwd: self.run_session(ip, pwd); self.saved_servers[ip] = pwd; self.save_db(); self.load_db()
    def connect_saved(self, item):
        ip, pwd = item.text(), self.saved_servers.get(item.text())
        if not pwd: return
        if self.verify_and_run(ip, pwd): return
        new_pwd, ok = QInputDialog.getText(self, "Authentication Failed", 
                                         f"Could not connect to {ip} with saved password.\nEnter new password:", 
                                         QLineEdit.Password)
        if ok and new_pwd:
            if self.verify_and_run(ip, new_pwd): self.saved_servers[ip] = new_pwd; self.save_db()
            else: QMessageBox.critical(self, "Error", "Still cannot connect. Server might be offline or password is wrong.")
    def verify_and_run(self, ip, pwd):
        try:
            raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM); raw.settimeout(3); raw.connect((ip, 9999))
            ctx = ssl._create_unverified_context(); s = ctx.wrap_socket(raw, server_hostname=ip)
            s.sendall(pwd.encode()); h = recv_all(s, 4)
            if h:
                sz = struct.unpack("!I", h)[0]; data = json.loads(recv_all(s, sz).decode()); s.close()
                if data.get('status') == "OK": self.run_session(ip, pwd); return True
            return False
        except: return False
    def remove_saved(self):
        if self.list.currentItem(): del self.saved_servers[self.list.currentItem().text()]; self.save_db(); self.load_db()
    def run_session(self, ip, pwd):
        try: m = ControlMenu(ip, pwd); m.show(); self.sessions.append(m)
        except Exception as e: QMessageBox.critical(self, "Error", str(e))

if __name__ == "__main__":
    app = QApplication(sys.argv); app.setStyle("Fusion"); d = Dashboard(); d.show(); sys.exit(app.exec_())
