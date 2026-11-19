# app_logger

One-line logging setup for Python projects: a clean console for your users and a detailed log
file for you. Built on Python's standard `logging` module, no other dependencies.

```
Console:   2026-11-16 12:00:44 [INFO] ✅ Analysis completed.
Log file:  2026-11-16 12:00:44.897 | INFO     | /home/me/project/run.py:52 | ✅ Analysis completed.
```

## Features

- Short lines on the console, detailed lines with a clickable `path:line` in the log file
- Errors: only the message on the console, the full traceback in the log file
- A new log file per run, named after your script: `run_2026.11.16_120044.log`
- Other files of your project just use `get_logger(__name__)`, no setup
- Safe to call more than once: no duplicate lines, other tools' logging left alone
- Type hints included, so editors and mypy can check your calls

Requires Python 3.10+.

## Installation

```bash
pip install git+https://github.com/Hamza-Zubair/app_logger.git@v0.3.0
```

Or in `requirements.txt`: `app_logger @ git+https://github.com/Hamza-Zubair/app_logger.git@v0.3.0`

## Usage

In the script you run, call `setup_logger()` once:

```python
from app_logger import setup_logger


def main():
    logger = setup_logger(log_to_file=True)

    logger.info("Starting...")
    try:
        run_analysis()
    except Exception as e:
        logger.exception(f"❌ Error: {e}")  # console: message only, log file: + traceback
```

In every other file, no setup is needed:

```python
from app_logger import get_logger

logger = get_logger(__name__)
logger.info("fitting curves")
```

## Options

All options of `setup_logger()` are optional:

| Option          | Default                    | What it does                                                              |
| --------------- | -------------------------- | ------------------------------------------------------------------------- |
| `log_to_file`   | `False`                    | Also write a log file.                                                    |
| `file_name`     | `<script>_<timestamp>.log` | Log file name or path. A fixed name is overwritten on each run.           |
| `console_level` | `"INFO"`                   | Lowest level on the console.                                              |
| `file_level`    | `"DEBUG"`                  | Lowest level in the log file.                                             |
| `name`          | `None`                     | Leave it out for one shared setup; give a name for an independent logger. |

Levels, in any casing or as their number: `debug` 10 · `info` 20 · `warning` 30 · `error` 40 · `critical` 50

## Examples

```python
setup_logger(log_to_file=True, console_level="debug")       # debug messages on the console too
setup_logger(log_to_file=True, file_level="warning")        # only warnings and errors in the file
setup_logger(log_to_file=True, file_name="logs/run.log")    # fixed file (the folder must exist)
```

Several independent loggers, each with its own outputs:

```python
screen = setup_logger(name="screen")
report = setup_logger(name="report", log_to_file=True, file_name="report.log")
```

A named logger only receives `get_logger` messages from names under it, e.g. `"report.pdf"`.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
```
