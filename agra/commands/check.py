"""`agra check` / `agra precheck` — jalankan precheck.yml.

KHUSUS command ini: `-i / --inventory` WAJIB diisi EXPLICIT.
TIDAK BOLEH pakai default `inventory/all-in-one` (agar user explicit menentukan
inventory mana yang mau di-check node-node nya sekaligus).
"""
from __future__ import annotations
import argparse
import os
import sys
from agra.utils.run_playbook import run_playbook
from agra.utils.colors import error, BOLD, RESET


def setup_parser(subparsers: "argparse._SubParsersAction") -> argparse.ArgumentParser:
    p: argparse.ArgumentParser = subparsers.add_parser(
        "check", aliases=["precheck", "verify"],
        help="Run preflight validation (playbook precheck.yml) + PING semua node di inventory. ⚠️ -i WAJIB explicit.",
        description="Validasi topologi inventory, grafana DB connectivity, versi variabel, TLS expiry, + PING reachability SEMUA HOST di inventory.\n\nPENTING: Parameter -i/--inventory WAJIB diisi (TIDAK BOLEH pakai default). Explicit inventory mana yang dicek.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Contoh penggunaan:
  agra check -i inventory/all-in-one           # Precheck all-in-one 1 node
  agra check -i inventory/multinode -K         # Precheck multi-node + tanya sudo password
  agra precheck -i ~/custom-inv/myinv.ini      # Pakai custom inventory path
""",
    )
    p.add_argument("-i", "--inventory",
                   help="✅ WAJIB: Inventory file path. TIDAK BOLEH default — harus explicit pilih inventory mana yang dicek beserta node nya.",
                   required=False)  # False di argparse agar custom error message lebih jelas di bawah (bukan standard argparse error)
    p.add_argument("-v", "--verbose", action="count", default=0, help="Ansible verbosity (-v to -vvvv)")
    p.set_defaults(func=run_check)
    return p


def run_check(args: argparse.Namespace) -> int:
    """Wrapper: pastikan -i / --inventory / AGRA_INVENTORY ADA, baru jalankan precheck."""

    inv_from_cli = getattr(args, "inventory", None) or None
    inv_from_env = os.environ.get("AGRA_INVENTORY", "") or None

    if inv_from_cli is None and inv_from_env is None:
        error("❌ `agra check` / `agra precheck` / `agra verify` MEMERLUKAN -i / --inventory secara EXPLICIT.")
        print(f"""
{BOLD}Kenapa diwajibkan?{RESET}
  • Command ini tidak hanya validasi vars — TAPI JUGA PING SEMUA HOST di inventory
    untuk memastikan NODE BISA DIKONEKSI (SSH reachable).
  • Agar anda TIDAK salah precheck — misal lupa inventory, tapi malah ke-all-in-one localhost
    padahal ingin precheck inventory multi-node production.
  • Semua 3 alias: `agra check` | `agra precheck` | `agra verify` — WAJIB pakai -i explicit.

{BOLD}Cara perbaiki (PILIH SALAH SATU):{RESET}
  1. Tambahkan flag explicit -i:   {BOLD}agra check -i inventory/all-in-one{RESET}
     atau:  {BOLD}agra precheck -i inventory/multinode -K{RESET}
  2. Atau set env AGRA_INVENTORY permanen (tidak perlu -i tiap kali):
        export AGRA_INVENTORY=/home/user/Agra/inventory/multinode
     lalu jalankan:  agra check / agra precheck / agra verify

{BOLD}Contoh command valid:{RESET}
  agra check -i inventory/all-in-one
  agra precheck -i inventory/multinode -K
  agra verify -i ~/custom-inv/production.ini
""", flush=True)
        return 1

    # Guard: Extra_vars boolean flag untuk defense-in-depth di playbook level (precheck.yml assert PALING ATAS).
    # Flag ini HANYA di-set JIKA user lewat CLI `agra check/precheck/verify` DENGAN -i / AGRA_INVENTORY valid.
    # Jika user BYPASS CLI & panggil `ansible-playbook precheck.yml` langsung — flag ini TIDAK ADA → FAIL di playbook.
    cli_guard_extra_vars = {
        "_agra_cli_inventory_explicit_confirmed": True,
    }

    return run_playbook(
        "precheck",
        inventory=inv_from_cli,  # jika inv_from_cli None (cuma env), resolve_inventory nanti ambil dari env
        verbosity=args.verbose,
        extra_vars=cli_guard_extra_vars,
        description="Preflight Validation (agra check) + PING SEMUA NODE",
        abort_on_nonzero=False,
    )
