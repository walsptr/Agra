"""Resolve project paths & load globals.yaml defaults."""
from __future__ import annotations
import os
import sys
from pathlib import Path
from typing import Dict, Any

try:
    import yaml
except ImportError:
    yaml = None

from agra.errors import InventoryNotFoundError
from agra.utils.colors import warn

from agra.constants import (
    PROJECT_ROOT, GLOBALS_FILE, PASSWORDS_FILE, DEFAULT_INVENTORY,
    ANSIBLE_DIR, ETC_DIR,
)


def _existing_inventory(raw: str, source: str) -> Path:
    """Path inventory yang benar-benar ada; relatif dihitung dari cwd (bukan repo)."""
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    p = p.resolve()
    if p.exists():
        return p
    msg = f"Inventory dari {source} tidak ditemukan: {p}"
    repo_copy = (PROJECT_ROOT / raw).resolve()
    if not Path(raw).expanduser().is_absolute() and repo_copy.exists():
        msg += f" (path relatif dihitung dari direktori kerja; maksudnya {repo_copy}?)"
    raise InventoryNotFoundError(msg)


def resolve_inventory(override: str | None = None) -> Path:
    """Resolve inventory: -i > env AGRA_INVENTORY > DEFAULT_INVENTORY.

    Inventory yang disebut eksplisit (-i atau AGRA_INVENTORY) tapi tidak ada =
    error, TIDAK fallback ke all-in-one — salah ketik tidak boleh membuat agra
    menyentuh host lain.
    """
    if override:
        return _existing_inventory(override, "-i/--inventory")

    env_inv = os.environ.get("AGRA_INVENTORY", "")
    if env_inv:
        return _existing_inventory(env_inv, "env AGRA_INVENTORY")

    if DEFAULT_INVENTORY.exists():
        return DEFAULT_INVENTORY
    raise InventoryNotFoundError(
        f"Inventory tidak ditemukan. Set via: -i /path/inventory ATAU env AGRA_INVENTORY ATAU buat {DEFAULT_INVENTORY}"
    )


def load_globals_yaml() -> Dict[str, Any]:
    """Load /etc/agra/globals.yml + passwords.yml secara shallow untuk info CLI.

    Playbook TIDAK memakai fungsi ini — playbook menerima kedua file via
    extra-vars dari run_playbook (ARCHITECTURE.md §8.1). Tidak ada fallback ke
    ./etc/agra di repo: file yang hilang/tidak terbaca hanya di-warn.
    """
    merged: Dict[str, Any] = {}
    if yaml is None:
        return merged
    for f in (GLOBALS_FILE, PASSWORDS_FILE):
        if not f.exists():
            warn(f"{f} tidak ditemukan.")
            continue
        try:
            with f.open("r") as fh:
                d = yaml.safe_load(fh) or {}
            if isinstance(d, dict):
                merged.update(d)
        except PermissionError:
            warn(f"Permission denied membaca {f}. Perbaiki ownership: sudo chown -R \"$USER:$USER\" {ETC_DIR}")
        except Exception as e:
            warn(f"Gagal load {f}: {type(e).__name__}: {str(e)[:120]}")
    return merged


def load_globals_file() -> Dict[str, Any]:
    """Load HANYA /etc/agra/globals.yml (tanpa passwords) — {} jika hilang/tidak valid."""
    if yaml is None:
        return {}
    try:
        with GLOBALS_FILE.open("r") as fh:
            data = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def ansible_bin_dir() -> str:
    """Direktori script interpreter ini (bin/ venv): ansible-core terpasang di sana
    sebagai dependency agra, walaupun venv tidak di-activate."""
    return str(Path(sys.executable).parent)


def ansible_path() -> str:
    """PATH dengan bin/ venv agra di depan — ansible-playbook dari venv yang sama menang."""
    path = os.environ.get("PATH", os.defpath)
    bin_dir = ansible_bin_dir()
    if bin_dir in path.split(os.pathsep):
        return path
    return bin_dir + os.pathsep + path


def ansible_env() -> Dict[str, str]:
    """Environment variables untuk subprocess ansible-playbook."""
    env = os.environ.copy()
    env["PATH"] = ansible_path()
    env.setdefault("ANSIBLE_ROLES_PATH", str(ANSIBLE_DIR / "roles"))
    env.setdefault("ANSIBLE_CONFIG", str(PROJECT_ROOT / "ansible.cfg"))
    return env
