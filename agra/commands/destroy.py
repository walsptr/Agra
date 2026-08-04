"""agra destroy - Hapus service monitoring. SAFETY 2 LAYER.

LAYER 1 (CLI, SEBELUM ansible pernah diinvoke):
  - WAJIB ada flag --yes-i-really-mean-it. JIKA TIDAK ADA → ABORT ERROR (exit 1), ansible TIDAK PERNAH di-call.
  - Flag --yes-i-really-mean-it OTOMATIS skip interactive typed sentence confirm (cukup 1x flag eksplisit sesuai RULES §8).
  - JIKA TIDAK ADA flag --yes-i-really-mean-it, dan (AGRA_NON_INTERACTIVE != 1, TIDAK -y/--yes) → PROMPT user KETIK KALIMAT KONFIRMASI PANJANG.
    JIKA SALAH → ABORT.
  - PURGE FLAGS (3 opsi pilhan user — default SEMUA FALSE, retain untuk redeploy):
      * --purge-data   : hapus HANYA data persist (grafana.db, prometheus TSDB, node_exporter textfile_dir)
      * --purge-config : hapus HANYA config workdirs (/etc/grafana, /etc/prometheus, /etc/node_exporter, /etc/agra)
      * --purge-all    : ALIAS set BOTH (--purge-data + --purge-config) = hapus SEMUA state service (data+config)

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
    "DAN JIKA MENGGUNAKAN --purge-data/--purge-config/--purge-all MAKA "
    "SEMUA DATA GRAFANA DB, PROMETHEUS TSDB, DAN CONFIG WORKDIRS "
    "(/etc/grafana /etc/prometheus /etc/node_exporter /etc/agra) "
    "TIDAK BISA DIKEMBALIKAN."
)


def setup_parser(subparsers: "argparse._SubParsersAction") -> argparse.ArgumentParser:
    p = subparsers.add_parser(
        "destroy", aliases=["remove", "teardown", "uninstall"],
        help="Destroy / uninstall monitoring stack services dari node (DEFAULT: retain data+config, TIDAK purge apapun).",
        description=f"Remove agra service containers/systemd units. SAFETY 2-LAYER (RULES §8): (1) CLI ABORT tanpa flag --yes-i-really-mean-it. (2) Playbook assert destroy_confirm=true. PURGE FLAGS (3 opsi — default OFF semua, state ditahan untuk redeploy): --purge-data (HANYA data persist), --purge-config (HANYA config workdirs /etc/<service>), --purge-all (alias DATA+CONFIG sekaligus).",
    )
    p.add_argument("-i", "--inventory")
    p.add_argument("-l", "--limit")
    p.add_argument(
        "--purge-data",
        action="store_true",
        dest="destroy_purge_data",
        help="PURGE TIPE 1: HAPUS HANYA data persist (grafana.db, prometheus tsdb, node_exporter textfile_dir). Config /etc/<service> DITAHAN.",
    )
    p.add_argument(
        "--purge-config",
        action="store_true",
        dest="destroy_purge_config",
        help="PURGE TIPE 2: HAPUS HANYA config workdirs service: /etc/grafana, /etc/prometheus, /etc/node_exporter, /etc/agra. Data persist (database/tsdb) DITAHAN.",
    )
    p.add_argument(
        "--purge-all",
        action="store_true",
        dest="purge_all",
        help="PURGE TIPE 3 (ALIAS): SET BOTH --purge-data + --purge-config. HAPUS SEMUA state (data persist + config workdirs). TIDAK BISA recovery apapun setelah ini.",
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
    purge_data_eff = bool(getattr(args, "destroy_purge_data", False) or getattr(args, "purge_all", False))
    purge_config_eff = bool(getattr(args, "destroy_purge_config", False) or getattr(args, "purge_all", False))

    if not getattr(args, "yes_i_really_mean_it", False):
        error("DESTROY DIBLOKIR (RULES §8 SAFETY LAYER 1: TIDAK ADA FLAG --yes-i-really-mean-it).")
        print(f"\n{RED}{BOLD}Operasi destroy BERSIFAT DESTRUKTIF.{RESET}")
        print(f"Untuk melanjutkan, TAMBAHKAN FLAG: {YELLOW}{BOLD}--yes-i-really-mean-it{RESET}")
        print(f"Contoh: {MAGENTA}agra destroy --yes-i-really-mean-it{RESET}")
        print(f"Contoh FULL PURGE (data+config): {MAGENTA}agra destroy --yes-i-really-mean-it --purge-all{RESET}")
        if purge_data_eff:
            print(f"{RED}  + purge_data AKTIF → SELURUH data persist (grafana.db, prometheus TSDB) AKAN DIHAPUS PERMANEN.{RESET}")
        else:
            print(f"{YELLOW}  + purge_data TIDAK AKTIF → data_dir service DITAHAN (aman redeploy nanti tanpa kehilangan data).{RESET}")
        if purge_config_eff:
            print(f"{RED}  + purge_config AKTIF → SELURUH config workdirs (/etc/grafana /etc/prometheus /etc/node_exporter /etc/agra) AKAN DIHAPUS PERMANEN.{RESET}")
        else:
            print(f"{YELLOW}  + purge_config TIDAK AKTIF → config workdirs /etc/<service> DITAHAN (aman redeploy nanti tanpa reconfig).{RESET}")
        print(f"\n{RED}Ansible TIDAK dipanggil sama sekali di abort ini.{RESET}")
        return 1

    interactive = (os.environ.get("AGRA_NON_INTERACTIVE", "") != "1") and not getattr(args, "auto_yes", False) and not getattr(args, "yes_i_really_mean_it", False)
    if interactive:
        section(f"{RED}{BOLD}DESTROY — KONFIRMASI AKHIR (typed sentence WAJIB){RESET}")
        warn(f"purge_data = {'ON (hapus data persist)' if purge_data_eff else 'OFF (data ditahan)'}")
        warn(f"purge_config = {'ON (hapus config workdirs /etc/<service>)' if purge_config_eff else 'OFF (config ditahan)'}")
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
    if purge_data_eff and purge_config_eff:
        warn(f"{RED}--purge-all AKTIF (DATA + CONFIG): SEMUA state (grafana.db / prom tsdb / /etc/grafana / /etc/prometheus / /etc/node_exporter / /etc/agra) AKAN DIHAPUS PERMANEN{RESET}")
    else:
        if purge_data_eff:
            warn(f"{RED}--purge-data AKTIF: data persist (grafana_data_dir & prometheus_data_dir) AKAN DIHAPUS PERMANEN{RESET}")
        if purge_config_eff:
            warn(f"{RED}--purge-config AKTIF: config workdirs (/etc/grafana /etc/prometheus /etc/node_exporter /etc/agra) AKAN DIHAPUS PERMANEN{RESET}")

    extra_vars = {
        "destroy_confirm": True,
        "destroy_purge_data": purge_data_eff,
        "destroy_purge_config": purge_config_eff,
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
