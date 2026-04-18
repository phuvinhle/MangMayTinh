from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt
from client.core.base import RemoteBase

class SystemApps(RemoteBase, QMainWindow):
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
