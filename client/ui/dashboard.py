import json
import socket
import ssl
import struct
from pathlib import Path
from PyQt5.QtWidgets import *
from PyQt5.QtGui import QColor
from client.core.network import recv_all
from client.ui.control_menu import ControlMenu

class Dashboard(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Control Server - Multi Management"); self.resize(500, 600)
        # Updated path
        self.db_path = Path("resources/data/servers.json")
        self.active_sessions = {}
        layout = QVBoxLayout(self); layout.addWidget(QLabel("<b>ADD NEW SERVER</b>"))
        
        form = QHBoxLayout()
        self.ip_input = QLineEdit("192.168.1.25"); self.ip_input.setPlaceholderText("Server IP")
        self.pwd_input = QLineEdit(); self.pwd_input.setPlaceholderText("Password"); self.pwd_input.setEchoMode(QLineEdit.Password)
        btn_add = QPushButton("ADD & CONNECT"); btn_add.clicked.connect(self.connect_new)
        form.addWidget(self.ip_input); form.addWidget(self.pwd_input); form.addWidget(btn_add)
        layout.addLayout(form)
        
        layout.addWidget(QLabel("<br><b>CONNECTION MANAGER</b>"))
        self.table = QTableWidget(0, 3); self.table.setHorizontalHeaderLabels(["Server IP", "Status", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)
        
        self.btn_del = QPushButton("REMOVE SELECTED FROM LIST"); self.btn_del.clicked.connect(self.remove_saved)
        layout.addWidget(self.btn_del)
        self.load_db()

    def load_db(self):
        if self.db_path.exists():
            with open(self.db_path, "r") as f: self.saved_servers = json.load(f)
        else: 
            self.saved_servers = {}
            # Ensure directory exists
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.update_table()

    def save_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.db_path, "w") as f: json.dump(self.saved_servers, f)

    def update_table(self):
        self.table.setRowCount(0)
        for ip, pwd in self.saved_servers.items():
            r = self.table.rowCount(); self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(ip))
            
            is_active = ip in self.active_sessions
            status_item = QTableWidgetItem("CONNECTED" if is_active else "OFFLINE")
            status_item.setForeground(QColor("green" if is_active else "red"))
            self.table.setItem(r, 1, status_item)
            
            btn_box = QWidget(); btn_layout = QHBoxLayout(btn_box); btn_layout.setContentsMargins(2, 2, 2, 2)
            if is_active:
                b_stop = QPushButton("STOP"); b_stop.setStyleSheet("color: red;"); b_stop.clicked.connect(lambda _, i=ip: self.stop_session(i))
                btn_layout.addWidget(b_stop)
            else:
                b_conn = QPushButton("CONNECT"); b_conn.clicked.connect(lambda _, i=ip, p=pwd: self.connect_saved(i, p))
                btn_layout.addWidget(b_conn)
            self.table.setCellWidget(r, 2, btn_box)

    def connect_new(self):
        ip, pwd = self.ip_input.text(), self.pwd_input.text()
        if ip and pwd:
            if ip in self.active_sessions: QMessageBox.warning(self, "Error", "Already connected."); return
            if self.verify_and_run(ip, pwd):
                self.saved_servers[ip] = pwd; self.save_db(); self.update_table()
            else: QMessageBox.critical(self, "Error", "Could not connect. Check IP/Pass.")

    def connect_saved(self, ip, pwd):
        if self.verify_and_run(ip, pwd): self.update_table()
        else:
            new_pwd, ok = QInputDialog.getText(self, "Authentication Failed", 
                                             f"Could not connect to {ip} with saved password.\nEnter new password:", 
                                             QLineEdit.Password)
            if ok and new_pwd:
                if self.verify_and_run(ip, new_pwd):
                    self.saved_servers[ip] = new_pwd; self.save_db(); self.update_table()
                else: QMessageBox.critical(self, "Error", "Connection failed again.")

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

    def run_session(self, ip, pwd):
        try:
            m = ControlMenu(ip, pwd, on_close_callback=self.on_session_closed)
            m.show(); self.active_sessions[ip] = m
        except Exception as e: QMessageBox.critical(self, "Error", str(e))

    def on_session_closed(self, ip):
        if ip in self.active_sessions: del self.active_sessions[ip]
        self.update_table()

    def stop_session(self, ip):
        if ip in self.active_sessions:
            self.active_sessions[ip].close_all_session() # This triggers on_session_closed

    def remove_saved(self):
        row = self.table.currentRow()
        if row >= 0:
            ip = self.table.item(row, 0).text()
            if ip in self.active_sessions: self.stop_session(ip)
            del self.saved_servers[ip]; self.save_db(); self.update_table()

    def closeEvent(self, ev):
        reply = QMessageBox.question(self, 'Exit Confirmation', 
                                   "Are you sure you want to exit? This will close all active connections.", 
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            # Shutdown everything
            for ip in list(self.active_sessions.keys()):
                self.stop_session(ip)
            super().closeEvent(ev)
            QApplication.quit()
        else:
            ev.ignore()
