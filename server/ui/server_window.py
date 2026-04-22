import sys
import time
import json
import os
import subprocess
from pathlib import Path
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor

class ServerWindow(QMainWindow):
    def __init__(self, server):
        super().__init__()
        self.server = server
        self.setWindowTitle("Control Server - Status")
        self.setFixedSize(550, 680)
        
        # Persistence path
        self.history_path = Path("resources/data/server_history.json")
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(15)

        # Header Section - Centered
        self.title_label = QLabel("SERVER STATUS: OFFLINE")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("color: #e74c3c; font-weight: bold; font-size: 20px; margin-bottom: 5px;")
        layout.addWidget(self.title_label)

        # Info Box
        info_group = QGroupBox("Server Access Info")
        info_layout = QGridLayout()
        info_layout.setContentsMargins(15, 15, 15, 15)
        info_layout.setSpacing(10)
        
        # IP Field
        info_layout.addWidget(QLabel("IP Address:"), 0, 0)
        self.ip_val = QLineEdit(self.server.get_local_ip())
        self.ip_val.setReadOnly(True)
        self.ip_val.setFixedHeight(30)
        self.ip_val.setStyleSheet("padding-left: 10px; font-family: monospace; color: black; background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px;")
        info_layout.addWidget(self.ip_val, 0, 1)
        btn_copy_ip = QPushButton("Copy")
        btn_copy_ip.setFixedWidth(60)
        btn_copy_ip.setFixedHeight(30)
        btn_copy_ip.clicked.connect(lambda: QApplication.clipboard().setText(self.ip_val.text()))
        info_layout.addWidget(btn_copy_ip, 0, 2)

        # Password Field
        info_layout.addWidget(QLabel("Password:"), 1, 0)
        self.pwd_val = QLineEdit(self.server.password)
        self.pwd_val.setReadOnly(True)
        self.pwd_val.setFixedHeight(30)
        self.pwd_val.setStyleSheet("padding-left: 10px; font-family: monospace; color: black; background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px;")
        info_layout.addWidget(self.pwd_val, 1, 1)
        btn_copy_pwd = QPushButton("Copy")
        btn_copy_pwd.setFixedWidth(60)
        btn_copy_pwd.setFixedHeight(30)
        btn_copy_pwd.clicked.connect(lambda: QApplication.clipboard().setText(self.pwd_val.text()))
        info_layout.addWidget(btn_copy_pwd, 1, 2)

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        # Connection History Header
        h_layout = QHBoxLayout()
        h_layout.addWidget(QLabel("<b>Connection History:</b>"), 0, Qt.AlignVCenter)
        h_layout.addStretch()
        
        # Right side button stack
        btn_side_layout = QVBoxLayout()
        btn_side_layout.setSpacing(4)
        
        btn_open_logs = QPushButton("📂 OPEN LOGS FOLDER")
        btn_open_logs.setFixedWidth(150)
        btn_open_logs.setStyleSheet("font-size: 10px; background-color: #f3f4f6; border: 1px solid #d1d5db; border-radius: 4px; padding: 3px;")
        btn_open_logs.setCursor(Qt.PointingHandCursor)
        btn_open_logs.clicked.connect(self.open_log_dir)
        btn_side_layout.addWidget(btn_open_logs)

        btn_clear = QPushButton("🗑️ CLEAR HISTORY")
        btn_clear.setFixedWidth(150)
        btn_clear.setStyleSheet("font-size: 10px; color: #e74c3c; background-color: #fff5f5; border: 1px solid #ffc9c9; border-radius: 4px; padding: 3px;")
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.clicked.connect(self.clear_history)
        btn_side_layout.addWidget(btn_clear)
        
        h_layout.addLayout(btn_side_layout)
        layout.addLayout(h_layout)

        # Table
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Time", "Client IP", "Status", "Log File"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet("background-color: white; border: 1px solid #dcdde1; border-radius: 4px;")
        layout.addWidget(self.table)

        # Footer
        footer_layout = QHBoxLayout()
        footer_layout.addStretch() 
        self.btn_toggle = QPushButton("START SERVER")
        self.btn_toggle.setFixedSize(180, 40)
        self.btn_toggle.setCursor(Qt.PointingHandCursor)
        self.btn_toggle.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; font-size: 14px; border-radius: 5px;")
        self.btn_toggle.clicked.connect(self.toggle_server)
        footer_layout.addWidget(self.btn_toggle)
        layout.addLayout(footer_layout)

        # Persistence and tracking
        self.history_data = [] 
        self.load_history()
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(1000)

    def load_history(self):
        if self.history_path.exists():
            try:
                with open(self.history_path, 'r') as f:
                    self.history_data = json.load(f)
                self.refresh_table_from_data()
            except: pass

    def save_history(self):
        try:
            with open(self.history_path, 'w') as f:
                json.dump(self.history_data, f)
        except: pass

    def clear_history(self):
        if QMessageBox.question(self, "Confirm", "Delete all connection history and physical log files?") == QMessageBox.Yes:
            # 1. Clear physical log files
            try:
                for log_file in self.server.log_dir.glob("*.txt"):
                    try: log_file.unlink()
                    except: pass
            except: pass
            
            # 2. Clear UI data and persistence
            self.history_data = []
            self.table.setRowCount(0)
            self.save_history()
            QMessageBox.information(self, "Success", "History and log files have been cleared.")

    def open_log_file(self, path):
        try:
            if sys.platform == "win32": os.startfile(path)
            else: subprocess.run(["xdg-open", str(path)])
        except: pass

    def open_log_dir(self):
        try:
            if sys.platform == "win32": os.startfile(self.server.log_dir)
            else: subprocess.run(["xdg-open", str(self.server.log_dir)])
        except: pass

    def toggle_server(self):
        if not self.server.running:
            self.server.start()
            self.btn_toggle.setText("STOP SERVER")
            self.btn_toggle.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold; font-size: 14px; border-radius: 5px;")
            self.title_label.setText("SERVER STATUS: ONLINE")
            self.title_label.setStyleSheet("color: #27ae60; font-weight: bold; font-size: 20px;")
        else:
            if QMessageBox.question(self, "Confirm", "Stop server and disconnect all clients?") == QMessageBox.Yes:
                self.server.stop()
                self.btn_toggle.setText("START SERVER")
                self.btn_toggle.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; font-size: 14px; border-radius: 5px;")
                self.title_label.setText("SERVER STATUS: OFFLINE")
                self.title_label.setStyleSheet("color: #e74c3c; font-weight: bold; font-size: 20px;")

    def refresh_table_from_data(self):
        display_map = {}
        for entry in self.history_data:
            display_map[entry['ip']] = entry
            
        self.table.setRowCount(0)
        sorted_entries = sorted(display_map.values(), key=lambda x: x['time'], reverse=True)
        active_ips = self.server.active_clients

        for item in sorted_entries:
            row = self.table.rowCount(); self.table.insertRow(row)
            
            t_item = QTableWidgetItem(item['time']); t_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, t_item)
            
            ip_item = QTableWidgetItem(item['ip']); ip_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 1, ip_item)
            
            is_active = item['ip'] in active_ips
            s_item = QTableWidgetItem("CONNECTED" if is_active else "DISCONNECTED")
            s_item.setForeground(QColor("#27ae60" if is_active else "#e74c3c"))
            s_item.setFont(QFont("Arial", 9, QFont.Bold)); s_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 2, s_item)
            
            lp = item.get('log_path')
            if lp and os.path.exists(lp):
                btn_box = QWidget(); btn_layout = QHBoxLayout(btn_box); btn_layout.setContentsMargins(5, 2, 5, 2); btn_layout.setAlignment(Qt.AlignCenter)
                btn_log = QPushButton("VIEW LOG"); btn_log.setFixedSize(80, 24); btn_log.setCursor(Qt.PointingHandCursor)
                btn_log.setStyleSheet("background-color: #3498db; color: white; font-size: 10px; border-radius: 2px;")
                btn_log.clicked.connect(lambda _, p=lp: self.open_log_file(p))
                btn_layout.addWidget(btn_log); self.table.setCellWidget(row, 3, btn_box)
            else:
                e_item = QTableWidgetItem("-"); e_item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, 3, e_item)

    def update_ui(self):
        with self.server.client_lock:
            active_data = list(self.server.active_clients_data)
        
        changed = False
        for d in active_data:
            if not any(h.get('log_path') == d['log'] for h in self.history_data):
                self.history_data.append({
                    'time': time.strftime("%Y-%m-%d %H:%M:%S"),
                    'ip': d['ip'],
                    'log_path': d['log']
                })
                changed = True
        
        self.refresh_table_from_data()
        if changed: self.save_history()

    def closeEvent(self, event):
        if self.server.running:
            reply = QMessageBox.question(self, 'Confirm Exit', "Server is still running. Exit anyway?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes: self.server.stop(); event.accept()
            else: event.ignore()
        else: event.accept()
