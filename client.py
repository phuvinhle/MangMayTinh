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
        if not self.init_cmd(): raise ConnectionError(f"Connection to {ip} failed")

    def init_cmd(self):
        try:
            raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            raw.settimeout(5)
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
        except: return False

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
            ox, oy = (self.view.width()-pm.width())/2, (self.view.height()-pm.height())/2
            rx, ry = p.x()-ox, p.y()-oy
            if 0 <= rx <= pm.width() and 0 <= ry <= pm.height():
                fx, fy = int(rx * self.target_res[0]/pm.width()), int(ry * self.target_res[1]/pm.height())
                self.send_safe_cmd({"type": "MOUSE", "x": fx, "y": fy, "btn": "right" if ev.button()==Qt.RightButton else "left"})

    def closeEvent(self, ev):
        self.active = False; self.send_safe_cmd({"type": "STREAM_CTRL", "active": False}); super().closeEvent(ev)

class ProcessManager(RemoteBase):
    def __init__(self, ip, pwd):
        super().__init__(ip, pwd)
        self.setWindowTitle(f"Processes - {ip}"); self.resize(700, 500)
        wid = QWidget(); self.setCentralWidget(wid); layout = QVBoxLayout(wid)
        self.search = QLineEdit(); self.search.setPlaceholderText("Search..."); layout.addWidget(self.search)
        self.table = QTableWidget(0, 4); self.table.setHorizontalHeaderLabels(["PID", "Name", "CPU", "MEM"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)
        btns = QHBoxLayout(); b1 = QPushButton("REFRESH"); b1.clicked.connect(self.load); b2 = QPushButton("KILL")
        b2.clicked.connect(self.kill); btns.addWidget(b1); btns.addWidget(b2); layout.addLayout(btns); self.load()

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
        self.setWindowTitle(f"Files - {ip}"); self.resize(800, 600)
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
                QMessageBox.information(self, "Done", "Download Completed")

class ControlMenu(QMainWindow):
    def __init__(self, ip, pwd):
        super().__init__()
        self.ip, self.pwd, self.child_windows = ip, pwd, []
        self.setWindowTitle(f"SERVER: {ip}"); self.setFixedSize(320, 520)
        wid = QWidget(); self.setCentralWidget(wid); layout = QVBoxLayout(wid)
        
        info = QLabel(f"Connected to: {ip}"); info.setAlignment(Qt.AlignCenter)
        info.setStyleSheet("font-weight: bold; color: green;"); layout.addWidget(info)
        
        opts = [
            ("LIVE CONTROL", self.open_live),
            ("PROCESSES", self.open_procs),
            ("FILES", self.open_files),
            ("POWER OPTIONS", self.open_power)
        ]
        for name, func in opts:
            b = QPushButton(name); b.setFixedHeight(50); b.clicked.connect(func); layout.addWidget(b)
            
    def open_live(self): w = LiveControl(self.ip, self.pwd); w.show(); self.child_windows.append(w)
    def open_procs(self): w = ProcessManager(self.ip, self.pwd); w.show(); self.child_windows.append(w)
    def open_files(self): w = FileExplorer(self.ip, self.pwd); w.show(); self.child_windows.append(w)
    
    def open_power(self):
        m = QMessageBox(self)
        m.setWindowTitle("Power Options")
        m.setText(f"Choose an action for server {self.ip}")
        btn_shut = m.addButton("SHUTDOWN", QMessageBox.ActionRole)
        btn_re = m.addButton("RESTART", QMessageBox.ActionRole)
        m.addButton("CANCEL", QMessageBox.RejectRole)
        m.exec_()
        if m.clickedButton() == btn_shut: self.power_cmd("SHUTDOWN")
        elif m.clickedButton() == btn_re: self.power_cmd("RESTART")

    def power_cmd(self, p_type):
        try:
            raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM); raw.connect((self.ip, 9999))
            ctx = ssl._create_unverified_context(); s = ctx.wrap_socket(raw, server_hostname=self.ip)
            s.sendall(self.pwd.encode())
            recv_all(s, 4) # Skip handshake
            cmd = json.dumps({"type": p_type}).encode()
            s.sendall(struct.pack("!I", len(cmd)) + cmd)
            QMessageBox.information(self, "Success", f"Sent {p_type} command to server.")
            self.close()
        except: QMessageBox.critical(self, "Error", "Failed to send power command.")

class Dashboard(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Control Server - Multi Management"); self.resize(400, 500)
        self.sessions = []; self.db_path = Path("servers.json")
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("<b>ADD NEW SERVER</b>"))
        self.ip_input = QLineEdit("192.168.1.25"); self.pwd_input = QLineEdit()
        self.pwd_input.setPlaceholderText("Password"); self.pwd_input.setEchoMode(QLineEdit.Password)
        btn_add = QPushButton("CONNECT & SAVE"); btn_add.setFixedHeight(40)
        btn_add.clicked.connect(self.connect_new); layout.addWidget(self.ip_input); layout.addWidget(self.pwd_input); layout.addWidget(btn_add)
        
        layout.addWidget(QLabel("<br><b>SAVED SERVERS (Multi-control)</b>"))
        self.list = QListWidget(); self.list.itemDoubleClicked.connect(self.connect_saved); layout.addWidget(self.list)
        
        btn_del = QPushButton("REMOVE SELECTED"); btn_del.clicked.connect(self.remove_saved); layout.addWidget(btn_del)
        self.load_db()

    def load_db(self):
        self.list.clear()
        if self.db_path.exists():
            with open(self.db_path, "r") as f:
                self.saved_servers = json.load(f)
                for ip in self.saved_servers: self.list.addItem(ip)
        else: self.saved_servers = {}

    def save_db(self):
        with open(self.db_path, "w") as f: json.dump(self.saved_servers, f)

    def connect_new(self):
        ip, pwd = self.ip_input.text(), self.pwd_input.text()
        if not ip or not pwd: return
        self.run_session(ip, pwd)
        self.saved_servers[ip] = pwd; self.save_db(); self.load_db()

    def connect_saved(self, item):
        ip = item.text(); pwd = self.saved_servers.get(ip)
        if pwd: self.run_session(ip, pwd)

    def remove_saved(self):
        it = self.list.currentItem()
        if it:
            del self.saved_servers[it.text()]; self.save_db(); self.load_db()

    def run_session(self, ip, pwd):
        try:
            m = ControlMenu(ip, pwd); m.show(); self.sessions.append(m)
        except Exception as e: QMessageBox.critical(self, "Error", str(e))

if __name__ == "__main__":
    app = QApplication(sys.argv); app.setStyle("Fusion")
    d = Dashboard(); d.show(); sys.exit(app.exec_())
