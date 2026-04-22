from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt
from client.core.base import RemoteBase

class SystemApps(RemoteBase, QMainWindow):
    def __init__(self, ip, pwd, controller=None):
        super().__init__(ip, pwd, controller)
        self.setWindowTitle(f"Apps - {ip}"); self.resize(500, 500)
        wid = QWidget(); self.setCentralWidget(wid); layout = QVBoxLayout(wid)
        self.search = QLineEdit(); self.search.setPlaceholderText("Search applications..."); self.search.textChanged.connect(self.filter_list)
        layout.addWidget(self.search)
        self.table = QTableWidget(0, 1); self.table.setHorizontalHeaderLabels(["Application Name"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows); layout.addWidget(self.table)
        btn_layout = QHBoxLayout()
        self.btn_ref = QPushButton("REFRESH"); self.btn_ref.clicked.connect(self.load_apps)
        self.btn_start = QPushButton("START APPLICATION"); self.btn_start.clicked.connect(self.start_app)
        btn_layout.addWidget(self.btn_ref); btn_layout.addWidget(self.btn_start); layout.addLayout(btn_layout)
        self.full_apps = []
        self.load_apps()

    def load_apps(self):
        self.search.clear()
        if self.send_safe_cmd({"type": "LIST_APPS"}):
            data = self.recv_json()
            if data: self.full_apps = data; self.filter_list()

    def filter_list(self):
        self.table.setRowCount(0); txt = self.search.text().lower()
        for app in self.full_apps:
            if not txt or txt in app['name'].lower():
                r = self.table.rowCount(); self.table.insertRow(r)
                item = QTableWidgetItem(app['name']); item.setData(Qt.UserRole, app['exec'])
                self.table.setItem(r, 0, item)

    def start_app(self):
        row = self.table.currentRow()
        if row >= 0:
            name = self.table.item(row, 0).text()
            exe = self.table.item(row, 0).data(Qt.UserRole)
            # Send command silently without any visual feedback in statusBar
            if not self.send_safe_cmd({"type": "START_APP", "exec": exe}):
                QMessageBox.warning(self, "Error", f"Failed to start {name}.")
