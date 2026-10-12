"""Vars stay in sync (PR 10): every var is documented in SCHEMA.md, used by
something, and globals.yml agrees with the role defaults it overrides."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from agra.constants import ANSIBLE_DIR, PROJECT_ROOT as REPO_ROOT, REMOVED_KEYS

SCHEMA_PATH = REPO_ROOT / "contexts" / "SCHEMA.md"
# contexts/ is not published (PR 12): a clone without it checks everything but SCHEMA sync.
SCHEMA = SCHEMA_PATH.read_text() if SCHEMA_PATH.exists() else ""
needs_schema = pytest.mark.skipif(not SCHEMA_PATH.exists(), reason="contexts/SCHEMA.md is not in this checkout")
GLOBALS = REPO_ROOT / "etc" / "agra" / "globals.yml"
DEFAULT_FILES = sorted(ANSIBLE_DIR.glob("roles/*/defaults/main.yml")) + [ANSIBLE_DIR / "playbooks" / "vars" / "lifecycle.yml"]
CODE_SUFFIXES = {".yml", ".yaml", ".j2", ".py", ".sh"}


def _keys(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def _defined():
    """{var: [files]} for role defaults, lifecycle vars and the globals template."""
    out: dict = {}
    for f in DEFAULT_FILES + [GLOBALS]:
        for k in _keys(f):
            out.setdefault(k, []).append(f)
    return out


def _code_files():
    for root in (ANSIBLE_DIR, REPO_ROOT / "agra"):
        yield from (p for p in root.rglob("*") if p.suffix in CODE_SUFFIXES and "__pycache__" not in p.parts)


CODE = {p: p.read_text() for p in _code_files()}
DEFINED = _defined()
SCHEMA_ROWS = set(re.findall(r"^\|\s*`([a-z_][a-z0-9_]*)`", SCHEMA, re.M))


def _is_definition(path: Path, line: str, key: str) -> bool:
    return path in DEFINED.get(key, []) and re.match(rf"\s*{key}\s*:", line) is not None


def _used(key: str) -> bool:
    pattern = re.compile(rf"\b{re.escape(key)}\b")
    for path, text in CODE.items():
        for line in text.splitlines():
            if pattern.search(line) and not _is_definition(path, line, key):
                return True
    return False


@needs_schema
@pytest.mark.parametrize("key", sorted(k for k in DEFINED if not k.startswith("_")))
def test_every_var_has_a_schema_row(key):
    assert key in SCHEMA_ROWS, f"{key} (from {[str(f.relative_to(REPO_ROOT)) for f in DEFINED[key]]}) has no row in contexts/SCHEMA.md"


@pytest.mark.parametrize("key", sorted(DEFINED))
def test_every_defined_var_is_used(key):
    assert _used(key), f"{key} is defined but no task/template/CLI reads it — remove it (and add it to REMOVED_KEYS)"


@pytest.mark.parametrize("key", sorted(SCHEMA_ROWS))
def test_every_schema_row_is_a_live_var(key):
    assert _used(key) or key in DEFINED, f"SCHEMA.md documents {key}, which nothing defines or reads"


def test_globals_template_matches_role_defaults():
    defaults: dict = {}
    for f in DEFAULT_FILES:
        defaults.update(_keys(f))
    drift = {k: (v, defaults[k]) for k, v in _keys(GLOBALS).items() if k in defaults and v != defaults[k]}
    assert drift == {}, f"globals.yml overrides role defaults with different values (globals, default): {drift}"


def _ansible_var_text(path: Path, text: str) -> str:
    """Text where an Ansible var can appear: all of a YAML file (bare `when:`
    expressions), only the Jinja blocks of a template (`server_name` is also
    an nginx directive)."""
    if path.suffix == ".j2":
        return "\n".join(re.findall(r"\{[{%](.*?)[%}]\}", text, re.S))
    return text


@pytest.mark.parametrize("key", sorted(REMOVED_KEYS))
def test_removed_keys_stay_removed(key):
    assert key not in DEFINED, f"{key} is in REMOVED_KEYS but still defined"
    users = [str(p.relative_to(REPO_ROOT)) for p, t in CODE.items()
             if p.suffix != ".py" and re.search(rf"\b{key}\b", _ansible_var_text(p, t))]
    assert users == [], f"{key} is in REMOVED_KEYS but still referenced: {users}"
