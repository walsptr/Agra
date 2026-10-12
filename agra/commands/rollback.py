"""agra rollback - Rollback service ke versi sebelumnya (DESIGN §7).

Target default: entry `previous` di /etc/agra/.installed_versions.yml (dicatat
otomatis oleh deploy/upgrade/rollback). Bisa dibatasi per service via
--service, atau di-pin manual via --<service>-tag. Target di-pass sebagai
extra-vars sehingga menimpa tag di globals.yml untuk run ini.

Safety: rencana ditampilkan dulu, warning eksplisit untuk lintas major version
(RULES §10), konfirmasi ketik ROLLBACK, lalu precheck, lalu rolling apply
(standby first, master last, health gate per host).
"""
from __future__ import annotations
import argparse
import os
from typing import Dict, List

from agra.constants import INSTALLED_VERSIONS_FILE
from agra.utils.colors import warn, info, error, section, BOLD, RESET, RED, YELLOW
from agra.utils.cli_args import add_inventory_argument
from agra.commands.check import require_explicit_inventory, run_validation
from agra.utils.run_playbook import check_extra_vars_conflicts, run_playbook
from agra.utils.versions import (
    SERVICE_TAG_VARS, load_installed_versions, entry_versions, globals_versions, major_version,
    partial_rollout_note,
)


def setup_parser(subparsers: "argparse._SubParsersAction") -> argparse.ArgumentParser:
    p = subparsers.add_parser(
        "rollback", aliases=["revert", "downgrade"],
        help="Rollback ke versi sebelumnya (default: versi `previous` yang tercatat).",
        description=(
            "Rollback rolling (standby first, master last, health gate per host). Target default = "
            f"entry `previous` di {INSTALLED_VERSIONS_FILE}. Batasi dengan --service, atau pin manual "
            "dengan --<service>-tag."
        ),
    )
    add_inventory_argument(p)
    p.add_argument("-l", "--limit")
    p.add_argument("-e", "--extra-vars", action="append", default=[])
    p.add_argument("--service", action="append", choices=sorted(SERVICE_TAG_VARS), default=[],
                   help="Service yang di-rollback ke versi `previous` (bisa diulang). Default: semua yang berubah.")
    for svc in SERVICE_TAG_VARS:
        p.add_argument(f"--{svc.replace('_', '-')}-tag", dest=f"{svc}_tag",
                       help=f"Pin manual tag {svc} (override versi `previous`).")
    p.add_argument("-t", "--tags", action="append", default=[])
    p.add_argument("--skip-tags", action="append", default=[])
    p.add_argument(
        "--precheck",
        action=argparse.BooleanOptionalAction,
        default=True,
        dest="precheck",
        help="Jalankan precheck validasi (tanpa update OS/Docker) SEBELUM rollback (default: aktif). --no-precheck TIDAK DISARANKAN.",
    )
    p.add_argument("--yes", action="store_true", help="Skip konfirmasi (CI; atau AGRA_NON_INTERACTIVE=1).")
    p.add_argument("-v", "--verbose", action="count", default=0)
    p.set_defaults(func=run_rollback)
    return p


def _split_csv(values: List[str]) -> List[str]:
    out: List[str] = []
    for v in values or []:
        out.extend(x.strip() for x in v.split(",") if x.strip())
    return out


def _resolve_targets(args: argparse.Namespace, previous: Dict[str, str]) -> Dict[str, str]:
    """Return {tag_var: target_tag}. Pin manual menang atas `previous`."""
    targets: Dict[str, str] = {}
    pinned = {var: getattr(args, var) for var in SERVICE_TAG_VARS.values() if getattr(args, var, None)}
    services = args.service or ([] if pinned else list(SERVICE_TAG_VARS))
    for svc in services:
        var = SERVICE_TAG_VARS[svc]
        if var in previous:
            targets[var] = previous[var]
        elif args.service:
            warn(f"Tidak ada versi `previous` tercatat untuk {svc} — lewati (pakai --{svc.replace('_', '-')}-tag untuk pin manual).")
    targets.update(pinned)
    return targets


def run_rollback(args: argparse.Namespace) -> int:
    # Rollback hanya mengubah versi yang tampil di rencana: -e <service>_tag
    # akan mengubah service lain tanpa terlihat/terkonfirmasi.
    check_extra_vars_conflicts(args.extra_vars, SERVICE_TAG_VARS.values())
    if getattr(args, "precheck", True):
        # Sebelum rencana & konfirmasi: jangan minta ketik ROLLBACK lalu gagal.
        require_explicit_inventory(args, "agra rollback")
    try:
        recorded = load_installed_versions()
    except PermissionError:
        error(f"Tidak bisa membaca {INSTALLED_VERSIONS_FILE}. Perbaiki ownership: sudo chown -R \"$USER:$USER\" /etc/agra")
        return 2

    previous = entry_versions(recorded, "previous")
    current = entry_versions(recorded, "current") or globals_versions()

    targets = _resolve_targets(args, previous)
    changes = {var: tag for var, tag in targets.items() if current.get(var) != tag}

    if not targets:
        error(f"Tidak ada target rollback: belum ada versi `previous` di {INSTALLED_VERSIONS_FILE}.")
        print("Pin versi manual, contoh: agra rollback -i <inventory> --grafana-tag 11.2.0")
        return 1
    if not changes:
        info("Semua service sudah berada di versi target. Tidak ada yang di-rollback.")
        return 0

    section("RENCANA ROLLBACK")
    major_jumps = []
    for var, tag in changes.items():
        cur = current.get(var, "?")
        cur_major, tgt_major = major_version(cur), major_version(tag)
        jump = cur_major is not None and tgt_major is not None and cur_major != tgt_major
        if jump:
            major_jumps.append(var)
        print(f"  {var:<20} {cur:>14}  →  {tag:<14}{RED}{BOLD}  LINTAS MAJOR VERSION{RESET}" if jump
              else f"  {var:<20} {cur:>14}  →  {tag}")

    if major_jumps:
        warn(f"{BOLD}Rollback lintas major version ({', '.join(major_jumps)}){RESET}: format data "
             "(Grafana schema / Prometheus TSDB) bisa tidak kompatibel dengan versi lama.")
        warn("Alternatif yang lebih aman: `agra backup list` lalu `agra restore -n <backup> --yes-i-really-mean-it` "
             "(upgrade selalu membuat backup sebelum jalan).")

    if not args.yes and os.environ.get("AGRA_NON_INTERACTIVE", "") != "1":
        try:
            resp = input(f"{YELLOW}Ketik '{BOLD}ROLLBACK{RESET}{YELLOW}' untuk melanjutkan, atau Ctrl+C untuk batal: ").strip()
        except (EOFError, KeyboardInterrupt):
            error("\nRollback dibatalkan user.")
            return 1
        if resp != "ROLLBACK":
            error(f"Konfirmasi salah (input={resp!r}). Rollback dibatalkan.")
            return 1

    if getattr(args, "precheck", True):
        rc = run_validation(args, "agra rollback")
        if rc != 0:
            error(f"Precheck FAILED (rc={rc}). Rollback dibatalkan.")
            return rc

    user_evar = args.extra_vars or []
    if isinstance(user_evar, str):
        user_evar = [user_evar]

    note = partial_rollout_note(args.limit)
    if note:
        warn(note)
    rc = run_playbook(
        "rollback",
        inventory=args.inventory,
        tags=_split_csv(args.tags) or None,
        skip_tags=_split_csv(args.skip_tags) or None,
        limit=args.limit,
        extra_vars=changes,
        extra_vars_raw=["_agra_cli_inventory_explicit_confirmed=true"] + list(user_evar),
        verbosity=args.verbose,
        description="Rollback rolling ke versi sebelumnya",
        abort_on_nonzero=False,
    )
    if note and rc == 0:
        warn(note)
    return rc
