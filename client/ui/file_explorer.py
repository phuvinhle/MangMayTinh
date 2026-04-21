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
        
        # Navigation row
        nav_layout = QHBoxLayout()
        self.path = QLineEdit("/"); self.path.textChanged.connect(self.start_path_timer)
        self.btn_home = QPushButton("HOME"); self.btn_home.setFixedWidth(80); self.btn_home.clicked.connect(self.go_home)
        self.btn_refresh = QPushButton("REFRESH"); self.btn_refresh.setFixedWidth(80); self.btn_refresh.clicked.connect(self.load)
        nav_layout.addWidget(self.path); nav_layout.addWidget(self.btn_home); nav_layout.addWidget(self.btn_refresh)
        layout.addLayout(nav_layout)
        
        # Search row
        search_layout = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText("Filter files/folders in current directory...")
        self.search.textChanged.connect(self.local_filter)
        self.btn_clear_filter = QPushButton("RESET"); self.btn_clear_filter.setFixedWidth(80); self.btn_clear_filter.clicked.connect(self.search.clear)
        search_layout.addWidget(self.search); search_layout.addWidget(self.btn_clear_filter)
        layout.addLayout(search_layout)

        self.table = QTableWidget(0, 3); self.table.setHorizontalHeaderLabels(["Name", "Type", "Size"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows); self.table.setSortingEnabled(True)
        self.table.itemDoubleClicked.connect(self.dive); layout.addWidget(self.table)
        
        btn = QPushButton("DOWNLOAD"); btn.setFixedHeight(40); btn.clicked.connect(self.download); layout.addWidget(btn)
        
        self.full_data = [] # Cache for local filtering
        self.path_timer = QTimer(); self.path_timer.setSingleShot(True); self.path_timer.timeout.connect(self.load)
        QTimer.singleShot(100, self.load)

    def start_path_timer(self):
        """Auto-load after typing with 700ms debounce."""
        self.path_timer.stop(); self.path_timer.start(700)

    def go_home(self):
        self.path.setText("/"); self.load()

    def local_filter(self):
        """Filter current directory listing instantly."""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        
        # Always add the ".." back-navigation entry if not at root
        curr_text = self.path.text()
        if curr_text and curr_text != "/" and curr_text != "\\":
            try:
                curr_path = Path(curr_text)
                if curr_path != curr_path.parent:
                    r = self.table.rowCount(); self.table.insertRow(r)
                    self.table.setItem(r, 0, QTableWidgetItem("..")); self.table.setItem(r, 1, QTableWidgetItem("Folder"))
            except: pass

        txt = self.search.text().lower()
        for f in self.full_data:
            if not txt or txt in f['name'].lower():
                r = self.table.rowCount(); self.table.insertRow(r)
                self.table.setItem(r, 0, QTableWidgetItem(f['name']))
                self.table.setItem(r, 1, QTableWidgetItem("Folder" if f['is_dir'] else "File"))
                self.table.setItem(r, 2, QTableWidgetItem(str(f['size'])))
        self.table.setSortingEnabled(True)

    def load(self):
        self.path_timer.stop() # Stop timer if manual load is called
        self.send_safe_cmd({"type": "LIST_FILES", "path": self.path.text()})
        data = self.recv_json()
        if data is not None:
            self.full_data = data
            self.local_filter()

    def dive(self, item):
        name = self.table.item(item.row(), 0).text()
        curr_text = self.path.text()
        try:
            curr_path = Path(curr_text)
            if name == "..": 
                new_path = curr_path.parent
                if new_path == curr_path: return 
                self.path.setText(str(new_path))
            else: 
                self.path.setText(str(curr_path / name))
            self.load()
        except: pass

    def download(self):
        row = self.table.currentRow()
        if row < 0: return
        name = self.table.item(row, 0).text()
        if name == "..": return
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
                        if not progress.wasCanceled(): 
                            QMessageBox.information(self, "Done", "Download Completed")
                            from client.core.network import open_file; open_file(lp)
                    finally: self.cmd_s.settimeout(old_timeout); progress.close()
            else: QMessageBox.warning(self, "Error", "File not found or empty.")
