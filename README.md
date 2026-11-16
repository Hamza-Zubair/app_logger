# app_logger

One-line logging setup for Python projects, built on the standard `logging` module.

- **Console**: clean, short lines (INFO and above), no tracebacks
- **Log file** (optional): detailed lines with a clickable `path:line` (DEBUG and above), with tracebacks

```
Console:   2026-11-16 12:00:44 [INFO] ✅ Analysis completed.
Log file:  2026-11-16 12:00:44.897 | INFO     | /home/me/project/run.py:52 | ✅ Analysis completed.
```

Requires Python 3.10+. No dependencies.

## Installation

```bash
pip install git+https://github.com/Hamza-Zubair/app_logger.git@v0.2.1
```

Or in `requirements.txt`:

```
app_logger @ git+https://github.com/Hamza-Zubair/app_logger.git@v0.2.1
```

## Usage

Call `setup_logger()` once, in the script you run:

```python
from app_logger import setup_logger


def main():
    logger = setup_logger(log_to_file=True)

    logger.info("Starting...")
    try:
        run_analysis()
    except Exception as e:
        logger.exception(f"❌ Error: {e}")
```

Errors raised anywhere in your code reach this `except`. The console shows only the message,
the log file also shows the traceback (the file and line where the error happened):

```
Console:   2026-11-16 15:14:16 [ERROR] ❌ Error: Config file not found: x.json
Log file:  2026-11-16 15:14:16.637 | ERROR    | /home/me/project/run.py:79 | ❌ Error: Config file not found: x.json
           Traceback (most recent call last):
             File "/home/me/project/my_package/io.py", line 14, in load_config
           ...
```

### Logging from other modules (optional)

To let another module write its own messages, give the logger your package name and use
`get_logger` in that module:

```python
# the script you run
logger = setup_logger(name="my_package", log_to_file=True)
```

```python
# my_package/analysis.py
from app_logger import get_logger

logger = get_logger(__name__)
logger.info("fitting curves")
```

## Options

| Parameter     | Default                                  | Description |
|---------------|------------------------------------------|-------------|
| `name`        | name of the script you run               | Logger name. Use your package name if other modules use `get_logger`. |
| `log_to_file` | `False`                                  | Also write a log file. |
| `file_name`   | `<script>_<timestamp>.log` in the current folder | Log file name or path. A fixed name is overwritten on each run. |

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
```

## License

MIT
