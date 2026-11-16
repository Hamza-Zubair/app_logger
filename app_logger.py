from abc import ABC, abstractmethod
from pathlib import Path
import datetime
import logging
import sys


class Format:
    def __init__(self, pattern, datefmt):
        self.pattern = pattern
        self.datefmt = datefmt


class Target(ABC):
    def __init__(self, level, fmt):
        self.level = level
        self.fmt = fmt

    @property
    def level(self):
        return self._level

    @level.setter
    def level(self, value):
        # looging code translation
        if isinstance(value, int):
            value = logging.getLevelName(value)
        # error handler for non-string values
        if not isinstance(value, str):  # 10.5, None, [1, 2]...
            raise TypeError(
                f"Level must be a string like 'info', got {type(value).__name__}"
            )
        # convert to uppercase and validate
        level = value.upper()
        if level not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            raise ValueError(f"Invalid log level: {level}")
        self._level = level

    def build(self):
        handler = self.make_handler()
        handler.setLevel(self.level)
        handler.setFormatter(
            logging.Formatter(self.fmt.pattern, datefmt=self.fmt.datefmt)
        )
        return handler

    @abstractmethod
    def make_handler(self):  # inheritance-based polymorphism instead of duck typing
        pass


class ConsoleTarget(Target):
    def make_handler(self):
        return logging.StreamHandler()

    def __repr__(self):
        return f"ConsoleTarget(level={self.level}, pattern={self.fmt.pattern})"


class FileTarget(Target):
    def __init__(self, level, fmt, file_name=None):
        super().__init__(level, fmt)
        if file_name is None:
            file_name = self.default_file_name()
        self.file_name = file_name

    def make_handler(self):
        return logging.FileHandler(str(self.file_name), mode="w", encoding="utf-8")

    @staticmethod
    def default_file_name():
        script = Path(sys.argv[0]).stem or "log"  # name of the script you ran
        timestamp = datetime.datetime.now().strftime("%Y.%m.%d_%H%M%S")
        return f"{script}_{timestamp}.log"

    def __repr__(self):
        return f"FileTarget(level={self.level}, pattern={self.fmt.pattern}, file_name={self.file_name})"


class AppLogger:
    def __init__(self, name, targets=None):
        self.name = name
        if targets is None:
            targets = []
        self.targets = targets  # a list of target OBJECTS

    def add_target(self, target):
        self.targets.append(target)  # hand in one more target later

    def get_logger(self):
        logger = logging.getLogger(self.name)
        logger.propagate = False
        for handler in logger.handlers[:]:
            handler.close()  # releases the log file
            logger.removeHandler(handler)

        logger.setLevel(logging.DEBUG)
        for target in self.targets:  # works for ANY kind of Target
            logger.addHandler(target.build())  # each target builds its own handler
        return logger


def setup_logger(name=None, log_to_file=False, file_name=None):
    # no name given -> use the name of the script you ran (fine for single-file scripts)
    # multi-file package -> pass the package name, e.g. setup_logger(name="drc_timepoint")
    if name is None:
        name = Path(sys.argv[0]).stem or "log"

    short_format = Format(
        pattern="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    long_format = Format(
        pattern="%(asctime)s.%(msecs)03d | %(levelname)-8s | %(pathname)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    targets = [ConsoleTarget(level="info", fmt=short_format)]

    # the file is OPTIONAL -> only add it to the list if asked
    if log_to_file:
        targets.append(FileTarget(level="debug", fmt=long_format, file_name=file_name))

    # one place that builds the logger, whatever is in the list
    return AppLogger(name, targets).get_logger()


if __name__ == "__main__":
    my_logger = setup_logger(log_to_file=True)
    my_logger.debug("debug message")
    my_logger.info("info message")
    my_logger.warning("warning message")
    my_logger.error("error message")
    my_logger.critical("critical message")

    def load_data():  # a test function, to see a log line from inside a function
        my_logger.warning("could not find column 'dose'")

    load_data()
