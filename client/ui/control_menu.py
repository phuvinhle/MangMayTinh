import socket
import ssl
import json
import struct
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt
from client.core.base import RemoteBase
from client.core.network import recv_all
from client.ui.live_control import LiveControl
from client.ui.process_manager import ProcessManager
from client.ui.system_apps import SystemApps
from client.ui.file_explorer import FileExplorer
from client.ui.activity_logs import ActivityLogs
from client.ui.media_manager import MediaManager

class ControlMenu(RemoteBase, QMainWindow):
    def __init__(self, ip, pwd, on_close_callback=None):
        super().__init__(ip, pwd)
        self.ip, self.pwd, self.child_windows = ip, pwd, []
        self.on_close_callback = on_close_callback
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
        # 1. Close all child windows explicitly
        for w in list(self.child_windows):
            try:
                w.close()
                self.child_windows.remove(w)
            except: pass
        # 2. Finally close this menu
        self.close()

    def closeEvent(self, ev):
        # Notify the dashboard that this session is ending
        if self.on_close_callback: self.on_close_callback(self.ip)
        # Standard base cleanup handles cmd_s
        super().closeEvent(ev)
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
