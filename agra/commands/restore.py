"""agra restore — CLI SAFETY LAYER VALIDASI manifest ada SEBELUM call ansible.

LAYER 1: --yes-i-really-mean-it flag WAJIB (sama seperti destroy).
LAYER 2: CLI validate restore_backup_name ATAU restore_backup_tarball ADA, manifest YAML bisa diparse (dulu sebelum ansible).
LAYER 3: Interactive typed sentence konfirmasi (AGRA_NON_INTERACTIVE=1 / --yes skip).
LAYER 4: Playbook restore.yml assert restore_confirm=true.
"""
from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional

try:
    import yaml
except ImportError:
    yaml = None

from agra.utils.colors import warn, info, error, section, BOLD, RESET, RED, YELLOW, MAGENTA
from agra.constants import BACKUP_ROOT_DIR
from agra.utils.run_playbook import run_playbook


RESTORE_CONFIRM_SENTENCE = (
    "YES SAYA SADAR RESTORE AKAN MENIMPA SELURUH KONFIGURASI DAN DATA GRAFANA SAAT INI "
    "DAN SISTEM SUDAH MELAKUKAN BACKUP-BEFORE-RESTORE OTOMATIS SEBAGAI SAFETY NET."
)


def _resolve_manifest_from_name(name: str, backup_dir: Path) -> Optional[Path]:
    """Cari manifest .yml dari backup_name (atau exact path)."""
    p = Path(name)
    if p.exists() and p.suffix in (".yml", ".yaml"):
        return p
    candidates = [
        backup_dir / f"{name}.yml",
        backup_dir / f"{name}.yaml",
        backup_dir / f"{name}.tar.gz",
    ]
    for c in candidates:
        if c.exists():
            if c.suffix in (".yml", ".yaml"):
                return c
            m = c.with_suffix("").with_suffix(".yml")
            if m.exists():
                return m
    if backup_dir.exists():
        for m in sorted(backup_dir.iterdir(), reverse=True):
            if m.is_file() and m.suffix == ".yml" and m.name.startswith("agra-backup-") and (name in m.stem):
                return m
    return None


def setup_parser(subparsers: "argparse._SubParsersAction") -> argparse.ArgumentParser:
    p = subparsers.add_parser(
        "restore", aliases=["res", "revert-backup"],
        help="Restore dari backup (butuh --backup-name ATAU --backup-tarball). SAFETY 2-LAYER.",
        description="Restore dari backup agra. Safety: CLI validate manifest EXISTS terlebih dahulu (tidak blind call ansible), --yes-i-really-mean-it WAJIB, typed sentence confirm. Playbook jalankan backup-before-restore otomatis (RULES §8).",
    )
    p.add_argument("-i", "--inventory", dest="inventory")
    p.add_argument("-l", "--limit")

    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("-n", "--backup-name", dest="restore_backup_name",
                     help="Nama backup (dari `agra backup list` column BACKUP NAME, atau exact path manifest .yml).")
    src.add_argument("-f", "--backup-tarball", "--from", dest="restore_backup_tarball",
                     help="Path ke file .tar.gz backup (alternatif jika tahu path explicit).")

    p.add_argument("-d", "--backup-dir", dest="backup_dir", default=str(BACKUP_ROOT_DIR),
                   help=f"Backup root dir (default: {BACKUP_ROOT_DIR}).")

    p.add_argument("--yes-i-really-mean-it", dest="yes_i_really_mean_it", action="store_true", required=False,
                   help="(WAJIB LAYER 1) Konfirmasi CLI — TANPA INI → ABORT SEBELUM ansible dipanggil.")
    p.add_argument("-y", "--yes", dest="auto_yes", action="store_true",
                   help="Skip typed sentence interactive confirmation (CI: AGRA_NON_INTERACTIVE=1 juga skip).")
    p.add_argument("-t", "--tags", action="append", default=[])
    p.add_argument("--skip-tags", action="append", default=[])
    p.add_argument("-e", "--extra-vars", action="append", default=[])
    p.add_argument(
        "--precheck",
        action=argparse.BooleanOptionalAction,
        default=True,
        dest="precheck",
        help="Jalankan precheck SEBELUM restore (default: TRUE / precheck aktif). "
             "Untuk bypass: --no-precheck (TIDAK DISARANKAN production)."
    )
    p.add_argument("-v", "--verbose", action="count", default=0)
    p.set_defaults(func=run_restore)
    return p


def run_restore(args: argparse.Namespace) -> int:
    if not getattr(args, "yes_i_really_mean_it", False):
        error("RESTORE DIBLOKIR (RULES §8 SAFETY LAYER 1: TIDAK ADA FLAG --yes-i-really-mean-it).")
        print(f"\n{RED}{BOLD}Restore bersifat DESTRUKTIF (menimpa Grafana DB saat ini).{RESET}")
        print(f"Tambahkan: {YELLOW}{BOLD}agra restore -n <BACKUP_NAME> --yes-i-really-mean-it{RESET}")
        print(f"\nLihat daftar backup: {MAGENTA}agra backup list{RESET}")
        return 1

    bdir = Path(args.backup_dir) if getattr(args, "backup_dir", None) else Path(BACKUP_ROOT_DIR)
    manifest_path: Optional[Path] = None
    tarball_path: Optional[Path] = None

    if getattr(args, "restore_backup_name", None):
        manifest_path = _resolve_manifest_from_name(args.restore_backup_name, bdir)
        if manifest_path:
            try:
                if yaml:
                    with manifest_path.open("r") as fh:
                        md = yaml.safe_load(fh) or {}
                    tp = md.get("backup_tarball_path")
                    if tp and Path(tp).exists():
                        tarball_path = Path(tp)
                    elif manifest_path.with_suffix(".tar.gz").exists():
                        tarball_path = manifest_path.with_suffix(".tar.gz")
            except Exception:
                pass
        if not manifest_path:
            error(
                f"Backup TIDAK DITEMUKAN: name='{args.restore_backup_name}' di dir {bdir}. "
                f"Cek daftar dengan: agra backup list -d {bdir}"
            )
            return 2
    elif getattr(args, "restore_backup_tarball", None):
        tarball_path = Path(args.restore_backup_tarball).expanduser()
        if not tarball_path.is_absolute():
            tarball_path = (Path.cwd() / tarball_path).resolve()
        if not tarball_path.exists():
            error(f"Tarball backup tidak ada: {tarball_path}")
            return 2
        manifest_path = tarball_path.with_suffix(".yml")
        if not manifest_path.exists():
            warn(f"Manifest .yml tidak ada berdampingan dengan tarball ({manifest_path}). Restore akan coba dari tarball saja.")

    info(f"Source manifest : {manifest_path or '-'}")
    info(f"Source tarball  : {tarball_path or '-'}")

    if manifest_path and yaml:
        try:
            with manifest_path.open("r") as fh:
                md = yaml.safe_load(fh) or {}
            info(f"Backup date     : {md.get('backup_date_human', md.get('backup_timestamp', 'N/A'))}")
            info(f"Backup host     : {md.get('backup_host', 'N/A')}")
            info(f"Include TSDB    : {md.get('backup_include_prometheus_tsdb', False)}")
        except Exception as e:
            warn(f"Manifest tidak valid (lanjut tetap): {e}")

    precheck_enabled = getattr(args, "precheck", True)
    if precheck_enabled:
        from agra.commands.check import run_check
        rc = run_check(args)
        if rc != 0:
            error(f"Precheck FAILED (rc={rc}). Restore DIBATALKAN untuk mencegah bad state.")
            warn("Untuk bypass precheck: `agra restore --no-precheck` (TIDAK DISARANKAN production).")
            return rc

    interactive = (os.environ.get("AGRA_NON_INTERACTIVE", "") != "1") and not getattr(args, "auto_yes", False)
    if interactive:
        section(f"{RED}{BOLD}RESTORE — KONFIRMASI TYPED SENTENCE{RESET}")
        warn(f"Restore AKAN MENIMPA Grafana DB (grafana.db) SAAT INI. Playbook otomatis menjalankan BACKUP-BEFORE-RESTORE dulu sebagai safety net.")
        print(f"\n{YELLOW}{BOLD}Ketik kalimat berikut PERSIS (case-sensitive):{RESET}\n")
        print(f"    {MAGENTA}{BOLD}{RESTORE_CONFIRM_SENTENCE}{RESET}\n")
        try:
            resp = input(f"{YELLOW}> ").strip()
        except (EOFError, KeyboardInterrupt):
            error("\nRestore dibatalkan user.")
            return 1
        if resp != RESTORE_CONFIRM_SENTENCE:
            error(f"Kalimat konfirmasi TIDAK cocok → ABORT.")
            return 1

    evars: Dict[str, Any] = {
        "restore_confirm": True,
    }
    if manifest_path:
        evars["restore_manifest_path"] = str(manifest_path)
    if getattr(args, "restore_backup_name", None):
        evars["restore_backup_name"] = args.restore_backup_name
    if tarball_path:
        evars["restore_backup_tarball"] = str(tarball_path)

    tags_flat = []
    for t in args.tags or []:
        tags_flat.extend([x.strip() for x in t.split(",") if x.strip()])
    skip_flat = []
    for t in getattr(args, "skip_tags", None) or []:
        skip_flat.extend([x.strip() for x in t.split(",") if x.strip()])

    user_evar = args.extra_vars or []
    if isinstance(user_evar, str):
        user_evar = [user_evar]
    merged_evar = ["_agra_cli_inventory_explicit_confirmed=true"] + list(user_evar)

    return run_playbook(
        "restore",
        inventory=getattr(args, "inventory", None),
        tags=tags_flat or None,
        skip_tags=skip_flat or None,
        limit=getattr(args, "limit", None),
        extra_vars=evars,
        extra_vars_raw=merged_evar or None,
        verbosity=getattr(args, "verbose", 0),
        description="Restore Grafana + Prometheus dari Backup (backup-before-restore otomatis)",
        abort_on_nonzero=False,
    )
