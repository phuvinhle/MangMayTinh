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


if __name__ == "__main__":
    server = ControlServer()
    threading.Thread(target=server.stream_loop, daemon=True).start()
    threading.Thread(target=server.command_loop, daemon=True).start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()
        sys.exit(0)
