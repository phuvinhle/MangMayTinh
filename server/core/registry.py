class BaseCommand:
    """Interface for all server commands."""
    def execute(self, server, conn, data):
        raise NotImplementedError

class CommandRegistry:
    """Registry to map command types to their respective classes."""
    _commands = {}

    @classmethod
    def register(cls, cmd_type):
        def decorator(command_class):
            cls._commands[cmd_type] = command_class()
            return command_class
        return decorator

    @classmethod
    def get(cls, cmd_type):
        return cls._commands.get(cmd_type)
