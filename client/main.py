import sys
import os
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# --- DLL FIX FOR WINDOWS ---
if sys.platform == "win32":
    executable_path = Path(sys.executable).parent
    possible_bin_paths = [
        executable_path / "Lib" / "site-packages" / "PyQt5" / "Qt5" / "bin",
        executable_path.parent / "Lib" / "site-packages" / "PyQt5" / "Qt5" / "bin",
        executable_path / "site-packages" / "PyQt5" / "Qt5" / "bin"
    ]
    for p in possible_bin_paths:
        if p.exists():
            os.add_dll_directory(str(p))
            os.environ["PATH"] = str(p) + os.pathsep + os.environ["PATH"]
            break

# Linux Fix
if sys.platform == "linux":
    os.environ["QT_QPA_PLATFORM"] = "xcb"

import logging
from PyQt5.QtWidgets import QApplication
from client.ui.dashboard import Dashboard

# --- LOGGING CONFIG ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    d = Dashboard()
    d.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
