"""
app_logger — one-line logging setup for Python projects.

- Console: clean, short lines for users (INFO and above)
- Log file (optional): detailed lines for debugging (DEBUG and above), with a clickable path:line

Usage, in the script you run:

    from app_logger import setup_logger

    logger = setup_logger(log_to_file=True)
    logger.info("Starting...")
"""

from abc import ABC, abstractmethod
from pathlib import Path
import datetime
import logging
import sys


# Script name helper
def _script_name() -> str:
    """
    Name of the script that was run, without folder and ".py", or "log" if there is none.

    :returns: Script name, e.g. "run"
    """
    return Path(sys.argv[0]).stem or "log"


# Log line layout
class Format:
    """
    A log line layout: the pattern, the date format, and whether tracebacks are shown.

    :param pattern: Logging pattern, e.g. "%(asctime)s [%(levelname)s] %(message)s"
    :param datefmt: Date format for %(asctime)s, e.g. "%Y-%m-%d %H:%M:%S" (None = default)
    :param traceback: Show the traceback of logger.exception(...) calls (False = message only)
    """

    def __init__(
        self, pattern: str, datefmt: str | None, traceback: bool = True
    ) -> None:
        self.pattern = pattern
        self.datefmt = datefmt
        self.traceback = traceback


# Formatter that leaves out tracebacks
class _NoTracebackFormatter(logging.Formatter):
    """
    A logging.Formatter that writes only the log line, never the traceback.
    """

    def format(self, record: logging.LogRecord) -> str:
        # hide the traceback for this one line, then put it back,
        # so other outputs (e.g. the log file) still get it
        saved = (record.exc_info, record.exc_text, record.stack_info)
        record.exc_info, record.exc_text, record.stack_info = None, None, None
        try:
            return super().format(record)
        finally:
            record.exc_info, record.exc_text, record.stack_info = saved


# Base class for every log output
class Target(ABC):
    """
    Base class for every log output (console, file, ...).

    Holds what all outputs share: a validated level and a Format.
    Each child class only has to provide make_handler().

    :param level: Minimum level, e.g. "info" (any casing) or logging.INFO
    :param fmt: Format used for this output's lines
    """

    def __init__(self, level: str | int, fmt: Format) -> None:
        # goes through the level setter below (validated)
        self.level = level
        self.fmt = fmt

    @property
    def level(self) -> str:
        """
        Minimum level of this output, always stored uppercase, e.g. "INFO".
        """
        return self._level

    @level.setter
    def level(self, value: str | int) -> None:
        # Check1: logging's number form (logging.DEBUG == 10) -> its name ("DEBUG")
        if isinstance(value, int):
            value = logging.getLevelName(value)
        # Check2: anything else that isn't text (10.5, None, [1, 2], ...) is rejected
        if not isinstance(value, str):
            raise TypeError(
                f"Level must be a string like 'info', got {type(value).__name__}"
            )
        # Check3: clean it up and make sure it's a real level
        level = value.strip().upper()
        if level not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            raise ValueError(f"Invalid log level: {level}")
        self._level = level

    def build(self) -> logging.Handler:
        """
        Create a ready-to-use handler with this output's level and format.

        :returns: Handler, to be attached to a logger
        """
        handler = self.make_handler()
        handler.setLevel(self.level)
        formatter_class = (
            logging.Formatter if self.fmt.traceback else _NoTracebackFormatter
        )
        handler.setFormatter(
            formatter_class(self.fmt.pattern, datefmt=self.fmt.datefmt)
        )
        return handler

    # inheritance-based polymorphism instead of duck typing
    @abstractmethod
    def make_handler(self) -> logging.Handler:
        """
        Create a new, bare handler of this output's kind. Every child must implement this.

        :returns: Handler without level or format
        """
        pass


# Console output
class ConsoleTarget(Target):
    """
    Output to the console (stderr).
    """

    def make_handler(self) -> logging.Handler:
        return logging.StreamHandler()

    def __repr__(self) -> str:
        return f"ConsoleTarget(level={self.level}, pattern={self.fmt.pattern})"


# Log file output
class FileTarget(Target):
    """
    Output to a log file.

    Default name: a new timestamped file every run.
    Fixed name: the same file every run, its old content is replaced (mode="w").

    :param level: Minimum level for the file
    :param fmt: Format used for the file's lines
    :param file_name: File name or path (None = "<script>_<timestamp>.log" in current folder)
    """

    def __init__(
        self, level: str | int, fmt: Format, file_name: str | Path | None = None
    ) -> None:
        super().__init__(level, fmt)
        if file_name is None:
            file_name = self.default_file_name()
        self.file_name = file_name

    def make_handler(self) -> logging.Handler:
        return logging.FileHandler(str(self.file_name), mode="w", encoding="utf-8")

    @staticmethod
    def default_file_name() -> str:
        """
        Name of the script that was run + a timestamp.

        :returns: File name, e.g. "run_2026.11.16_120044.log" ("log_<timestamp>.log" if no script)
        """
        timestamp = datetime.datetime.now().strftime("%Y.%m.%d_%H%M%S")
        return f"{_script_name()}_{timestamp}.log"

    def __repr__(self) -> str:
        return (
            f"FileTarget(level={self.level}, pattern={self.fmt.pattern}, "
            f"file_name={self.file_name})"
        )


# Puts the outputs together into a Python logger
class AppLogger:
    """
    Attaches any list of targets to a Python logger.

    :param name: Logger name
    :param targets: Outputs to attach (None = no outputs)
    """

    def __init__(self, name: str, targets: list[Target] | None = None) -> None:
        self.name = name
        if targets is None:
            targets = []
        self.targets = targets

    def add_target(self, target: Target) -> None:
        """
        Add one more output. It takes effect on the next build().

        :param target: Output to add
        """
        self.targets.append(target)

    def build(self) -> logging.Logger:
        """
        Set up the Python logger with this object's targets.

        Safe to call more than once: old handlers are replaced, so messages are never
        printed twice. If building a new handler fails, the error is raised and the
        previous setup stays untouched.

        :returns: Configured logging.Logger
        """
        logger = logging.getLogger(self.name)

        # Step1: build ALL new handlers first, so a failure can't break the old setup
        new_handlers = []
        try:
            for target in self.targets:
                new_handlers.append(target.build())
        except Exception:
            # close the ones that did work (e.g. the console), then show the error
            for handler in new_handlers:
                handler.close()
            raise

        # Step2: everything worked -> remove the old handlers (closes old log files)
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)

        # Step3: attach the new ones
        # don't also pass messages to the root logger (would print them twice)
        logger.propagate = False
        # let everything through; each target decides with its own level
        logger.setLevel(logging.DEBUG)
        for handler in new_handlers:
            logger.addHandler(handler)
        return logger


# Main entry: call this once, in the script you run
def setup_logger(
    name: str | None = None,
    log_to_file: bool = False,
    file_name: str | Path | None = None,
) -> logging.Logger:
    """
    Create the logger: console (short format, INFO and above, no tracebacks) and an
    optional log file (detailed format with path:line, DEBUG and above, with tracebacks).

    :param name: Logger name (None = name of the script you ran)
    :param log_to_file: Also write a log file
    :param file_name: Log file name or path (None = "<script>_<timestamp>.log" in current folder)
    :returns: Configured logging.Logger, e.g. logger.info("...")
    """
    if name is None:
        name = _script_name()

    short_format = Format(
        pattern="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        traceback=False,
    )
    long_format = Format(
        pattern=(
            "%(asctime)s.%(msecs)03d | %(levelname)-8s | "
            "%(pathname)s:%(lineno)d | %(message)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # console is always on, the file only if asked
    targets: list[Target] = [ConsoleTarget(level="info", fmt=short_format)]
    if log_to_file:
        targets.append(FileTarget(level="debug", fmt=long_format, file_name=file_name))

    return AppLogger(name, targets).build()


# Optional helper for other modules
def get_logger(name: str) -> logging.Logger:
    """
    Get a logger that writes through the setup_logger() setup. Optional: only needed if
    another module should write its own messages, e.g. logger = get_logger(__name__).

    It does no setup itself, so it never replaces outputs or starts a new log file.

    :param name: Logger name, usually __name__
    :returns: logging.Logger with that name
    """
    return logging.getLogger(name)


# Quick manual check: python app_logger.py
if __name__ == "__main__":
    demo_logger = setup_logger(log_to_file=True)
    demo_logger.debug("debug message")
    demo_logger.info("info message")
    demo_logger.warning("warning message")
    demo_logger.error("error message")
    demo_logger.critical("critical message")
