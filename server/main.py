import threading
import sys
import time
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import server.commands  # noqa: E402 – registers all commands
from server.core.logic import ControlServer  # noqa: E402
from server.ui.server_window import ServerWindow # noqa: E402
from PyQt5.QtWidgets import QApplication

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Start logic
    srv = ControlServer()
    
    # Run loops in threads
    t1 = threading.Thread(target=srv.stream_loop, daemon=True)
    t2 = threading.Thread(target=srv.command_loop, daemon=True)
    t1.start()
    t2.start()

    # Create GUI
    window = ServerWindow(srv)
    window.show()

    # Main thread runs GUI
    sys.exit(app.exec_())
