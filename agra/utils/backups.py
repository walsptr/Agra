"""Backup files on the control node: where they live and how a name maps to them.

`backup.yml` fetches every backup (``<name>.tar.gz`` + ``<name>.yml``) from the
master to ``backup_control_node_dir``; `agra backup list` and `agra restore`
only ever read that directory.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from agra.constants import CONTROL_BACKUP_DIR, GLOBALS_FILE

TARBALL_SUFFIX = ".tar.gz"
MANIFEST_SUFFIXES = (".yml", ".yaml")


def control_backup_dir(override: Optional[str] = None) -> Path:
    """`-d` if given, else backup_control_node_dir from globals.yml, else the default."""
    if override:
        return Path(override).expanduser()
    try:
        import yaml
        with GLOBALS_FILE.open() as fh:
            data = yaml.safe_load(fh) or {}
        value = data.get("backup_control_node_dir") if isinstance(data, dict) else None
        if value:
            return Path(str(value)).expanduser()
    except Exception:
        pass  # unreadable globals is reported by run_playbook, not here
    return CONTROL_BACKUP_DIR


def backup_name(path: Path) -> str:
    """Backup name of a tarball or manifest path (the directory name inside the tarball)."""
    name = path.name
    for suffix in (TARBALL_SUFFIX, *MANIFEST_SUFFIXES):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def manifest_for(path: Path) -> Path:
    """`X.tar.gz` / `X.yml` → `X.yml` (Path.with_suffix would give `X.tar.yml`)."""
    return path.with_name(backup_name(path) + ".yml")


def tarball_for(path: Path) -> Path:
    return path.with_name(backup_name(path) + TARBALL_SUFFIX)


def resolve_manifest(name: str, backup_dir: Path) -> Optional[Path]:
    """Manifest for an exact backup name or path — never a partial match.

    Restore is destructive: `-n 2026` must not pick whichever backup happens to
    contain "2026".
    """
    p = Path(name).expanduser()
    if p.suffix in MANIFEST_SUFFIXES or name.endswith(TARBALL_SUFFIX):
        candidate = p if p.suffix in MANIFEST_SUFFIXES else manifest_for(p)
        if candidate.is_file():
            return candidate
        if not p.is_absolute() and len(p.parts) == 1:
            p = backup_dir / p.name  # bare file name: look in the backup dir
            candidate = p if p.suffix in MANIFEST_SUFFIXES else manifest_for(p)
            return candidate if candidate.is_file() else None
        return None
    for suffix in MANIFEST_SUFFIXES:
        candidate = backup_dir / f"{name}{suffix}"
        if candidate.is_file():
            return candidate
    return None
