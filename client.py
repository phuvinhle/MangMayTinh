import sys
import os
from pathlib import Path

# --- DLL FIX FOR WINDOWS (uv/venv optimized) ---
if sys.platform == "win32":
    # uv often puts site-packages in a standard location
    # We try multiple ways to find the PyQt5 Qt bin folder
    executable_path = Path(sys.executable).parent
    possible_bin_paths = [
        executable_path / "Lib" / "site-packages" / "PyQt5" / "Qt5" / "bin",
        executable_path.parent / "Lib" / "site-packages" / "PyQt5" / "Qt5" / "bin",
        # For some uv structures
        executable_path / "site-packages" / "PyQt5" / "Qt5" / "bin"
    ]
    
    for p in possible_bin_paths:
        if p.exists():
            os.add_dll_directory(str(p))
            os.environ["PATH"] = str(p) + os.pathsep + os.environ["PATH"]
            break

# Linux Fix
if sys.platform == "linux":
    try:
        executable_path = Path(sys.executable).parent
        # Try to find plugins path in a similar way
        plugins_path = list(executable_path.parent.glob("**/PyQt5/Qt5/plugins"))
        if plugins_path:
            os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(plugins_path[0])
            os.environ["QT_QPA_PLATFORM"] = "xcb"
    except: pass

import socket
import ssl
import struct
import cv2
import json
import time
import numpy as np
import threading
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

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
    def __init__(self, ip, pwd):
        super().__init__()
        self.ip, self.pwd = ip, pwd
        self.target_res = (1280, 720)
        self.cmd_s = None
        if not self.init_cmd(): raise ConnectionError("Handshake failed")

    def init_cmd(self):
        try:
            raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            raw.settimeout(10)
            ctx = ssl._create_unverified_context()
            ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
            self.cmd_s = ctx.wrap_socket(raw)
            self.cmd_s.connect((self.ip, 9999))
            self.cmd_s.sendall(self.pwd.encode())
            
            h = recv_all(self.cmd_s, 4)
            if not h:
                print("Auth Error: No response from server"); return False
            sz = struct.unpack("!I", h)[0]
            data = recv_all(self.cmd_s, sz)
            if not data:
                print("Auth Error: Failed to receive handshake data"); return False
            res = json.loads(data.decode())
            if res.get('status') == "OK":
                self.target_res = (res['w'], res['h']); return True
            else:
                msg = res.get('msg', 'Unknown error')
                print(f"Auth Error: {msg}"); return False
        except Exception as e:
            print(f"Auth Error: {e}"); return False

    def send_safe_cmd(self, data):
        try:
            p = json.dumps(data).encode('utf-8')
            self.cmd_s.sendall(struct.pack("!I", len(p)) + p); return True
        except: return False

    def recv_json(self):
        try:
            h = recv_all(self.cmd_s, 4)
            if not h: return None
            sz = struct.unpack("!I", h)[0]
            return json.loads(recv_all(self.cmd_s, sz).decode())
        except: return None

class LiveControl(RemoteBase):
    def __init__(self, ip, pwd):
        super().__init__(ip, pwd)
        self.setWindowTitle(f"Live Control - {ip}"); self.resize(1000, 750)
        self.view = QLabel("Loading Stream..."); self.view.setAlignment(Qt.AlignCenter)
        self.view.setStyleSheet("background: black;"); self.setCentralWidget(self.view)
        self.send_safe_cmd({"type": "STREAM_CTRL", "active": True, "mode": "SCREEN"})
        self.active = True
        threading.Thread(target=self.stream_loop, daemon=True).start()

    def stream_loop(self):
        ctx = ssl._create_unverified_context()
        ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        try:
            s = ctx.wrap_socket(socket.socket())
            s.connect((self.ip, 9998))
            while self.active:
                h = recv_all(s, 4)
                if not h: break
                sz = struct.unpack("!I", h)[0]
                b = recv_all(s, sz)
                img = cv2.imdecode(np.frombuffer(b, np.uint8), 1)
                if img is not None:
                    qi = QImage(img.data, img.shape[1], img.shape[0], img.shape[1]*3, QImage.Format_RGB888).rgbSwapped()
                    pix = QPixmap.fromImage(qi).scaled(self.view.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    QMetaObject.invokeMethod(self.view, "setPixmap", Qt.QueuedConnection, Q_ARG(QPixmap, pix))
            s.close()
        except: pass

    def mousePressEvent(self, ev):
        p = self.view.mapFromParent(ev.pos())
        if self.view.rect().contains(p) and self.view.pixmap():
            pm = self.view.pixmap()
            offset_x = (self.view.width()-pm.width())/2; offset_y = (self.view.height()-pm.height())/2
            rx, ry = p.x()-offset_x, p.y()-offset_y
            if 0 <= rx <= pm.width() and 0 <= ry <= pm.height():
                fx, fy = int(rx * self.target_res[0]/pm.width()), int(ry * self.target_res[1]/pm.height())
                self.send_safe_cmd({"type": "MOUSE", "x": fx, "y": fy, "btn": "right" if ev.button()==Qt.RightButton else "left"})

    def closeEvent(self, ev):
        self.active = False; self.send_safe_cmd({"type": "STREAM_CTRL", "active": False}); super().closeEvent(ev)

class ProcessManager(RemoteBase):
    def __init__(self, ip, pwd):
        super().__init__(ip, pwd)
        self.setWindowTitle("Processes"); self.resize(700, 500)
        wid = QWidget(); self.setCentralWidget(wid); layout = QVBoxLayout(wid)
        self.search = QLineEdit(); self.search.setPlaceholderText("Search..."); layout.addWidget(self.search)
        self.table = QTableWidget(0, 4); self.table.setHorizontalHeaderLabels(["PID", "Name", "CPU", "MEM"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)
        btns = QHBoxLayout(); b1 = QPushButton("LOAD"); b1.clicked.connect(self.load); b2 = QPushButton("KILL"); b2.clicked.connect(self.kill)
        btns.addWidget(b1); btns.addWidget(b2); layout.addLayout(btns); self.load()

    def load(self):
        self.send_safe_cmd({"type": "LIST_PROCS"})
        data = self.recv_json()
        if data:
            self.table.setRowCount(0)
            for p in data:
                if self.search.text().lower() in p['name'].lower():
                    r = self.table.rowCount(); self.table.insertRow(r)
                    self.table.setItem(r, 0, QTableWidgetItem(str(p['pid'])))
                    self.table.setItem(r, 1, QTableWidgetItem(p['name']))
                    self.table.setItem(r, 2, QTableWidgetItem(f"{p['cpu_percent']}%"))
                    self.table.setItem(r, 3, QTableWidgetItem(f"{round(p['memory_percent'],1)}%"))

    def kill(self):
        row = self.table.currentRow()
        if row >= 0:
            pid = int(self.table.item(row, 0).text())
            self.send_safe_cmd({"type": "KILL_PROC", "pid": pid}); time.sleep(0.5); self.load()

class FileExplorer(RemoteBase):
    def __init__(self, ip, pwd):
        super().__init__(ip, pwd)
        self.setWindowTitle("Files"); self.resize(800, 600)
        wid = QWidget(); self.setCentralWidget(wid); layout = QVBoxLayout(wid)
        self.path = QLineEdit("/"); layout.addWidget(self.path)
        self.table = QTableWidget(0, 3); self.table.setHorizontalHeaderLabels(["Name", "Type", "Size"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.itemDoubleClicked.connect(self.dive)
        layout.addWidget(self.table); btn = QPushButton("DOWNLOAD"); btn.clicked.connect(self.download); layout.addWidget(btn); self.load()

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
        self.send_safe_cmd({"type": "DOWNLOAD", "path": str(Path(self.path.text())/name)})
        h = recv_all(self.cmd_s, 8)
        if not h: return
        sz = struct.unpack("!Q", h)[0]
        if sz > 0:
            lp, _ = QFileDialog.getSaveFileName(self, "Save", name if "." in name else name+".zip")
            if lp:
                with open(lp, "wb") as f:
                    rem = sz
                    while rem > 0:
                        chunk = self.cmd_s.recv(min(rem, 32768))
                        if not chunk: break
                        f.write(chunk); rem -= len(chunk)
                QMessageBox.information(self, "Done", "Completed")

class RecordCapture(RemoteBase):
    def __init__(self, ip, pwd):
        super().__init__(ip, pwd)
        self.setWindowTitle("Capture"); self.resize(400, 500)
        wid = QWidget(); self.setCentralWidget(wid); layout = QVBoxLayout(wid)
        self.preview = QLabel("Capture Preview"); self.preview.setFixedSize(320, 240); self.preview.setStyleSheet("border: 1px solid gray;"); layout.addWidget(self.preview)
        btns = [("SNAP SCREEN", lambda: self.snap("SCREEN")), ("SNAP WEBCAM", lambda: self.snap("WEBCAM"))]
        for n, f in btns: b = QPushButton(n); b.clicked.connect(f); layout.addWidget(b)
        self.btn_rec = QPushButton("RECORD WEBCAM"); self.btn_rec.setCheckable(True); self.btn_rec.clicked.connect(self.rec); layout.addWidget(self.btn_rec)

    def snap(self, mode):
        self.send_safe_cmd({"type": "SCREENSHOT", "mode": mode})
        h = recv_all(self.cmd_s, 4)
        if not h: return
        sz = struct.unpack("!I", h)[0]
        data = recv_all(self.cmd_s, sz)
        img = cv2.imdecode(np.frombuffer(data, np.uint8), 1)
        self.preview.setPixmap(QPixmap.fromImage(QImage(img.data, img.shape[1], img.shape[0], img.shape[1]*3, QImage.Format_RGB888).rgbSwapped()).scaled(320, 240, Qt.KeepAspectRatio))
        path, _ = QFileDialog.getSaveFileName(self, "Save", "shot.jpg"); 
        if path:
            with open(path, "wb") as f: f.write(data)

    def rec(self, checked):
        if checked:
            self.send_safe_cmd({"type": "REC_START", "mode": "WEBCAM"}); self.btn_rec.setText("STOP & DOWNLOAD")
        else:
            self.send_safe_cmd({"type": "REC_STOP"})
            h = recv_all(self.cmd_s, 8)
            if not h: return
            sz = struct.unpack("!Q", h)[0]
            if sz > 0:
                lp, _ = QFileDialog.getSaveFileName(self, "Save Video", "video.mp4")
                if lp:
                    with open(lp, "wb") as f:
                        rem = sz
                        while rem > 0:
                            chunk = self.cmd_s.recv(min(rem, 32768))
                            if not chunk: break
                            f.write(chunk); rem -= len(chunk)
            self.btn_rec.setText("RECORD WEBCAM")

class SystemApps(RemoteBase):
    def __init__(self, ip, pwd):
        super().__init__(ip, pwd)
        self.setWindowTitle("System Apps"); self.resize(500, 600)
        wid = QWidget(); self.setCentralWidget(wid); layout = QVBoxLayout(wid)
        self.list = QListWidget(); layout.addWidget(self.list)
        btn = QPushButton("START SELECTED"); btn.clicked.connect(self.start)
        layout.addWidget(btn); self.load()

    def load(self):
        self.send_safe_cmd({"type": "LIST_APPS"})
        self.apps = self.recv_json()
        if self.apps:
            self.list.clear()
            for a in self.apps: self.list.addItem(f"{'[SW] ' if a['sw'] else ''}{a['name']}")

    def start(self):
        idx = self.list.currentRow()
        if idx >= 0: self.send_safe_cmd({"type": "START_APP", "exec": self.apps[idx]['exec']})

class LogMonitor(RemoteBase):
    def __init__(self, ip, pwd):
        super().__init__(ip, pwd)
        self.setWindowTitle("Logs"); self.resize(500, 400)
        wid = QWidget(); self.setCentralWidget(wid); layout = QVBoxLayout(wid)
        self.text = QTextEdit(); self.text.setReadOnly(True); layout.addWidget(self.text)
        btn = QPushButton("EXPORT"); btn.clicked.connect(self.export); layout.addWidget(btn)
        self.timer = QTimer(); self.timer.timeout.connect(self.fetch); self.timer.start(1000)

    def fetch(self):
        self.send_safe_cmd({"type": "GET_LOGS"})
        logs = self.recv_json()
        if logs:
            for l in logs: self.text.append(l)

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Log", "activity.txt")
        if path:
            with open(path, "w") as f: f.write(self.text.toPlainText())

class ControlMenu(QMainWindow):
    def __init__(self, ip, pwd):
        super().__init__()
        self.ip, self.pwd, self.child_windows = ip, pwd, []
        self.setWindowTitle(f"MENU - {ip}"); self.setFixedSize(300, 450)
        wid = QWidget(); self.setCentralWidget(wid); layout = QVBoxLayout(wid)
        opts = [("LIVE CONTROL", self.open_live), ("PROCESSES", self.open_procs), ("FILES", self.open_files), ("CAPTURE/RECORD", self.open_rec), ("SYSTEM APPS", self.open_apps), ("LOGS", self.open_logs)]
        for name, func in opts:
            b = QPushButton(name); b.setFixedHeight(50); b.clicked.connect(func); layout.addWidget(b)

    def open_live(self): self.w1 = LiveControl(self.ip, self.pwd); self.w1.show(); self.child_windows.append(self.w1)
    def open_procs(self): self.w2 = ProcessManager(self.ip, self.pwd); self.w2.show(); self.child_windows.append(self.w2)
    def open_files(self): self.w3 = FileExplorer(self.ip, self.pwd); self.w3.show(); self.child_windows.append(self.w3)
    def open_rec(self): self.w4 = RecordCapture(self.ip, self.pwd); self.w4.show(); self.child_windows.append(self.w4)
    def open_apps(self): self.w5 = SystemApps(self.ip, self.pwd); self.w5.show(); self.child_windows.append(self.w5)
    def open_logs(self): self.w6 = LogMonitor(self.ip, self.pwd); self.w6.show(); self.child_windows.append(self.w6)

class Dashboard(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LOGIN"); self.setFixedSize(350, 200); self.sessions = []
        l = QVBoxLayout(self)
        self.ip = QLineEdit("192.168.1.25"); self.pwd = QLineEdit(); self.pwd.setEchoMode(QLineEdit.Password)
        btn = QPushButton("CONNECT SERVER"); btn.setFixedHeight(40); btn.clicked.connect(self.go)
        l.addWidget(QLabel("IP:")); l.addWidget(self.ip); l.addWidget(QLabel("PASS:")); l.addWidget(self.pwd); l.addWidget(btn)

    def go(self):
        try:
            m = ControlMenu(self.ip.text(), self.pwd.text())
            m.show(); self.sessions.append(m)
        except Exception as e: QMessageBox.critical(self, "Error", f"Auth Failed: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv); app.setStyle("Fusion")
    d = Dashboard(); d.show(); sys.exit(app.exec_())
