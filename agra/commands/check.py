"""`agra check` / `agra precheck` — jalankan precheck.yml.

KHUSUS command ini: `-i / --inventory` WAJIB diisi EXPLICIT.
TIDAK BOLEH pakai default `inventory/all-in-one` (agar user explicit menentukan
inventory mana yang mau di-check node-node nya sekaligus).
"""
from __future__ import annotations
import argparse
import os
from agra.errors import AgraUserError
from agra.constants import GLOBALS_FILE, SECRET_KEYS, PER_HOST_KEYS, REMOVED_KEYS
from agra.utils.cli_args import add_inventory_argument
from agra.utils.run_playbook import run_playbook
from agra.utils.colors import warn


def setup_parser(subparsers: "argparse._SubParsersAction") -> argparse.ArgumentParser:
    p: argparse.ArgumentParser = subparsers.add_parser(
        "check", aliases=["precheck", "verify"],
        help="Run preflight bootstrap + validation (update packages OS, safe-upgrade, install Docker engine, verify Docker ready) + PING semua node + validasi config vars. ⚠️ -i WAJIB explicit.",
        description="Jalankan 2 fase: [1] BOOTSTRAP NODE: apt/dnf update cache + safe-upgrade packages + install Docker engine + dependencies + start Docker daemon + verify Docker info OK di setiap node. [2] VALIDASI: topologi inventory, Grafana DB connectivity, variabel versi tag, TLS expiry, + PING reachability SEMUA HOST di inventory.\n\nPENTING: Parameter -i/--inventory WAJIB diisi (TIDAK BOLEH pakai default). Explicit inventory mana yang di-bootstrap beserta divalasinya.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Contoh penggunaan:
  agra check -i inventory/all-in-one           # Precheck all-in-one 1 node
  agra -i inventory/multinode check            # -i boleh sebelum command
  agra precheck -i ~/custom-inv/myinv.ini      # Pakai custom inventory path
""",
    )
    # Tidak required di argparse agar pesan error di run_check lebih jelas.
    add_inventory_argument(p, help="WAJIB (atau env AGRA_INVENTORY): inventory yang di-check — tidak ada default all-in-one.")
    p.add_argument("-v", "--verbose", action="count", default=0, help="Ansible verbosity (-v to -vvvv)")
    p.set_defaults(func=run_check)
    return p


def _warn_misplaced_globals_keys() -> None:
    """Warn jika globals.yml berisi secret, var per-host, atau var yang sudah dihapus.

    Precheck tidak bisa membedakan asal var (semua extra-vars), jadi cek
    sumber file dilakukan di sini.
    """
    try:
        import yaml
        with GLOBALS_FILE.open() as fh:
            data = yaml.safe_load(fh) or {}
    except Exception:
        return  # run_playbook yang melaporkan file hilang / tidak terbaca
    if not isinstance(data, dict):
        return
    for key in SECRET_KEYS:
        if key in data:
            warn(f"{GLOBALS_FILE}: '{key}' adalah secret — pindahkan ke passwords.yml (passwords.yml dimuat setelah globals.yml dan menang jika key ada di sana).")
    for key in PER_HOST_KEYS:
        if key in data:
            warn(f"{GLOBALS_FILE}: '{key}' berlaku per-host — hapus dari globals.yml dan set di host_vars/<host>.yml (globals.yml berlaku untuk semua host).")
    for key, why in REMOVED_KEYS.items():
        if key in data:
            warn(f"{GLOBALS_FILE}: '{key}' sudah dihapus dan tidak berefek — hapus dari globals.yml. {why}")


def require_explicit_inventory(args: argparse.Namespace, command: str) -> None:
    """Precheck menyentuh SEMUA host inventory: tanpa -i / AGRA_INVENTORY jangan
    pernah jatuh ke inventory/all-in-one diam-diam. Exit 2 (kesalahan operator)."""
    if getattr(args, "inventory", None) or os.environ.get("AGRA_INVENTORY", ""):
        return
    raise AgraUserError(
        f"`{command}` menjalankan precheck dan MEMERLUKAN inventory explicit: tambahkan "
        f"-i <inventory> (contoh: {command} -i inventory/multinode), atau set env AGRA_INVENTORY. "
        "Precheck tidak memakai default inventory/all-in-one supaya tidak salah target."
    )


def run_validation(args: argparse.Namespace, command: str) -> int:
    """Precheck untuk backup/upgrade/rollback/restore: validasi konfigurasi +
    koneksi + `docker info` di host yang di-target (--limit dihormati), TANPA
    bootstrap. apt/dnf upgrade hanya lewat `agra check`: upgrade paket Docker
    me-restart semua container di semua node sekaligus."""
    require_explicit_inventory(args, command)
    _warn_misplaced_globals_keys()
    evars = {"_agra_cli_inventory_explicit_confirmed": True, "_agra_precheck_bootstrap": False}
    # Bukan --limit: play validasi di localhost tidak cocok dengan pattern host
    # user dan akan di-skip. Pattern dipakai sebagai `hosts:` play node saja.
    if getattr(args, "limit", None):
        evars["_agra_precheck_limit"] = args.limit
    return run_playbook(
        "precheck",
        inventory=getattr(args, "inventory", None),
        verbosity=getattr(args, "verbose", 0),
        extra_vars=evars,
        description=f"Precheck validasi sebelum `{command}` (tanpa bootstrap node)",
        abort_on_nonzero=False,
    )


def run_check(args: argparse.Namespace) -> int:
    """`agra check`: validasi + bootstrap node (apt/dnf upgrade, Docker)."""
    require_explicit_inventory(args, "agra check")

    # Guard: Extra_vars boolean flag untuk defense-in-depth di playbook level (precheck.yml assert PALING ATAS).
    # Flag ini HANYA di-set JIKA user lewat CLI `agra check/precheck/verify` DENGAN -i / AGRA_INVENTORY valid.
    # Jika user BYPASS CLI & panggil `ansible-playbook precheck.yml` langsung — flag ini TIDAK ADA → FAIL di playbook.
    _warn_misplaced_globals_keys()

    cli_guard_extra_vars = {
        "_agra_cli_inventory_explicit_confirmed": True,
    }

    return run_playbook(
        "precheck",
        inventory=getattr(args, "inventory", None),  # None (cuma env): resolve_inventory ambil dari env
        verbosity=args.verbose,
        extra_vars=cli_guard_extra_vars,
        description="Preflight Validation (agra check) + PING SEMUA NODE",
        abort_on_nonzero=False,
    )
