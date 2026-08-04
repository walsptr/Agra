"""agra destroy - Hapus service monitoring. SAFETY 2 LAYER.

LAYER 1 (CLI, SEBELUM ansible pernah diinvoke):
  - WAJIB ada flag --yes-i-really-mean-it. JIKA TIDAK ADA → ABORT ERROR (exit 1), ansible TIDAK PERNAH di-call.
  - Flag --yes-i-really-mean-it OTOMATIS skip interactive typed sentence confirm (cukup 1x flag eksplisit sesuai RULES §8).
  - JIKA TIDAK ADA flag --yes-i-really-mean-it, dan (AGRA_NON_INTERACTIVE != 1, TIDAK -y/--yes) → PROMPT user KETIK KALIMAT KONFIRMASI PANJANG:
      YES SAYA SADAR AKAN MENGHAPUS SELURUH SERVICE MONITORING DAN JIKA MENGGUNAKAN --purge-data MAKA SEMUA DATA GRAFANA DB DAN PROMETHEUS TSDB TIDAK BISA DIKEMBALIKAN.
    JIKA SALAH → ABORT.
  - --purge-data TIDAK default (default = retain data_dir, bisa redeploy nanti tanpa kehilangan data)

LAYER 2 (playbook destroy.yml): assert destroy_confirm=true sebagai defense-in-depth (walaupun CLI sudah check).
"""
from __future__ import annotations
import argparse
import os
import sys
from agra.utils.colors import warn, info, error, section, BOLD, RESET, RED, YELLOW, MAGENTA
from agra.utils.run_playbook import run_playbook


CONFIRM_SENTENCE = (
    "YES SAYA SADAR AKAN MENGHAPUS SELURUH SERVICE MONITORING "
    "DAN JIKA MENGGUNAKAN --purge-data MAKA SEMUA DATA GRAFANA DB "
    "DAN PROMETHEUS TSDB TIDAK BISA DIKEMBALIKAN."
)


def setup_parser(subparsers: "argparse._SubParsersAction") -> argparse.ArgumentParser:
    p = subparsers.add_parser(
        "destroy", aliases=["remove", "teardown", "uninstall"],
        help="Destroy / uninstall monitoring stack services dari node (DEFAULT: retain data, TIDAK purge).",
        description=f"Remove agra service containers/systemd units. SAFETY 2-LAYER (RULES §8): (1) CLI ABORT tanpa flag --yes-i-really-mean-it. (2) Playbook assert destroy_confirm=true. --purge-data: hapus grafana.db + prometheus tsdb (default OFF, data disimpan untuk redeploy).",
    )
    p.add_argument("-i", "--inventory")
    p.add_argument("-l", "--limit")
    p.add_argument(
        "--purge-data",
        action="store_true",
        dest="destroy_purge_data",
        help="HAPUS JUGA data_dir (grafana.db & prometheus tsdb). DEFAULT FALSE: data disimpan agar redeploy tanpa kehilangan.",
    )
    p.add_argument(
        "--yes-i-really-mean-it",
        dest="yes_i_really_mean_it",
        action="store_true",
        help="(WAJIB) Flag konfirmasi CLI LAYER 1. Tanpa ini command ABORT SEBELUM ansible dipanggil.",
    )
    p.add_argument("-y", "--yes", dest="auto_yes", action="store_true", help="Skip interactive typed sentence confirm (CI: AGRA_NON_INTERACTIVE=1 atau --yes-i-really-mean-it juga setara dengan -y).")
    p.add_argument("-t", "--tags", action="append", default=[])
    p.add_argument("--skip-tags", action="append", default=[])
    p.add_argument("-e", "--extra-vars", action="append", default=[])
    p.add_argument(
        "--precheck",
        action=argparse.BooleanOptionalAction,
        default=False,
        dest="precheck",
        help="Jalankan precheck SEBELUM destroy (default: FALSE / nonaktif. Destroy punya safety 2 layer sendiri). "
             "Untuk aktifkan: --precheck (TIDAK DISARANKAN — destroy butuh state apa adanya)."
    )
    p.add_argument("-v", "--verbose", action="count", default=0)
    p.set_defaults(func=run_destroy)
    return p


def run_destroy(args: argparse.Namespace) -> int:
    if not getattr(args, "yes_i_really_mean_it", False):
        error("DESTROY DIBLOKIR (RULES §8 SAFETY LAYER 1: TIDAK ADA FLAG --yes-i-really-mean-it).")
        print(f"\n{RED}{BOLD}Operasi destroy BERSIFAT DESTRUKTIF.{RESET}")
        print(f"Untuk melanjutkan, TAMBAHKAN FLAG: {YELLOW}{BOLD}--yes-i-really-mean-it{RESET}")
        print(f"Contoh: {MAGENTA}agra destroy --yes-i-really-mean-it{RESET}")
        if args.destroy_purge_data:
            print(f"{RED}  + --purge-data AKTIF → SELURUH data grafana.db & prometheus TSDB AKAN DIHAPUS PERMANEN.{RESET}")
        else:
            print(f"{YELLOW}  + --purge-data TIDAK AKTIF → data_dir service AKAN DITAHAN (aman redeploy nanti).{RESET}")
        print(f"\n{RED}Ansible TIDAK dipanggil sama sekali di abort ini.{RESET}")
        return 1

    interactive = (os.environ.get("AGRA_NON_INTERACTIVE", "") != "1") and not getattr(args, "auto_yes", False) and not getattr(args, "yes_i_really_mean_it", False)
    if interactive:
        section(f"{RED}{BOLD}DESTROY — KONFIRMASI AKHIR (typed sentence WAJIB){RESET}")
        purge = args.destroy_purge_data
        warn(f"{'AKAN MENGHAPUS DATA (--purge-data ON)' if purge else 'Data AKAN DITAHAN (--purge-data OFF)'}")
        warn(f"Groups['monitoring'] akan di-destroy: semua service common/node_exporter/prometheus/grafana/nginx/keepalived")
        print(f"\n{YELLOW}{BOLD}Ketik KALIMAT BERIKUT INI PERSIS (case-sensitive), lalu tekan ENTER:{RESET}\n")
        print(f"    {MAGENTA}{BOLD}{CONFIRM_SENTENCE}{RESET}\n")
        try:
            resp = input(f"{YELLOW}> ").strip()
        except (EOFError, KeyboardInterrupt):
            error("\nDestroy dibatalkan user (Ctrl+C).")
            return 1
        if resp != CONFIRM_SENTENCE:
            error("KALIMAT KONFIRMASI TIDAK COCOK (boleh copy-paste saja dari atas). Destroy dibatalkan.")
            return 1
        info("Konfirmasi KALIMAT cocok. Safety LAYER 1 passed.")

    section("RUN: destroy playbook (Safety LAYER 2 di-playbook assert destroy_confirm=true)")
    if args.destroy_purge_data:
        warn(f"{RED}--purge-data AKTIF: grafana_data_dir & prometheus_data_dir AKAN DIHAPUS PERMANEN{RESET}")

    extra_vars = {
        "destroy_confirm": True,
        "destroy_purge_data": bool(args.destroy_purge_data),
    }

    tags_flat = []
    for t in args.tags or []:
        tags_flat.extend([x.strip() for x in t.split(",") if x.strip()])
    skip_flat = []
    for t in args.skip_tags or []:
        skip_flat.extend([x.strip() for x in t.split(",") if x.strip()])

    user_evar = args.extra_vars or []
    if isinstance(user_evar, str):
        user_evar = [user_evar]
    merged_evar = ["_agra_cli_inventory_explicit_confirmed=true"] + list(user_evar)

    return run_playbook(
        "destroy",
        inventory=args.inventory,
        tags=tags_flat or None,
        skip_tags=skip_flat or None,
        limit=args.limit,
        extra_vars=extra_vars,
        extra_vars_raw=merged_evar or None,
        verbosity=args.verbose,
        description="Destroy Monitoring Stack (Safety LAYER 1 PASS → LAYER 2 playbook)",
        abort_on_nonzero=False,
    )
