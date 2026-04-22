import json
import socket
import ssl
import struct
from pathlib import Path
from PyQt5.QtWidgets import *
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtCore import QTimer, Qt
from client.core.network import recv_all
from client.ui.control_menu import ControlMenu

class Dashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Control Client - Dashboard")
        self.setFixedSize(650, 750)
        self.db_path = Path("resources/data/servers.json")
        self.active_sessions = {}
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(15)

        # Header - Centered
        title = QLabel("REMOTE CONTROL DASHBOARD")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #2c3e50; margin-bottom: 5px;")
        layout.addWidget(title)

        # Add New Server Box
        add_group = QGroupBox("Add New Server")
        add_layout = QGridLayout()
        add_layout.setContentsMargins(15, 15, 15, 15)
        add_layout.setSpacing(10)
        
        add_layout.addWidget(QLabel("Server IP:"), 0, 0)
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("e.g. 192.168.1.100")
        self.ip_input.setFixedHeight(30)
        self.ip_input.setStyleSheet("padding-left: 10px; border: 1px solid #dcdde1; border-radius: 4px;")
        add_layout.addWidget(self.ip_input, 0, 1)

        add_layout.addWidget(QLabel("Password:"), 1, 0)
        self.pwd_input = QLineEdit()
        self.pwd_input.setEchoMode(QLineEdit.Password)
        self.pwd_input.setPlaceholderText("Access Password")
        self.pwd_input.setFixedHeight(30)
        self.pwd_input.setStyleSheet("padding-left: 10px; border: 1px solid #dcdde1; border-radius: 4px;")
        add_layout.addWidget(self.pwd_input, 1, 1)

        self.btn_connect = QPushButton("CONNECT NOW")
        self.btn_connect.setFixedHeight(40)
        self.btn_connect.setCursor(Qt.PointingHandCursor)
        self.btn_connect.setStyleSheet("background-color: #3498db; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_connect.clicked.connect(self.connect_new)
        add_layout.addWidget(self.btn_connect, 2, 0, 1, 2)

        add_group.setLayout(add_layout)
        layout.addWidget(add_group)

        # Server List Header with Remove Button
        list_header = QHBoxLayout()
        list_header.addWidget(QLabel("<b>Saved Servers:</b>"), 0, Qt.AlignVCenter)
        list_header.addStretch()
        
        self.btn_remove_selected = QPushButton("🗑️ REMOVE SELECTED")
        self.btn_remove_selected.setFixedWidth(150)
        self.btn_remove_selected.setStyleSheet("font-size: 10px; color: #e74c3c; background-color: #fff5f5; border: 1px solid #ffc9c9; border-radius: 4px; padding: 5px;")
        self.btn_remove_selected.setCursor(Qt.PointingHandCursor)
        self.btn_remove_selected.clicked.connect(self.remove_saved)
        list_header.addWidget(self.btn_remove_selected)
        layout.addLayout(list_header)

        # Table
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Server IP", "Status", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet("background-color: white; border: 1px solid #dcdde1; border-radius: 4px;")
        layout.addWidget(self.table)

        self.load_db()
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_active_sessions)
        self.timer.start(5000)

    def check_active_sessions(self):
        for ip in list(self.active_sessions.keys()):
            ip = ip.strip()
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(1)
                s.connect((ip, 9999)); s.close()
            except:
                self.stop_session(ip)
                QMessageBox.warning(self, "Disconnected", f"Server {ip} is no longer connected.")
                self.update_table()

    def load_db(self):
        if self.db_path.exists():
            try:
                with open(self.db_path, "r") as f: self.saved_servers = json.load(f)
                self.saved_servers = {k.strip(): v.strip() for k, v in self.saved_servers.items()}
            except: self.saved_servers = {}
        else: 
            self.saved_servers = {}
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.update_table()

    def save_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.db_path, "w") as f: json.dump(self.saved_servers, f)

    def update_table(self):
        self.table.setRowCount(0)
        for ip, pwd in self.saved_servers.items():
            ip = ip.strip()
            r = self.table.rowCount(); self.table.insertRow(r)
            
            ip_item = QTableWidgetItem(ip)
            ip_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 0, ip_item)
            
            is_active = ip in self.active_sessions
            status_item = QTableWidgetItem("CONNECTED" if is_active else "DISCONNECTED")
            status_item.setForeground(QColor("#27ae60" if is_active else "#e74c3c"))
            status_item.setFont(QFont("Arial", 9, QFont.Bold))
            status_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 1, status_item)
            
            btn_box = QWidget(); btn_layout = QHBoxLayout(btn_box); btn_layout.setContentsMargins(5, 2, 5, 2); btn_layout.setAlignment(Qt.AlignCenter)
            if is_active:
                btn = QPushButton("STOP"); btn.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold; border-radius: 3px;")
                btn.clicked.connect(lambda _, i=ip: self.stop_session(i))
            else:
                btn = QPushButton("CONNECT"); btn.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold; border-radius: 3px;")
                btn.clicked.connect(lambda _, i=ip, p=pwd: self.connect_saved(i, p))
            btn.setFixedSize(80, 26); btn.setCursor(Qt.PointingHandCursor); btn_layout.addWidget(btn); self.table.setCellWidget(r, 2, btn_box)
        
    def connect_new(self):
        ip, pwd = self.ip_input.text().strip(), self.pwd_input.text().strip()
        if ip.endswith('.'): ip = ip[:-1]
        if ip and pwd:
            if ip in self.active_sessions: return
            if self.verify_and_run(ip, pwd):
                self.saved_servers[ip] = pwd; self.save_db(); self.update_table()
                self.ip_input.clear(); self.pwd_input.clear()
            else: QMessageBox.critical(self, "Error", "Connection failed.")

    def connect_saved(self, ip, pwd):
        ip = ip.strip()
        if ip.endswith('.'): ip = ip[:-1]
        if self.verify_and_run(ip, pwd): self.update_table()
        else:
            new_pwd, ok = QInputDialog.getText(self, "Authentication", f"Could not connect to {ip}.\nEnter password:", QLineEdit.Password)
            if ok and new_pwd:
                if self.verify_and_run(ip, new_pwd.strip()):
                    self.saved_servers[ip] = new_pwd.strip(); self.save_db(); self.update_table()
                else: QMessageBox.critical(self, "Error", "Connection failed.")

    def verify_and_run(self, ip, pwd):
        try:
            raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM); raw.settimeout(3); raw.connect((ip, 9999))
            ctx = ssl._create_unverified_context(); s = ctx.wrap_socket(raw, server_hostname=ip)
            s.sendall(pwd.strip().encode()); h = recv_all(s, 4)
            if h:
                sz = struct.unpack("!I", h)[0]; data = json.loads(recv_all(s, sz).decode()); s.close()
                if data.get('status') == "OK": self.run_session(ip, pwd.strip()); return True
            return False
        except: return False

    def run_session(self, ip, pwd):
        try:
            m = ControlMenu(ip, pwd, on_close_callback=self.on_session_closed)
            m.show(); self.active_sessions[ip] = m
        except: pass

    def on_session_closed(self, ip):
        if ip in self.active_sessions: del self.active_sessions[ip]
        self.update_table()

    def stop_session(self, ip):
        if ip in self.active_sessions: self.active_sessions[ip].close_all_session()

    def remove_saved(self):
        row = self.table.currentRow()
        if row >= 0:
            ip = self.table.item(row, 0).text().strip()
            if QMessageBox.question(self, "Confirm", f"Remove {ip} from saved list?") == QMessageBox.Yes:
                if ip in self.active_sessions: self.stop_session(ip)
                if ip in self.saved_servers: del self.saved_servers[ip]; self.save_db(); self.update_table()
        else: QMessageBox.information(self, "Info", "Please select a server from the table to remove.")

    def closeEvent(self, ev):
        reply = QMessageBox.question(self, 'Exit', "Disconnect all and exit?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            for ip in list(self.active_sessions.keys()): self.stop_session(ip)
            super().closeEvent(ev); QApplication.quit()
        else: ev.ignore()
