import time
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from client.core.base import RemoteBase
from client.ui.widgets import NumericItem

class ProcessManager(RemoteBase, QMainWindow):
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

        self.table = QTableWidget(0, 4); self.table.setHorizontalHeaderLabels(["PID", "Name", "CPU %", "RAM %"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents) # PID
        header.setSectionResizeMode(1, QHeaderView.Stretch)          # Name
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents) # CPU
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents) # RAM
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
