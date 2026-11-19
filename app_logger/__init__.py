"""
app_logger — one-line logging setup for Python projects.

- Console: clean, short lines for users (INFO and above by default)
- Log file (optional): detailed lines with path:line (DEBUG and above by default)

Usage, in the script you run:

    from app_logger import setup_logger

    logger = setup_logger(log_to_file=True)
    logger.info("Starting...")

In every other file of your project (no setup there):

    from app_logger import get_logger

    logger = get_logger(__name__)


How it fits together
--------------------
setup_logger(name=None, log_to_file=False, file_name=None,     <- your one line
             console_level="INFO", file_level="DEBUG")
|   all the choices (formats, levels) are made here:
|
+-- short_format = Format(pattern, datefmt, traceback=False)  console: no tracebacks
+-- long_format  = Format(pattern, datefmt)                   file: with tracebacks
|
+-- ConsoleTarget(console_level, short_format)                always
+-- FileTarget(file_level, long_format, file_name)            only if log_to_file
|       no file_name? -> _script_name() + timestamp
|
+-- AppLogger(name, targets).build()
        - each Target.build() makes a handler, tagged "app_logger"
          (traceback=False in its Format -> _NoTracebackFormatter)
        - removes OUR old handlers (tag "app_logger"), never anyone else's
        - attaches the new ones to:
            name=None -> the root logger: every get_logger(__name__) reaches it
            a name    -> that logger only: independent from other setups

get_logger(__name__)                                         <- other files

Format                 a layout: pattern + date format + show tracebacks or not
Target (ABC)           an output: a validated level + a Format, turned into a handler
ConsoleTarget          make_handler() -> console handler
FileTarget             make_handler() -> file handler
_NoTracebackFormatter  writes a line without its traceback (used for the console)
_script_name()         the script's name, for the default log file name
AppLogger              puts the handlers on a logger (root or named), safely
setup_logger()         your choices + puts it all together
get_logger()           a logger for other files
"""

import datetime
import logging
import sys
from abc import ABC, abstractmethod
from pathlib import Path

# every handler app_logger creates gets this name, so it only ever replaces its own
_HANDLER_NAME = "app_logger"


# Script name helper
def _script_name() -> str:
    """
    Name of the script that was run, without folder and ".py" ("log" if there is none).

    :returns: Script name, e.g. "run"
    """
    return Path(sys.argv[0]).stem or "log"


# Log line layout
class Format:
    """
    A log line layout: the pattern, the date format, and whether tracebacks are shown.

    :param pattern: Logging pattern, e.g. "%(asctime)s [%(levelname)s] %(message)s"
    :param datefmt: Date format for %(asctime)s, e.g. "%Y-%m-%d %H:%M:%S"
                    (None = logging's default)
    :param traceback: Show tracebacks of logger.exception(...) (False = message only)
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
        """
        Format the record without its traceback.

        :param record: The log record to format
        :returns: The formatted log line
        """
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
        handler.set_name(_HANDLER_NAME)
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
        Create a new, bare handler of this output's kind.
        Every child class must implement this.

        :returns: Handler without level or format
        """


# Console output
class ConsoleTarget(Target):
    """
    Output to the console (stderr).
    """

    def make_handler(self) -> logging.Handler:
        """
        :returns: Handler that writes to the console (stderr)
        """
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
    :param file_name: File name or path
                      (None = "<script>_<timestamp>.log" in the current folder)
    """

    def __init__(
        self, level: str | int, fmt: Format, file_name: str | Path | None = None
    ) -> None:
        super().__init__(level, fmt)
        if file_name is None:
            file_name = self.default_file_name()
        self.file_name = file_name

    def make_handler(self) -> logging.Handler:
        """
        :returns: Handler that writes to file_name (old content replaced)
        """
        return logging.FileHandler(str(self.file_name), mode="w", encoding="utf-8")

    @staticmethod
    def default_file_name() -> str:
        """
        Name of the script that was run + a timestamp.

        :returns: File name, e.g. "run_2026.11.16_120044.log"
                  ("log_<timestamp>.log" if no script)
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

    :param name: Logger name (None = the root logger, which every logger reports to)
    :param targets: Outputs to attach (None = no outputs)
    """

    def __init__(self, name: str | None, targets: list[Target] | None = None) -> None:
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

        Safe to call more than once: handlers from an earlier build() are replaced,
        so messages are never printed twice. Handlers that app_logger didn't create
        are left alone. If building a new handler fails, the error is raised and the
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

        # Step2: everything worked -> remove OUR old handlers (closes old log files)
        for handler in logger.handlers[:]:
            if handler.get_name() == _HANDLER_NAME:
                handler.close()
                logger.removeHandler(handler)

        # Step3: attach the new ones
        # a named logger doesn't also pass messages up to the root (no duplicates);
        # for the root logger itself this has no effect
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
    console_level: str | int = "INFO",
    file_level: str | int = "DEBUG",
) -> logging.Logger:
    """
    Create the logger: a console (short lines, no tracebacks) and an optional log file
    (path:line, with tracebacks). Call it once, in the script you run.

    :param name: None = one setup on the root logger, used by every get_logger();
                 a name = an independent logger with its own outputs
    :param log_to_file: Also write a log file
    :param file_name: Log file name or path (None = "<script>_<timestamp>.log")
    :param console_level: Minimum level on the console, any casing
    :param file_level: Minimum level in the log file, any casing
    :returns: Configured logging.Logger
    """
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
    targets: list[Target] = [ConsoleTarget(level=console_level, fmt=short_format)]
    if log_to_file:
        targets.append(
            FileTarget(level=file_level, fmt=long_format, file_name=file_name)
        )

    # no name -> the root logger: every file's get_logger(__name__) reports to it
    # a name  -> only that logger: independent from other setups
    return AppLogger(name, targets).build()


# For every other file of your project
def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for another file of your project, e.g. get_logger(__name__).

    No setup needed: it writes to the outputs of setup_logger() (called without a
    name). With setup_logger(name="pkg"), only names under it ("pkg.<...>") do.

    :param name: Logger name, usually __name__
    :returns: Logger with that name
    """
    return logging.getLogger(name)


# Quick manual check: python app_logger/__init__.py
if __name__ == "__main__":
    demo_logger = setup_logger(log_to_file=True)
    demo_logger.debug("debug message")
    demo_logger.info("info message")
    demo_logger.warning("warning message")
    demo_logger.error("error message")
    demo_logger.critical("critical message")
