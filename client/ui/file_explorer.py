import socket
import struct
from pathlib import Path
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt, QTimer
from client.core.base import RemoteBase
from client.core.network import recv_all

class FileExplorer(RemoteBase, QMainWindow):
    def __init__(self, ip, pwd, controller=None):
        super().__init__(ip, pwd, controller)
        self.setWindowTitle(f"Files - {ip}"); self.resize(800, 600)
        wid = QWidget(); self.setCentralWidget(wid); layout = QVBoxLayout(wid)
        
        self.current_dir = "/" # Standard root
        
        # Navigation row (Path bar with Enter and Auto-load)
        nav_layout = QHBoxLayout()
        self.path = QLineEdit(self.current_dir)
        self.path.setPlaceholderText("Enter server path (Auto-loads in 0.7s)...")
        self.path.returnPressed.connect(self.load)
        self.path.textChanged.connect(self.on_path_changed) 
        
        self.btn_home = QPushButton("HOME")
        self.btn_home.setFixedWidth(80); self.btn_home.clicked.connect(self.go_home)
        
        nav_layout.addWidget(QLabel("<b>Path:</b>"))
        nav_layout.addWidget(self.path); nav_layout.addWidget(self.btn_home)
        layout.addLayout(nav_layout)
        
        # Debounce timer for auto-loading path while typing
        self.nav_timer = QTimer(self)
        self.nav_timer.setSingleShot(True)
        self.nav_timer.timeout.connect(self.load)

        # Filter row (Local Search)
        search_layout = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText("Search in current view...")
        self.search.textChanged.connect(self.local_filter)
        self.btn_refresh = QPushButton("REFRESH"); self.btn_refresh.setFixedWidth(80); self.btn_refresh.clicked.connect(self.load)
        search_layout.addWidget(QLabel("Filter:"))
        search_layout.addWidget(self.search); search_layout.addWidget(self.btn_refresh)
        layout.addLayout(search_layout)

        self.table = QTableWidget(0, 3); self.table.setHorizontalHeaderLabels(["Name", "Type", "Size"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows); self.table.setSortingEnabled(True)
        self.table.itemDoubleClicked.connect(self.dive)
        self.table.itemClicked.connect(self.sync_path_on_click)
        layout.addWidget(self.table)
        
        btn = QPushButton("DOWNLOAD"); btn.setFixedHeight(40); btn.clicked.connect(self.download); layout.addWidget(btn)
        
        self.full_data = [] 
        QTimer.singleShot(100, self.load)

    def on_path_changed(self):
        """Handle path text changes: filter locally and prepare for auto-load."""
        self.local_filter()
        # Restart debounce timer (700ms) to trigger a full load from server
        if self.path.text().strip():
            self.nav_timer.start(700)

    def go_home(self):
        self.path.setText("/")
        self.load()

    def sync_path_on_click(self, item):
        name = self.table.item(item.row(), 0).text()
        if name == "..": return
        separator = "\\" if "\\" in self.current_dir else "/"
        new_path = self.current_dir.rstrip(separator) + separator + name
        self.path.blockSignals(True)
        self.path.setText(new_path)
        self.path.blockSignals(False)

    def local_filter(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        if self.current_dir != "/":
            r = self.table.rowCount(); self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem("..")); self.table.setItem(r, 1, QTableWidgetItem("Folder"))
        txt = self.search.text().lower()
        path_txt = self.path.text()
        if not txt and path_txt.startswith(self.current_dir):
            tail = path_txt[len(self.current_dir):].lstrip("/\\").lower()
            if tail: txt = tail
        for f in self.full_data:
            if not txt or txt in f['name'].lower():
                r = self.table.rowCount(); self.table.insertRow(r)
                self.table.setItem(r, 0, QTableWidgetItem(f['name']))
                self.table.setItem(r, 1, QTableWidgetItem("Folder" if f['is_dir'] else "File"))
                self.table.setItem(r, 2, QTableWidgetItem(str(f['size'])))
        self.table.setSortingEnabled(True)

    def load(self):
        self.nav_timer.stop() # Cancel any pending auto-load if manual load triggered
        self.search.clear()
        target_path = self.path.text()
        if self.send_safe_cmd({"type": "LIST_FILES", "path": target_path}):
            data = self.recv_json()
            if data is not None:
                self.current_dir = target_path
                self.full_data = data
                self.local_filter()

    def dive(self, item):
        name = self.table.item(item.row(), 0).text()
        separator = "\\" if "\\" in self.current_dir else "/"
        if name == "..": 
            parts = self.current_dir.rstrip(separator).split(separator)
            if len(parts) > 1: new_path = separator.join(parts[:-1])
            else: new_path = separator
            if not new_path: new_path = separator
            self.path.setText(new_path)
        else: 
            self.path.setText(self.current_dir.rstrip(separator) + separator + name)
        self.load()

    def download(self):
        row = self.table.currentRow()
        if row < 0: return
        name = self.table.item(row, 0).text()
        full_path = str(Path(self.path.text())/name)
        if self.send_safe_cmd({"type": "DOWNLOAD", "path": full_path}):
            h = recv_all(self.cmd_s, 8)
            if not h: return
            sz = struct.unpack("!Q", h)[0]
            if sz > 0:
                lp, _ = QFileDialog.getSaveFileName(self, "Save File", name if "." in name else name+".zip")
                if lp:
                    progress = QProgressDialog(f"Downloading {name}...", "Cancel", 0, 100, self)
                    progress.setWindowModality(Qt.WindowModal); progress.show()
                    old_timeout = self.cmd_s.gettimeout(); self.cmd_s.settimeout(0.1)
                    try:
                        with open(lp, "wb") as f:
                            rem = sz
                            while rem > 0:
                                if progress.wasCanceled(): break
                                try:
                                    chunk = self.cmd_s.recv(min(rem, 65536))
                                    if not chunk: break
                                    f.write(chunk); rem -= len(chunk); progress.setValue(int((sz - rem) * 100 / sz))
                                except socket.timeout: pass
                                QApplication.processEvents()
                        if not progress.wasCanceled(): QMessageBox.information(self, "Done", "Download Completed")
                    finally: self.cmd_s.settimeout(old_timeout); progress.close()
            else: QMessageBox.warning(self, "Error", "File not found or empty.")
