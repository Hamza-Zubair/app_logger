"""
Tests for app_logger.py

Run them (from the repository folder) with:   .venv/bin/python -m pytest -v

Each test checks ONE behaviour. If you change app_logger.py, run these again:
if they all pass, you didn't break anything that used to work.

Pytest helpers used here (pytest passes them in automatically by name):
    tmp_path    -> a fresh empty folder, deleted after the test (so no log files pile up)
    monkeypatch -> temporarily change things (like sys.argv or the working directory)
    capsys      -> captures what was printed to the console, so we can check it
"""

import logging
import re
import sys

import pytest

from app_logger import (
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


@pytest.fixture(autouse=True)
def run_in_temp_folder(tmp_path, monkeypatch):
    """Every test runs inside an empty temp folder, so log files never land in your project."""
    monkeypatch.chdir(tmp_path)


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
    # the try_a.py scenario: call 2 crashes, the program carries on
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


def test_setup_logger_name_defaults_to_script_name(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["/anywhere/my_tool.py"])
    logger = setup_logger()
    try:
        assert logger.name == "my_tool"
    finally:
        for h in logger.handlers[:]:
            h.close()
            logger.removeHandler(h)


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


def test_file_line_has_level_path_and_line_number(logger_name, tmp_path):
    logger = setup_logger(name=logger_name, log_to_file=True, file_name="x.log")
    logger.warning("where am I")
    line = (tmp_path / "x.log").read_text().strip()
    # e.g. 2026-11-16 12:00:44.871 | WARNING  | /path/test_app_logger.py:123 | where am I
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3} \| WARNING  \| .*test_app_logger\.py:\d+ \| where am I",
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


def test_multi_module_child_loggers_reach_the_file(logger_name, tmp_path):
    # rule 1: the entry script sets up the parent ONCE
    setup_logger(name=logger_name, log_to_file=True, file_name="x.log")
    # rule 2: another module just asks for a child by its dotted name
    child = get_logger(f"{logger_name}.analysis")
    child.debug("message from a submodule")
    assert "message from a submodule" in (tmp_path / "x.log").read_text()


def test_get_logger_returns_the_same_logger_as_logging(logger_name):
    assert get_logger(logger_name) is logging.getLogger(logger_name)


def test_get_logger_does_not_replace_the_setup(logger_name, tmp_path):
    logger = setup_logger(name=logger_name, log_to_file=True, file_name="x.log")
    handlers_before = list(logger.handlers)
    get_logger(logger_name)  # e.g. a module asking for the SAME name
    get_logger(f"{logger_name}.analysis")  # or a child name
    assert logger.handlers == handlers_before  # no handlers removed, no new file


def test_get_logger_called_before_setup_still_works(logger_name, tmp_path):
    # The usual real-world order: a module does `logger = get_logger(__name__)` at the
    # top of the file, which runs on IMPORT, i.e. before main() calls setup_logger().
    child = get_logger(f"{logger_name}.analysis")
    setup_logger(name=logger_name, log_to_file=True, file_name="x.log")
    child.info("logged after setup")
    assert "logged after setup" in (tmp_path / "x.log").read_text()


def test_get_logger_child_follows_console_and_file_levels(
    logger_name, tmp_path, capsys
):
    setup_logger(name=logger_name, log_to_file=True, file_name="x.log")
    child = get_logger(f"{logger_name}.analysis")
    child.debug("child debug")
    child.info("child info")
    console = capsys.readouterr().err
    file_text = (tmp_path / "x.log").read_text()
    assert "child debug" not in console  # console: INFO and up
    assert "child info" in console
    assert "child debug" in file_text  # file: everything
    assert "child info" in file_text


def test_get_logger_child_line_shows_its_own_file(logger_name, tmp_path):
    setup_logger(name=logger_name, log_to_file=True, file_name="x.log")
    get_logger(f"{logger_name}.analysis").warning("from the child")
    line = (tmp_path / "x.log").read_text().strip()
    assert "test_app_logger.py:" in line  # path:line of the code that logged
    assert line.endswith("| from the child")


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
