"""agra backup — subcommands create & list.

backup create = jalankan playbook backup.yml (Prometheus via snapshot API RULES §8).
backup list = PURE PYTHON parse manifest .yml di direktori backup CONTROL NODE
(backup.yml mem-fetch setiap backup dari master ke sana) → print table.
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    import yaml
except ImportError:
    yaml = None

from agra.utils.colors import info, warn, error, section, BOLD, RESET, CYAN, GRAY
from agra.constants import BACKUP_ROOT_DIR
from agra.utils.backups import control_backup_dir, tarball_for
from agra.utils.cli_args import add_inventory_argument, positive_int
from agra.commands.check import run_validation
from agra.utils.run_playbook import run_playbook


def _resolve_backup_dir(args_dir: Optional[str] = None) -> Path:
    """Direktori backup di MASTER (backup create -d): CLI args.backup_dir or default."""
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


def _list_entries(bdir: Path) -> List[Dict[str, Any]]:
    """Backup di control node, terbaru dulu: satu dict per manifest yang valid."""
    manifests = sorted(
        [f for f in bdir.iterdir() if f.is_file() and f.name.endswith(".yml") and "manifest" not in f.name.lower() and "backup" in f.name],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    entries: List[Dict[str, Any]] = []
    for m in manifests:
        try:
            with m.open("r") as fh:
                d = yaml.safe_load(fh) or {}
        except Exception as e:
            warn(f"Skip invalid manifest {m.name}: {e}")
            continue
        if not isinstance(d, dict):
            warn(f"Skip invalid manifest {m.name}: bukan mapping YAML")
            continue
        # backup_tarball_path di manifest = path di master; salinan yang bisa
        # direstore ada di samping manifest ini.
        tp = tarball_for(m)
        size = d.get("backup_tarball_size_bytes", d.get("backup_tarball_size"))
        if size is None and tp.is_file():
            size = tp.stat().st_size
        try:
            size_bytes = int(size) if size is not None else None
        except (TypeError, ValueError):
            size_bytes = None
        date_val = d.get("backup_date_human", d.get("backup_timestamp", ""))
        try:
            if isinstance(date_val, str) and "T" in date_val:
                date_val = datetime.fromisoformat(date_val.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
        entries.append({
            "name": str(d.get("backup_name") or m.name).split("/")[-1].replace(".yml", ""),
            "date": str(date_val),
            "host": d.get("backup_host"),
            "safety": bool(d.get("backup_safety", False)),
            "prometheus_tsdb": bool(d.get("backup_include_prometheus_tsdb", False)),
            "database_included": d.get("database_included"),
            "size_bytes": size_bytes,
            "manifest": str(m),
            "tarball": str(tp),
            "tarball_exists": tp.is_file(),
        })
    return entries


def cmd_list(args: argparse.Namespace) -> int:
    """List backup manifests — pure Python, no ansible. --json: stdout hanya JSON."""
    as_json = getattr(args, "json", False)
    bdir = control_backup_dir(getattr(args, "backup_dir", None))
    if not as_json:
        section(f"List agra backups di {bdir} (control node)")

    if not bdir.exists():
        warn(f"Backup root dir {bdir} TIDAK ADA. Belum pernah ada backup? Jalankan: agra backup create")
        if as_json:
            print("[]")
        return 0
    if not bdir.is_dir():
        error(f"{bdir} bukan direktori. -d / backup_control_node_dir harus menunjuk direktori backup di control node.")
        return 2

    if yaml is None:
        error("PyYAML TIDAK TERINSTALL (required untuk backup list). Install: pip install PyYAML>=6.0")
        return 2

    try:
        entries = _list_entries(bdir)
    except PermissionError as e:
        error(f"Tidak bisa membaca {e.filename or bdir} sebagai user saat ini.")
        print(f'Perbaiki ownership (backup di control node milik operator user): sudo chown -R "$USER:$USER" {bdir}',
              file=sys.stderr)
        return 2
    if as_json:
        print(json.dumps(entries, indent=2, default=str))
        return 0
    if not entries:
        info("Tidak ada backup manifest ditemukan.")
        return 0

    cols = ["#", "NAME", "DATE", "HOST", "TSDB", "SIZE", "TAR"]
    rows = []
    for i, e in enumerate(entries, 1):
        host = str(e["host"] or "-") + (" (safety)" if e["safety"] else "")
        rows.append([str(i), e["name"], e["date"], host, "Y" if e["prometheus_tsdb"] else "n",
                     _fmt_size(e["size_bytes"] or 0), "✅" if e["tarball_exists"] else "❌"])

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

    print(f"\nTotal backups: {BOLD}{len(rows)}{RESET} (terurut dari TERBARU)")
    print(f"{GRAY}Restore contoh: agra restore --backup-name {rows[0][1]} --yes-i-really-mean-it{RESET}")
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    evars: Dict[str, Any] = {}
    if getattr(args, "include_prometheus_tsdb", False):
        evars["backup_include_prometheus_tsdb"] = True
    if getattr(args, "backup_dir", None):
        evars["backup_root_dir"] = str(_resolve_backup_dir(args.backup_dir))
    if getattr(args, "retention", None) is not None:
        evars["backup_retention_count"] = args.retention

    tags_flat = []
    for t in getattr(args, "tags", None) or []:
        tags_flat.extend([x.strip() for x in t.split(",") if x.strip()])

    precheck_enabled = getattr(args, "precheck", True)
    if precheck_enabled:
        rc = run_validation(args, "agra backup create")
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
    add_inventory_argument(p)
    p.add_argument("-l", "--limit", dest="limit")
    p.add_argument("-d", "--backup-dir", dest="backup_dir", help=f"create: direktori backup di MASTER (default: {BACKUP_ROOT_DIR}); list: direktori di CONTROL NODE (default: /etc/agra/backups)")
    p.add_argument("-t", "--tags", action="append", default=[], dest="tags")
    p.add_argument("-e", "--extra-vars", action="append", default=[], dest="extra_vars")
    p.add_argument(
        "--precheck",
        action=argparse.BooleanOptionalAction,
        default=True,
        dest="precheck",
        help="Jalankan precheck validasi (tanpa update OS/Docker) SEBELUM backup create (default: TRUE / precheck aktif). "
             "Untuk bypass: --no-precheck (TIDAK DISARANKAN production)."
    )
    p.add_argument("-v", "--verbose", action="count", default=0, dest="verbose")

    sub = p.add_subparsers(dest="backup_command", required=False, metavar="{create | list}")
    sub.default = "create"

    p_create = sub.add_parser("create", help="Run backup playbook (default subcommand).")
    p_create.add_argument("--include-prometheus-tsdb", "--tsdb", action="store_true", dest="include_prometheus_tsdb",
                          help="Sertakan Prometheus TSDB snapshot via Admin API (/api/v1/admin/tsdb/snapshot, BUKAN tar folder). WARNING: butuh disk space besar untuk metrics TSDB.")
    p_create.add_argument("-n", "--retention", type=positive_int, dest="retention",
                          help="Override backup_retention_count: jumlah backup terbaru yang disimpan, minimal 1 (default 7).")
    # Opsi yang juga ada di `agra backup` — default milik parent (cli_args.py).
    add_inventory_argument(p_create)
    p_create.add_argument("-d", "--backup-dir", dest="backup_dir", default=argparse.SUPPRESS,
                          help=f"Direktori backup di MASTER (default: backup_root_dir, else {BACKUP_ROOT_DIR})")
    p_create.add_argument("-l", "--limit", default=argparse.SUPPRESS)
    p_create.add_argument("-t", "--tags", action="append", default=argparse.SUPPRESS)
    p_create.add_argument("-e", "--extra-vars", action="append", default=argparse.SUPPRESS)
    p_create.add_argument(
        "--precheck",
        action=argparse.BooleanOptionalAction,
        default=argparse.SUPPRESS,
        dest="precheck",
        help="Jalankan precheck validasi (tanpa update OS/Docker) SEBELUM backup create (default: TRUE / precheck aktif). "
             "Untuk bypass: --no-precheck (TIDAK DISARANKAN production)."
    )
    p_create.add_argument("-v", "--verbose", action="count", default=argparse.SUPPRESS, dest="verbose")
    p_create.set_defaults(func=cmd_create)

    p_list = sub.add_parser("list", aliases=["ls", "show"], help="List backups (pure Python parse manifest YAML — TIDAK perlu ansible).")
    p_list.add_argument("-d", "--backup-dir", dest="backup_dir", default=argparse.SUPPRESS,
                        help="Direktori backup di CONTROL NODE (default: backup_control_node_dir di globals.yml, else /etc/agra/backups)")
    p_list.add_argument("--json", action="store_true", help="Output JSON (list backup, terbaru dulu) ke stdout; pesan lain ke stderr.")
    p_list.set_defaults(func=cmd_list)

    p.set_defaults(func=cmd_create, backup_command="create")
    return p
