import socket
import struct
from pathlib import Path
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt
from client.core.base import RemoteBase
from client.core.network import recv_all

class FileExplorer(RemoteBase, QMainWindow):
    def __init__(self, ip, pwd, controller=None):
        super().__init__(ip, pwd, controller)
        self.setWindowTitle(f"Files - {ip}"); self.resize(800, 600)
        wid = QWidget(); self.setCentralWidget(wid); layout = QVBoxLayout(wid)
        
        # Navigation row
        self.path = QLineEdit("/"); layout.addWidget(self.path)
        
        # Search row (New: Consistent with other modules)
        search_layout = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText("Filter files/folders in current directory...")
        self.search.textChanged.connect(self.local_filter)
        self.btn_refresh = QPushButton("REFRESH"); self.btn_refresh.setFixedWidth(80); self.btn_refresh.clicked.connect(self.load)
        search_layout.addWidget(self.search); search_layout.addWidget(self.btn_refresh)
        layout.addLayout(search_layout)

        self.table = QTableWidget(0, 3); self.table.setHorizontalHeaderLabels(["Name", "Type", "Size"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows); self.table.setSortingEnabled(True)
        self.table.itemDoubleClicked.connect(self.dive); layout.addWidget(self.table)
        
        btn = QPushButton("DOWNLOAD"); btn.setFixedHeight(40); btn.clicked.connect(self.download); layout.addWidget(btn)
        
        self.full_data = [] # Cache for local filtering
        self.load()

    def local_filter(self):
        """Filter current directory listing instantly."""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        
        # Always add the ".." back-navigation entry if not at root (cross-platform check)
        curr_path = Path(self.path.text())
        if curr_path != curr_path.parent:
            r = self.table.rowCount(); self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem("..")); self.table.setItem(r, 1, QTableWidgetItem("Folder"))

        txt = self.search.text().lower()
        for f in self.full_data:
            if not txt or txt in f['name'].lower():
                r = self.table.rowCount(); self.table.insertRow(r)
                self.table.setItem(r, 0, QTableWidgetItem(f['name']))
                self.table.setItem(r, 1, QTableWidgetItem("Folder" if f['is_dir'] else "File"))
                self.table.setItem(r, 2, QTableWidgetItem(str(f['size'])))
        self.table.setSortingEnabled(True)

    def load(self):
        self.search.clear() # Clear filter on new directory load
        self.send_safe_cmd({"type": "LIST_FILES", "path": self.path.text()})
        data = self.recv_json()
        if data:
            self.full_data = data
            self.local_filter()

    def dive(self, item):
        name = self.table.item(item.row(), 0).text()
        if name == "..": self.path.setText(str(Path(self.path.text()).parent))
        else: self.path.setText(str(Path(self.path.text()) / name))
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
