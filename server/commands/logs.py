import struct

from server.core.registry import CommandRegistry, BaseCommand


@CommandRegistry.register("GET_LOGS")
class GetLogsCommand(BaseCommand):
    def execute(self, server, conn, data):
        logs = "\n".join(server.activity_logs)
        server.activity_logs.clear()  # Clear after sending
        p = logs.encode('utf-8')
        conn.sendall(struct.pack("!I", len(p)) + p)
