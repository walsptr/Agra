"""Konstanta path global untuk CLI."""
from __future__ import annotations
import os
from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

ANSIBLE_DIR: Path = PROJECT_ROOT / "ansible"
PLAYBOOK_DIR: Path = ANSIBLE_DIR / "playbooks"
ROLES_DIR: Path = ANSIBLE_DIR / "roles"
SITE_PLAYBOOK: Path = ANSIBLE_DIR / "site.yml"

ETC_DIR: Path = PROJECT_ROOT / "etc" / "agra"
GLOBALS_FILE: Path = ETC_DIR / "globals.yml"
PASSWORDS_FILE: Path = ETC_DIR / "passwords.yml"
CONFIG_DIR: Path = ETC_DIR / "config"

INVENTORY_DIR: Path = PROJECT_ROOT / "inventory"
DEFAULT_INVENTORY: Path = INVENTORY_DIR / "all-in-one"
MULTINODE_INVENTORY: Path = INVENTORY_DIR / "multinode"

BACKUP_ROOT_DIR: Path = Path("/var/lib/agra/backups")

VAULT_PASSWORD_FILE: Path = PROJECT_ROOT / ".vault_pass"

PLAYBOOKS = {
    "precheck": PLAYBOOK_DIR / "precheck.yml",
    "deploy": PLAYBOOK_DIR / "deploy.yml",
    "upgrade": PLAYBOOK_DIR / "upgrade_monitoring.yml",
    "rollback": PLAYBOOK_DIR / "rollback.yml",
    "destroy": PLAYBOOK_DIR / "destroy.yml",
    "backup": PLAYBOOK_DIR / "backup.yml",
    "restore": PLAYBOOK_DIR / "restore.yml",
    "genpwd": PLAYBOOK_DIR / "genpwd.yml",
}

REQUIRED_COMMANDS = ["ansible-playbook", "ansible"]
