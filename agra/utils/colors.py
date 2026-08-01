"""Helper ANSI color & styled output untuk CLI agra."""
from __future__ import annotations
import os
import sys

_NO_COLOR = os.environ.get("NO_COLOR", "") != "" or not sys.stderr.isatty()


def _code(code: str) -> str:
    return "" if _NO_COLOR else f"\033[{code}m"


RESET = _code("0")
BOLD = _code("1")
DIM = _code("2")
RED = _code("31")
GREEN = _code("32")
YELLOW = _code("33")
BLUE = _code("34")
MAGENTA = _code("35")
CYAN = _code("36")
GRAY = _code("90")


def info(msg: str, bold: bool = False) -> None:
    prefix = f"{GREEN}{BOLD if bold else ''}✓{RESET} {GREEN if bold else ''}"
    print(f"{prefix}{msg}{RESET}", flush=True)


def warn(msg: str) -> None:
    prefix = f"{YELLOW}{BOLD}⚠{RESET} {YELLOW}"
    print(f"{prefix}{msg}{RESET}", flush=True, file=sys.stderr)


def error(msg: str) -> None:
    prefix = f"{RED}{BOLD}✗{RESET} {RED}"
    print(f"{prefix}{msg}{RESET}", flush=True, file=sys.stderr)


def debug(msg: str) -> None:
    if os.environ.get("AGRA_DEBUG", "") == "1":
        print(f"{GRAY}DEBUG: {msg}{RESET}", flush=True, file=sys.stderr)


def section(msg: str) -> None:
    print(f"\n{BOLD}{CYAN}═══ {msg} ═══{RESET}", flush=True)
