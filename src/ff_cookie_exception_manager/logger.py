import logging
import sys


class RootLogger(logging.Logger):
    class InfoFilter(logging.Filter):
        def filter(self, record):
            return record.levelno < logging.ERROR

    def __init__(self, name, level=logging.INFO):
        super().__init__(name, level)

        # Create handler for stdout with level DEBUG
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setLevel(logging.DEBUG)
        stdout_handler.addFilter(self.InfoFilter())

        # Create handler for stderr with level ERROR
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(logging.ERROR)

        # Create formatter and add it to the handlers
        formatter = logging.Formatter(
            "%(asctime)s\t%(levelname)s\t%(message)s", datefmt="%Y-%m-%dT%H:%M:%S"
        )
        stdout_handler.setFormatter(formatter)
        stderr_handler.setFormatter(formatter)

        # Add handlers to the logger
        self.addHandler(stdout_handler)
        self.addHandler(stderr_handler)

    def __reduce__(self):
        return logging.getLogger, ()


root = RootLogger("ff-cookie-exceptions-sync")


def setLevel(level):
    root.setLevel(level)


def critical(msg, *args, **kwargs):
    root.critical(msg, *args, **kwargs)


def error(msg, *args, **kwargs):
    root.error(msg, *args, **kwargs)


def exception(msg, *args, exc_info=True, **kwargs):
    error(msg, *args, exc_info=exc_info, **kwargs)


def warning(msg, *args, **kwargs):
    root.warning(msg, *args, **kwargs)


def info(msg, *args, **kwargs):
    root.info(msg, *args, **kwargs)


def debug(msg, *args, **kwargs):
    root.debug(msg, *args, **kwargs)


def log(level, msg, *args, **kwargs):
    root.log(level, msg, *args, **kwargs)


def disable(level=logging.CRITICAL):
    root.manager.disable = level
    root.manager._clear_cache()
