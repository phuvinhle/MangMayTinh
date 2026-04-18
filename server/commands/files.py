import struct
import zipfile
from pathlib import Path

from server.core.registry import CommandRegistry, BaseCommand


@CommandRegistry.register("LIST_FILES")
class ListFilesCommand(BaseCommand):
    def execute(self, server, conn, data):
        p = Path(data['path'])
        files = []
        if p.exists() and p.is_dir():
            for item in p.iterdir():
                try:
                    files.append({
                        "name": item.name,
                        "is_dir": item.is_dir(),
                        "size": (
                            item.stat().st_size if not item.is_dir() else 0
                        ),
                    })
                except Exception:
                    continue
        server.send_json(conn, files)


@CommandRegistry.register("DOWNLOAD")
class DownloadCommand(BaseCommand):
    def execute(self, server, conn, data):
        p = Path(data['path'])
        temp_zip = None
        if p.is_dir():
            temp_zip = Path("temp_dl.zip")
            with zipfile.ZipFile(temp_zip, 'w') as z:
                for f in p.rglob('*'):
                    try:
                        z.write(f, f.relative_to(p))
                    except Exception:
                        continue
            p = temp_zip

        if p.is_file():
            sz = p.stat().st_size
            conn.sendall(struct.pack("!Q", sz))
            with open(p, "rb") as f:
                while chunk := f.read(32768):
                    conn.sendall(chunk)
        else:
            conn.sendall(struct.pack("!Q", 0))

        if temp_zip and temp_zip.exists():
            try:
                temp_zip.unlink()
            except Exception:
                pass
