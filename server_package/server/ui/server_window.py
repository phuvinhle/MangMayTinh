import sys
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

class ServerWindow(QMainWindow):
    def __init__(self, server_logic):
        super().__init__()
        self.server = server_logic
        self.setWindowTitle("Server Information")
        self.setFixedSize(400, 400)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header
        title = QLabel("SERVER INFORMATION")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-weight: bold; font-size: 18px;")
        layout.addWidget(title)
        layout.addSpacing(10)

        # Info Box
        info_group = QGroupBox("Details")
        info_layout = QGridLayout()
        
        # IP Row
        info_layout.addWidget(QLabel("Local IP:"), 0, 0)
        self.ip_edit = QLineEdit(self.server.get_local_ip())
        self.ip_edit.setReadOnly(True)
        self.ip_edit.setStyleSheet("font-weight: normal; color: black; background: transparent; border: none;")
        btn_copy_ip = QPushButton("Copy")
        btn_copy_ip.setFixedWidth(50)
        btn_copy_ip.clicked.connect(lambda: QApplication.clipboard().setText(self.ip_edit.text()))
        info_layout.addWidget(self.ip_edit, 0, 1)
        info_layout.addWidget(btn_copy_ip, 0, 2)

        # Password Row
        info_layout.addWidget(QLabel("Password:"), 1, 0)
        self.pwd_edit = QLineEdit(self.server.password)
        self.pwd_edit.setReadOnly(True)
        self.pwd_edit.setStyleSheet("font-weight: normal; color: black; background: transparent; border: none;")
        btn_copy_pwd = QPushButton("Copy")
        btn_copy_pwd.setFixedWidth(50)
        btn_copy_pwd.clicked.connect(lambda: QApplication.clipboard().setText(self.pwd_edit.text()))
        info_layout.addWidget(self.pwd_edit, 1, 1)
        info_layout.addWidget(btn_copy_pwd, 1, 2)

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        # Connected Clients List
        layout.addWidget(QLabel("<b>Connected Clients:</b>"))
        self.client_list = QListWidget()
        self.client_list.setStyleSheet("background-color: #f9f9f9; border-radius: 5px;")
        layout.addWidget(self.client_list)
        layout.addSpacing(10)

        # Stop Button
        self.btn_stop = QPushButton("STOP SERVER")
        self.btn_stop.setFixedHeight(40)
        self.btn_stop.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c; 
                color: white; 
                font-weight: bold; 
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        self.btn_stop.clicked.connect(self.close)
        layout.addWidget(self.btn_stop)

        # Timer to update client list
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(1000)

    def update_ui(self):
        with self.server.client_lock:
            # Show unique IPs only
            clients = sorted(list(set(self.server.active_clients)))
        
        # Update list only if changed
        current_items = [self.client_list.item(i).text() for i in range(self.client_list.count())]
        if clients != current_items:
            self.client_list.clear()
            for c in clients:
                item = QListWidgetItem(c)
                item.setForeground(Qt.black)
                self.client_list.addItem(item)

    def closeEvent(self, event):
        reply = QMessageBox.question(self, 'Confirm Exit',
                                   "Stopping the server will disconnect all clients. Continue?",
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            self.server.stop()
            event.accept()
        else:
            event.ignore()
