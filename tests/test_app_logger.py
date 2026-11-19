"""
Tests for the app_logger package (app_logger/__init__.py)

Run them (from the repository folder) with:   .venv/bin/python -m pytest -v

Each test checks ONE behaviour. If you change app_logger, run these again:
if they all pass, you didn't break anything that used to work.

Pytest helpers used here (pytest passes them in automatically by name):
    tmp_path    -> a fresh empty folder, deleted after the test (so no log files pile up)
    monkeypatch -> temporarily change things (like sys.argv or the working directory)
    capsys      -> captures what was printed to the console, so we can check it
"""

import logging
import re
import sys
from pathlib import Path

import pytest

from app_logger import (
    _HANDLER_NAME,
    AppLogger,
    ConsoleTarget,
    FileTarget,
    Format,
    Target,
    get_logger,
    setup_logger,
)

# ---------------------------------------------------------------------------
# Shared setup
# ---------------------------------------------------------------------------
SIMPLE = Format("%(levelname)s:%(message)s", None)  # an easy-to-check format


def our_root_handlers():
    """The handlers setup_logger() put on the root logger."""
    return [h for h in logging.getLogger().handlers if h.get_name() == _HANDLER_NAME]


@pytest.fixture(autouse=True)
def run_in_temp_folder(tmp_path, monkeypatch):
    """Every test runs inside an empty temp folder, so log files never land in your project."""
    monkeypatch.chdir(tmp_path)


@pytest.fixture(autouse=True)
def clean_root_logger():
    """setup_logger() configures the root logger, which lives for the whole test run:
    remove its outputs after each test so they can't leak into the next one."""
    root = logging.getLogger()
    old_level = root.level
    yield
    for handler in our_root_handlers():
        handler.close()
        root.removeHandler(handler)
    root.setLevel(old_level)


@pytest.fixture
def logger_name(request):
    """A unique logger name per test, and close its handlers afterwards.

    Python keeps loggers alive for the whole test run (one per name), so without this
    one test's handlers could leak into the next test.
    """
    name = f"test_{request.node.name}"
    yield name
    for handler in logging.getLogger(name).handlers[:]:
        handler.close()
        logging.getLogger(name).removeHandler(handler)


# ---------------------------------------------------------------------------
# Format
# ---------------------------------------------------------------------------
def test_format_stores_pattern_and_datefmt():
    fmt = Format("%(message)s", "%H:%M")
    assert fmt.pattern == "%(message)s"
    assert fmt.datefmt == "%H:%M"
    assert fmt.traceback is True  # default: show tracebacks


def test_format_traceback_can_be_switched_off():
    assert Format("%(message)s", None, traceback=False).traceback is False


# ---------------------------------------------------------------------------
# Target (the abstract parent)
# ---------------------------------------------------------------------------
def test_target_cannot_be_created_directly():
    with pytest.raises(TypeError):
        Target("info", SIMPLE)


def test_child_without_make_handler_cannot_be_created():
    class BrokenTarget(Target):  # forgot to write make_handler()
        pass

    with pytest.raises(TypeError):
        BrokenTarget("info", SIMPLE)


# ---------------------------------------------------------------------------
# The level property (lives in Target, so we test it through ConsoleTarget)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "given, expected",
    [
        ("info", "INFO"),  # lowercase
        ("Info", "INFO"),  # mixed case
        ("DEBUG", "DEBUG"),  # already uppercase
        ("critical", "CRITICAL"),
        (" info ", "INFO"),  # surrounding spaces are stripped
        (logging.WARNING, "WARNING"),  # logging's number form (30)
        (logging.DEBUG, "DEBUG"),  # (10)
    ],
)
def test_level_accepts_valid_values(given, expected):
    assert ConsoleTarget(given, SIMPLE).level == expected


@pytest.mark.parametrize("bad", ["banana", "", "inf o", 15, 999, 0])
def test_level_rejects_invalid_values_with_valueerror(bad):
    with pytest.raises(ValueError, match="Invalid log level"):
        ConsoleTarget(bad, SIMPLE)


@pytest.mark.parametrize("bad", [10.5, None, ["info"], {"level": "info"}])
def test_level_rejects_wrong_types_with_typeerror(bad):
    with pytest.raises(TypeError, match="Level must be a string"):
        ConsoleTarget(bad, SIMPLE)


def test_level_can_be_changed_later():
    target = ConsoleTarget("info", SIMPLE)
    target.level = "error"
    assert target.level == "ERROR"


def test_failed_level_change_keeps_old_value():
    target = ConsoleTarget("info", SIMPLE)
    with pytest.raises(ValueError):
        target.level = "banana"
    assert target.level == "INFO"  # the bad value never got stored


# ---------------------------------------------------------------------------
# ConsoleTarget
# ---------------------------------------------------------------------------
def test_console_target_builds_a_stream_handler_with_level_and_format():
    handler = ConsoleTarget("warning", SIMPLE).build()
    assert type(handler) is logging.StreamHandler
    assert handler.level == logging.WARNING
    assert handler.formatter._fmt == SIMPLE.pattern


# ---------------------------------------------------------------------------
# FileTarget
# ---------------------------------------------------------------------------
def test_file_target_keeps_the_given_file_name():
    assert FileTarget("debug", SIMPLE, "my.log").file_name == "my.log"


def test_default_file_name_uses_script_name_and_timestamp(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["/some/folder/my_script.py"])
    name = FileTarget.default_file_name()
    assert re.fullmatch(r"my_script_\d{4}\.\d{2}\.\d{2}_\d{6}\.log", name), name


def test_default_file_name_falls_back_to_log_without_a_script(monkeypatch):
    monkeypatch.setattr(sys, "argv", [""])  # e.g. the interactive python prompt
    assert FileTarget.default_file_name().startswith("log_")


def test_file_target_without_name_uses_default(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run.py"])
    assert FileTarget("debug", SIMPLE).file_name.startswith("run_")


def test_file_target_builds_a_file_handler_and_creates_the_file(tmp_path):
    handler = FileTarget("debug", SIMPLE, "out.log").build()
    try:
        assert isinstance(handler, logging.FileHandler)
        assert handler.level == logging.DEBUG
        assert (tmp_path / "out.log").exists()  # relative name -> current folder
    finally:
        handler.close()


def test_file_target_accepts_a_full_path(tmp_path):
    full_path = tmp_path / "sub" / "out.log"
    full_path.parent.mkdir()
    handler = FileTarget("debug", SIMPLE, full_path).build()
    handler.close()
    assert full_path.exists()


def test_missing_folder_fails_loudly(tmp_path):
    # we WANT a clear error here, not a silent "no logs"
    with pytest.raises(FileNotFoundError):
        FileTarget("debug", SIMPLE, tmp_path / "does_not_exist" / "out.log").build()


# ---------------------------------------------------------------------------
# AppLogger
# ---------------------------------------------------------------------------
def test_build_returns_a_real_python_logger(logger_name):
    logger = AppLogger(logger_name, [ConsoleTarget("info", SIMPLE)]).build()
    assert isinstance(logger, logging.Logger)
    assert logger.name == logger_name
    assert logger is logging.getLogger(logger_name)  # same object other files will get


def test_logger_lets_everything_through_and_targets_decide(logger_name):
    logger = AppLogger(logger_name, [ConsoleTarget("info", SIMPLE)]).build()
    assert logger.level == logging.DEBUG


def test_logger_does_not_propagate_to_root(logger_name):
    logger = AppLogger(logger_name).build()
    assert logger.propagate is False


def test_no_targets_means_no_handlers(logger_name):
    assert AppLogger(logger_name).build().handlers == []


def test_add_target(logger_name):
    app = AppLogger(logger_name)
    app.add_target(ConsoleTarget("info", SIMPLE))
    assert len(app.build().handlers) == 1


def test_two_applogger_objects_do_not_share_their_targets_list(logger_name):
    a = AppLogger(logger_name)
    b = AppLogger(logger_name)
    a.add_target(ConsoleTarget("info", SIMPLE))
    assert b.targets == []  # the None trick: each object gets its own list


def test_build_twice_does_not_duplicate_handlers(logger_name, capsys):
    app = AppLogger(logger_name, [ConsoleTarget("info", SIMPLE)])
    app.build()
    logger = app.build()
    assert len(logger.handlers) == 1
    logger.info("hello")
    assert capsys.readouterr().err.count("hello") == 1  # printed once, not twice


def test_build_again_closes_the_old_file(logger_name):
    app = AppLogger(logger_name, [FileTarget("debug", SIMPLE, "a.log")])
    old_handler = app.build().handlers[0]
    app.build()
    assert old_handler.stream is None  # None = file was closed


def test_failed_second_setup_keeps_the_first_one_working(logger_name, tmp_path):
    # a second setup_logger() call crashes (missing folder), the program carries on
    logger = setup_logger(name=logger_name, log_to_file=True, file_name="demo.log")
    logger.info("message 1")
    with pytest.raises(FileNotFoundError):  # the error is still shown
        setup_logger(
            name=logger_name, log_to_file=True, file_name="no_such_folder/x.log"
        )
    logger.info("message 2")
    content = (tmp_path / "demo.log").read_text()
    assert "message 1" in content
    assert "message 2" in content  # the old file output survived the failed call


# ---------------------------------------------------------------------------
# setup_logger (what your projects actually call)
# ---------------------------------------------------------------------------
def test_setup_logger_default_is_console_only(logger_name):
    logger = setup_logger(name=logger_name)
    assert len(logger.handlers) == 1
    assert not isinstance(logger.handlers[0], logging.FileHandler)


def test_setup_logger_with_file_has_console_and_file(logger_name):
    logger = setup_logger(name=logger_name, log_to_file=True, file_name="x.log")
    kinds = sorted(type(h).__name__ for h in logger.handlers)
    assert kinds == ["FileHandler", "StreamHandler"]


def test_setup_logger_without_name_sets_up_the_root_logger():
    # like logging.basicConfig(): the root is the top of the tree, every logger reports to it
    logger = setup_logger()
    assert logger is logging.getLogger()
    assert len(our_root_handlers()) == 1


def test_setup_logger_with_name_sets_up_only_that_logger(logger_name):
    logger = setup_logger(name=logger_name)
    assert logger.name == logger_name
    assert len(logger.handlers) == 1
    assert our_root_handlers() == []  # the root is left alone


def test_setup_logger_leaves_other_root_handlers_alone():
    # e.g. handlers added by Jupyter or pytest: only app_logger's own get replaced
    foreign = logging.NullHandler()
    logging.getLogger().addHandler(foreign)
    try:
        setup_logger()
        setup_logger()
        assert foreign in logging.getLogger().handlers
        assert len(our_root_handlers()) == 1
    finally:
        logging.getLogger().removeHandler(foreign)


def test_two_named_loggers_are_independent(tmp_path, capsys):
    # one console-only logger and one console + file logger in the same program
    logger1 = setup_logger(name="test_abc", log_to_file=False)
    logger2 = setup_logger(name="test_xyz", log_to_file=True, file_name="xyz.log")
    try:
        logger1.info("from logger1")
        logger2.info("from logger2")
        console = capsys.readouterr().err
        file_text = (tmp_path / "xyz.log").read_text()
        assert console.count("from logger1") == 1
        assert console.count("from logger2") == 1
        assert "from logger1" not in file_text  # logger1 has no file
        assert "from logger2" in file_text
    finally:
        for logger in (logger1, logger2):
            for handler in logger.handlers[:]:
                handler.close()
                logger.removeHandler(handler)


def test_named_and_unnamed_setup_together_do_not_duplicate(logger_name, capsys):
    setup_logger()  # root
    logger = setup_logger(name=logger_name)  # an independent named logger
    logger.info("once")
    assert capsys.readouterr().err.count("once") == 1


def test_console_shows_info_and_up_but_not_debug(logger_name, capsys):
    logger = setup_logger(name=logger_name)
    logger.debug("secret debug")
    logger.info("visible info")
    logger.error("visible error")
    console = capsys.readouterr().err
    assert "secret debug" not in console
    assert "[INFO] visible info" in console
    assert "[ERROR] visible error" in console


def test_file_gets_everything_including_debug(logger_name, tmp_path):
    logger = setup_logger(name=logger_name, log_to_file=True, file_name="x.log")
    logger.debug("debug line")
    logger.info("info line")
    content = (tmp_path / "x.log").read_text()
    assert "debug line" in content
    assert "info line" in content


def test_console_level_can_be_changed(logger_name, capsys):
    logger = setup_logger(name=logger_name, console_level="debug")
    logger.debug("debug on the console")
    assert "[DEBUG] debug on the console" in capsys.readouterr().err


def test_file_level_can_be_changed(logger_name, tmp_path):
    logger = setup_logger(
        name=logger_name, log_to_file=True, file_name="x.log", file_level="warning"
    )
    logger.info("info line")
    logger.warning("warning line")
    content = (tmp_path / "x.log").read_text()
    assert "info line" not in content
    assert "warning line" in content


def test_levels_accept_logging_numbers(logger_name, capsys):
    logger = setup_logger(name=logger_name, console_level=logging.DEBUG)
    logger.debug("number level")
    assert "number level" in capsys.readouterr().err


@pytest.mark.parametrize("bad", ["dbug", "", 15])
def test_bad_level_is_rejected_with_a_clear_error(logger_name, bad):
    with pytest.raises(ValueError, match="Invalid log level"):
        setup_logger(name=logger_name, console_level=bad)


def test_file_line_has_level_path_and_line_number(logger_name, tmp_path):
    logger = setup_logger(name=logger_name, log_to_file=True, file_name="x.log")
    logger.warning("where am I")
    line = (tmp_path / "x.log").read_text().strip()
    # e.g. 2026-11-16 12:00:44.871 | WARNING  | /path/test_app_logger.py:123 | where am I
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3} \| WARNING  \| "
        r".*test_app_logger\.py:\d+ \| where am I",
        line,
    ), line


def test_file_is_overwritten_on_each_run(logger_name, tmp_path):
    (tmp_path / "x.log").write_text("OLD RUN\n")
    logger = setup_logger(name=logger_name, log_to_file=True, file_name="x.log")
    logger.info("new run")
    content = (tmp_path / "x.log").read_text()
    assert "OLD RUN" not in content
    assert "new run" in content


def test_unicode_and_emoji_are_written_to_file(logger_name, tmp_path):
    logger = setup_logger(name=logger_name, log_to_file=True, file_name="x.log")
    logger.info("✅ Success: µM dose")
    assert "✅ Success: µM dose" in (tmp_path / "x.log").read_text(encoding="utf-8")


def test_calling_setup_logger_twice_does_not_duplicate(logger_name, capsys):
    setup_logger(name=logger_name)
    logger = setup_logger(name=logger_name)
    logger.info("once")
    assert capsys.readouterr().err.count("once") == 1


def test_logging_error_does_not_crash_the_program(logger_name, capsys):
    # bad %-formatting inside a message: logging reports it, but the program keeps going
    logger = setup_logger(name=logger_name)
    logger.info("broken %d", "not a number")
    logger.info("still running")
    assert "still running" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Other files: get_logger(__name__)
# (no name in setup_logger + a module's own name was the case broken in v0.2.x)
# ---------------------------------------------------------------------------
# a name that has nothing to do with setup_logger's name, like a real module's __name__
MODULE = "some_package.analysis"


def test_module_logger_reaches_console_and_file_without_a_setup_name(tmp_path, capsys):
    setup_logger(log_to_file=True, file_name="x.log")  # no name, like a real script
    get_logger(MODULE).info("message from a module")
    assert "[INFO] message from a module" in capsys.readouterr().err
    assert "message from a module" in (tmp_path / "x.log").read_text()


def test_module_logger_created_before_setup_still_works(tmp_path):
    # the usual order: `logger = get_logger(__name__)` at the top of a module
    # runs on IMPORT, i.e. before main() calls setup_logger()
    module_logger = get_logger(MODULE)
    setup_logger(log_to_file=True, file_name="x.log")
    module_logger.info("logged after setup")
    assert "logged after setup" in (tmp_path / "x.log").read_text()


def test_module_logger_follows_console_and_file_levels(tmp_path, capsys):
    setup_logger(log_to_file=True, file_name="x.log")
    module_logger = get_logger(MODULE)
    module_logger.debug("module debug")
    module_logger.info("module info")
    console = capsys.readouterr().err
    file_text = (tmp_path / "x.log").read_text()
    assert "module debug" not in console  # console: INFO and up
    assert "module info" in console
    assert "module debug" in file_text  # file: everything
    assert "module info" in file_text


def test_module_logger_line_shows_its_own_file(tmp_path):
    setup_logger(log_to_file=True, file_name="x.log")
    get_logger(MODULE).warning("from the module")
    line = (tmp_path / "x.log").read_text().strip()
    assert "test_app_logger.py:" in line  # path:line of the code that logged
    assert line.endswith("| from the module")


def test_named_setup_reaches_only_modules_under_its_name(logger_name, tmp_path):
    setup_logger(name=logger_name, log_to_file=True, file_name="x.log")
    get_logger(f"{logger_name}.analysis").info("from a module under the name")
    get_logger(MODULE).info("from an unrelated module")
    file_text = (tmp_path / "x.log").read_text()
    assert "from a module under the name" in file_text
    assert "from an unrelated module" not in file_text


def test_pytest_caplog_sees_messages_of_the_unnamed_setup(caplog):
    # caplog listens on the root logger, so it sees the unnamed (root) setup
    setup_logger().warning("checked by caplog")
    get_logger(MODULE).warning("module, checked by caplog")
    assert "checked by caplog" in caplog.text
    assert "module, checked by caplog" in caplog.text


def test_get_logger_is_the_same_as_pythons_logger_with_that_name():
    assert get_logger(MODULE) is logging.getLogger(MODULE)


# ---------------------------------------------------------------------------
# Tracebacks: console = message only, log file = message + traceback
# ---------------------------------------------------------------------------
def _fail_inside_a_function():
    raise FileNotFoundError("Config file not found: x.json")


def test_console_shows_exception_message_without_traceback(logger_name, capsys):
    logger = setup_logger(name=logger_name)
    try:
        _fail_inside_a_function()
    except Exception as e:
        logger.exception(f"❌ Error: {e}")
    console = capsys.readouterr().err
    assert "[ERROR] ❌ Error: Config file not found: x.json" in console
    assert "Traceback" not in console


def test_file_shows_exception_message_with_traceback(logger_name, tmp_path):
    logger = setup_logger(name=logger_name, log_to_file=True, file_name="x.log")
    try:
        _fail_inside_a_function()
    except Exception as e:
        logger.exception(f"❌ Error: {e}")
    content = (tmp_path / "x.log").read_text(encoding="utf-8")
    assert "❌ Error: Config file not found: x.json" in content
    assert "Traceback (most recent call last)" in content
    assert "in _fail_inside_a_function" in content  # WHERE it actually broke


def test_hiding_the_traceback_does_not_depend_on_output_order(logger_name, capsys):
    # file first, console second: the console must still hide it, the file still show it
    file_fmt = Format("%(message)s", None, traceback=True)
    console_fmt = Format("%(message)s", None, traceback=False)
    logger = AppLogger(
        logger_name,
        [FileTarget("debug", file_fmt, "x.log"), ConsoleTarget("info", console_fmt)],
    ).build()
    try:
        _fail_inside_a_function()
    except Exception:
        logger.exception("boom")
    assert "Traceback" not in capsys.readouterr().err
    assert "Traceback" in Path("x.log").read_text(encoding="utf-8")
