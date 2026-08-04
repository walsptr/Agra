"""Resolve project paths & load globals.yaml defaults."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Dict, Any

try:
    import yaml
except ImportError:
    yaml = None

from agra.constants import (
    PROJECT_ROOT, GLOBALS_FILE, PASSWORDS_FILE, DEFAULT_INVENTORY,
    ANSIBLE_DIR, CONFIG_DIR,
)


def resolve_inventory(override: str | None = None) -> Path:
    """Resolve inventory file: CLI override > AGRA_INVENTORY env > DEFAULT_INVENTORY."""
    if override:
        p = Path(override).expanduser()
        if not p.is_absolute():
            p = (PROJECT_ROOT / p).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Inventory file not found: {p}")
        return p

    env_inv = os.environ.get("AGRA_INVENTORY", "")
    if env_inv:
        p = Path(env_inv).expanduser()
        if not p.is_absolute():
            p = (PROJECT_ROOT / p).resolve()
        if p.exists():
            return p

    if DEFAULT_INVENTORY.exists():
        return DEFAULT_INVENTORY
    raise FileNotFoundError(
        f"No inventory found. Set via: -i /path/inventory OR env AGRA_INVENTORY OR create {DEFAULT_INVENTORY}"
    )


def load_globals_yaml() -> Dict[str, Any]:
    """Load globals.yml + passwords.yml secara shallow (untuk info CLI). Playbook Ansible yang pakai vars full."""
    merged: Dict[str, Any] = {}
    for f in [GLOBALS_FILE, PASSWORDS_FILE]:
        if f.exists() and yaml is not None:
            try:
                with f.open("r") as fh:
                    d = yaml.safe_load(fh) or {}
                if isinstance(d, dict):
                    merged.update(d)
            except Exception:
                pass
    return merged


def ansible_env() -> Dict[str, str]:
    """Environment variables untuk subprocess ansible-playbook."""
    env = os.environ.copy()
    env.setdefault("ANSIBLE_ROLES_PATH", str(ANSIBLE_DIR / "roles"))
    env.setdefault("ANSIBLE_CONFIG", str(PROJECT_ROOT / "ansible.cfg"))
    return env
