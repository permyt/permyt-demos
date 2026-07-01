import sys

from django.core.management.base import BaseCommand
from django.db.models import TextChoices


class AppCommand(BaseCommand):
    """
    Base command class with common functionality.
    """

    class LogType(TextChoices):
        ERROR = "error", "Error message"
        SUCCESS = "success", "Success message"
        DEBUG = "debug", "Debug log message"

    LOG_TYPES = LogType

    def handle(self, *args, **options):
        """
        The actual logic of the command. Subclasses must implement
        this method.
        """
        raise NotImplementedError("subclasses of AppCommand must provide a handle() method")

    def confirm(self, message):
        """
        Utility method to ask for user confirmation before executing a command.
        """
        confirmation = input(f"{message} (y/n): ")
        if confirmation.lower() not in ("y", "yes"):
            self.log("Command execution cancelled by user.", log_type=self.LOG_TYPES.ERROR)
            self.exit()

    def log(self, message, log_type=LOG_TYPES.DEBUG):
        """
        Utility method to write log messages to stdout.
        """
        if log_type == self.LOG_TYPES.ERROR:
            self.stderr.write(self.style.ERROR(message))

        elif log_type == self.LOG_TYPES.SUCCESS:
            self.stdout.write(self.style.SUCCESS(message))

        else:
            self.stdout.write(message)

    def exit(self):
        """
        Utility method to exit the command execution.
        """
        sys.exit(0)
