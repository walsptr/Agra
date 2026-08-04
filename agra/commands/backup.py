"""agra backup — subcommands create & list.

backup create = jalankan playbook backup.yml (Prometheus via snapshot API RULES §8).
backup list = PURE PYTHON parse manifest .yml di backup_root_dir → print table.
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    import yaml
except ImportError:
    yaml = None

from agra.utils.colors import info, warn, error, section, BOLD, RESET, YELLOW, GREEN, CYAN, GRAY
from agra.constants import BACKUP_ROOT_DIR
from agra.utils.run_playbook import run_playbook


def _resolve_backup_dir(args_dir: Optional[str] = None) -> Path:
    """Resolve backup dir: CLI args.backup_dir or constant default."""
    p = Path(args_dir) if args_dir else Path(BACKUP_ROOT_DIR)
    return p


def _fmt_size(n) -> str:
    try:
        n = int(n)
    except Exception:
        return "?"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    f = float(n)
    while f >= 1024 and i < len(units) - 1:
        f /= 1024
        i += 1
    return f"{f:.1f} {units[i]}"


def cmd_list(args: argparse.Namespace) -> int:
    """List backup manifests — pure Python, no ansible."""
    bdir = _resolve_backup_dir(getattr(args, "backup_dir", None))
    section(f"List agra backups di {bdir}")

    if not bdir.exists():
        warn(f"Backup root dir {bdir} TIDAK ADA. Belum pernah ada backup? Jalankan: agra backup create")
        return 0

    if yaml is None:
        error("PyYAML TIDAK TERINSTALL (required untuk backup list). Install: pip install PyYAML>=6.0")
        return 2

    manifests = sorted(
        [f for f in bdir.iterdir() if f.is_file() and f.name.endswith(".yml") and "manifest" not in f.name.lower() and "backup" in f.name],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not manifests:
        info("Tidak ada backup manifest ditemukan.")
        return 0

    parsed: List[Dict[str, Any]] = []
    for m in manifests:
        try:
            with m.open("r") as fh:
                d = yaml.safe_load(fh) or {}
            if isinstance(d, dict):
                d.setdefault("_manifest_path", str(m))
                d.setdefault("_tarball_exists", False)
                tar = d.get("backup_tarball_path", "")
                if tar:
                    tp = Path(tar)
                    d["_tarball_exists"] = tp.exists()
                    if tp.exists() and "backup_tarball_size_bytes" not in d:
                        try:
                            d["backup_tarball_size_bytes"] = tp.stat().st_size
                        except Exception:
                            pass
                parsed.append(d)
        except Exception as e:
            warn(f"Skip invalid manifest {m.name}: {e}")

    cols = ["#", "BACKUP NAME", "DATE", "HOST", "MODE", "TSDB?", "SIZE", "TARBALL"]
    rows: List[List[str]] = []
    for i, d in enumerate(parsed, 1):
        name = d.get("backup_name", d.get("_manifest_path", "?")).split("/")[-1].replace(".yml", "")
        date_val = d.get("backup_date_human", d.get("backup_timestamp", ""))
        try:
            if isinstance(date_val, str) and "T" in date_val:
                dt = datetime.fromisoformat(date_val.replace("Z", "+00:00"))
                date_val = dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
        host = d.get("backup_host", "-")
        mode = d.get("agra_deployment_mode", "-")
        tsdb = "Y" if d.get("backup_include_prometheus_tsdb") else "n"
        size = _fmt_size(d.get("backup_tarball_size_bytes", d.get("backup_tarball_size", 0)))
        tar = "✅" if d.get("_tarball_exists") else "❌"
        rows.append([str(i), name, date_val, host, mode, tsdb, size, tar])

    widths = [len(c) for c in cols]
    for r in rows:
        for i, v in enumerate(r):
            widths[i] = max(widths[i], len(v))
    sep = "─" * (sum(widths) + 3 * len(cols) - 1)
    def fmt_row(r):
        return " │ ".join(v.ljust(widths[i]) for i, v in enumerate(r))
    print(f"{CYAN}{BOLD}{fmt_row(cols)}{RESET}")
    print(f"{GRAY}{sep}{RESET}")
    for r in rows:
        print(fmt_row(r))

    n = len(rows)
    print(f"\nTotal backups: {BOLD}{n}{RESET} (terurut dari TERBARU)")
    print(f"{GRAY}Restore contoh: agra restore --backup-name {rows[0][1] if rows else '<name>'} --yes-i-really-mean-it{RESET}")
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    evars: Dict[str, Any] = {}
    if getattr(args, "include_prometheus_tsdb", False):
        evars["backup_include_prometheus_tsdb"] = True
    if getattr(args, "backup_dir", None):
        evars["backup_root_dir"] = str(_resolve_backup_dir(args.backup_dir))
    if getattr(args, "retention", None):
        evars["backup_retention_count"] = int(args.retention)

    tags_flat = []
    for t in getattr(args, "tags", None) or []:
        tags_flat.extend([x.strip() for x in t.split(",") if x.strip()])

    precheck_enabled = getattr(args, "precheck", True)
    if precheck_enabled:
        from agra.commands.check import run_check
        rc = run_check(args)
        if rc != 0:
            error(f"Precheck FAILED (rc={rc}). Backup Create DIBATALKAN untuk mencegah bad state.")
            warn("Untuk bypass precheck: `agra backup create --no-precheck` (TIDAK DISARANKAN production).")
            return rc

    user_evar = getattr(args, "extra_vars", None) or []
    if isinstance(user_evar, str):
        user_evar = [user_evar]
    merged_evar = ["_agra_cli_inventory_explicit_confirmed=true"] + list(user_evar)

    return run_playbook(
        "backup",
        inventory=getattr(args, "inventory", None),
        tags=tags_flat or None,
        limit=getattr(args, "limit", None),
        extra_vars=evars if evars else None,
        extra_vars_raw=merged_evar or None,
        verbosity=getattr(args, "verbose", 0),
        description="Backup Grafana config + Prometheus Snapshot API TSDB",
        abort_on_nonzero=False,
    )


def setup_parser(subparsers: "argparse._SubParsersAction") -> argparse.ArgumentParser:
    p = subparsers.add_parser(
        "backup", aliases=["bak", "snap"],
        help="Backup monitoring (subcommands: create | list).",
        description="Backup management: agra backup create (playbook backup.yml) | agra backup list (pure Python parse manifest YAML, TIDAK perlu ansible).",
    )
    p.add_argument("-i", "--inventory", dest="inventory")
    p.add_argument("-l", "--limit", dest="limit")
    p.add_argument("-d", "--backup-dir", dest="backup_dir", help=f"Backup root dir (default: {BACKUP_ROOT_DIR})")
    p.add_argument("-t", "--tags", action="append", default=[], dest="tags")
    p.add_argument("-e", "--extra-vars", action="append", default=[], dest="extra_vars")
    p.add_argument(
        "--precheck",
        action=argparse.BooleanOptionalAction,
        default=True,
        dest="precheck",
        help="Jalankan precheck SEBELUM backup create (default: TRUE / precheck aktif). "
             "Untuk bypass: --no-precheck (TIDAK DISARANKAN production)."
    )
    p.add_argument("-v", "--verbose", action="count", default=0, dest="verbose")

    sub = p.add_subparsers(dest="backup_command", required=False, metavar="{create | list}")
    sub.default = "create"

    p_create = sub.add_parser("create", help="Run backup playbook (default subcommand).")
    p_create.add_argument("--include-prometheus-tsdb", "--tsdb", action="store_true", dest="include_prometheus_tsdb",
                          help="Sertakan Prometheus TSDB snapshot via Admin API (RULES §8: via /api/v1/admin/tsdb/snapshot, BUKAN tar folder). WARNING: butuh disk space besar untuk metrics TSDB.")
    p_create.add_argument("-n", "--retention", type=int, dest="retention",
                          help="Override backup_retention_count (default keep 7 terbaru).")
    p_create.add_argument("-i", "--inventory", dest="inventory")
    p_create.add_argument("-l", "--limit")
    p_create.add_argument("-t", "--tags", action="append", default=[])
    p_create.add_argument("-e", "--extra-vars", action="append", default=[])
    p_create.add_argument(
        "--precheck",
        action=argparse.BooleanOptionalAction,
        default=True,
        dest="precheck",
        help="Jalankan precheck SEBELUM backup create (default: TRUE / precheck aktif). "
             "Untuk bypass: --no-precheck (TIDAK DISARANKAN production)."
    )
    p_create.add_argument("-v", "--verbose", action="count", default=0, dest="verbose")
    p_create.set_defaults(func=cmd_create)

    p_list = sub.add_parser("list", aliases=["ls", "show"], help="List backups (pure Python parse manifest YAML — TIDAK perlu ansible).")
    p_list.add_argument("-d", "--backup-dir", dest="backup_dir", help=f"Backup root dir (default: {BACKUP_ROOT_DIR})")
    p_list.add_argument("--json", action="store_true", help="Output JSON machine readable.")
    p_list.set_defaults(func=cmd_list)

    p.set_defaults(func=cmd_create, backup_command="create")
    return p
