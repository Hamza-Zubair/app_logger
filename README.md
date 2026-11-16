# app_logger

One-line logging setup for Python projects, built on the standard `logging` module:

- **Console**: clean, short lines for users (INFO and above)
- **Log file** (optional): detailed lines for debugging (DEBUG and above), with a clickable `path:line`

```
Console:   2026-11-16 12:00:44 [INFO] ✅ Analysis completed.
Log file:  2026-11-16 12:00:44.897 | INFO     | /home/me/project/run.py:52 | ✅ Analysis completed.
```

No dependencies beyond the Python standard library.

## Install

```bash
pip install git+https://github.com/Hamza-Zubair/app_logger.git
```

Or pin a version in `requirements.txt`, so a project keeps the version it was tested with:

```
app_logger @ git+https://github.com/Hamza-Zubair/app_logger.git@v0.1.0
```

Upgrade later with `pip install --upgrade git+https://github.com/Hamza-Zubair/app_logger.git`.

## Use: single-file script

```python
from app_logger import setup_logger

logger = setup_logger()                    # console only
logger = setup_logger(log_to_file=True)    # console + log file

logger.info("Starting...")
```

## Use: project with several modules (two rules)

**Rule 1: in the script you run, set up once, with your package name:**

```python
# run_analysis.py
from app_logger import setup_logger

logger = setup_logger(name="my_package", log_to_file=True)
```

**Rule 2: in every other module, just this line (no setup):**

```python
# my_package/analysis.py
import logging

logger = logging.getLogger(__name__)   # "my_package.analysis" -> logs into the logger from rule 1
```

Do **not** use `__name__` in rule 1: in the script you run it is always `"__main__"`, so the
modules' logs would not reach your console or file.

## Options

| Parameter     | Default                | Meaning |
|---------------|------------------------|---------|
| `name`        | name of the script run | Logger name. In a package, use the package name (rule 1). |
| `log_to_file` | `False`                | Also write a detailed log file. |
| `file_name`   | `<script>_<timestamp>.log` in the current folder | Where to write the log file. A path like `"logs/run.log"` also works (the folder must exist). |

The log file is overwritten on each run (`mode="w"`), so each run has its own timestamped file.

## Develop

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -v
```

## How it is built

| Class           | Job |
|-----------------|-----|
| `Format`        | holds a pattern + date format |
| `Target` (ABC)  | shared code for every output: validated `level` property, `build()` |
| `ConsoleTarget` | `make_handler()` → console handler |
| `FileTarget`    | `make_handler()` → file handler, timestamped default name |
| `AppLogger`     | attaches any list of targets to a Python logger (no duplicates, old files closed) |
| `setup_logger()`| the one function you call: picks the formats and targets |
