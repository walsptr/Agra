"""agra destroy - Hapus service monitoring. SAFETY 2 LAYER.

LAYER 1 (CLI, SEBELUM ansible pernah diinvoke): WAJIB flag --yes-i-really-mean-it
  (RULES §8). Tanpa flag → exit 1, ansible TIDAK PERNAH dipanggil. Flag ini satu-
  satunya konfirmasi — tidak ada prompt interaktif tambahan.
  PURGE FLAGS (default SEMUA OFF — data & config ditahan untuk redeploy):
      * --purge-data   : hapus HANYA data persist (grafana.db, prometheus TSDB, node_exporter textfile_dir)
      * --purge-config : hapus HANYA config workdirs, per grup: /etc/nginx + /etc/keepalived
                         di [monitoring], /etc/grafana di [grafana], /etc/prometheus di
                         [prometheus], /etc/node_exporter di [node_exporter]
      * --purge-all    : --purge-data + --purge-config
  Nilai purge hanya dari flag di atas: -e destroy_purge_* ditolak.

LAYER 2 (playbook destroy.yml): assert destroy_confirm=true sebagai defense-in-depth.
"""
from __future__ import annotations
import argparse
from agra.utils.colors import warn, error, section, BOLD, RESET, RED, YELLOW, MAGENTA
from agra.utils.cli_args import add_inventory_argument
from agra.utils.run_playbook import check_extra_vars_conflicts, run_playbook


def setup_parser(subparsers: "argparse._SubParsersAction") -> argparse.ArgumentParser:
    p = subparsers.add_parser(
        "destroy", aliases=["remove", "teardown", "uninstall"],
        help="Destroy / uninstall monitoring stack services dari node (DEFAULT: retain data+config, TIDAK purge apapun).",
        description="Remove agra service containers. SAFETY 2-LAYER: (1) CLI ABORT tanpa flag --yes-i-really-mean-it. (2) Playbook assert destroy_confirm=true. PURGE FLAGS (3 opsi — default OFF semua, state ditahan untuk redeploy): --purge-data (HANYA data persist), --purge-config (HANYA config workdirs /etc/<service>), --purge-all (alias DATA+CONFIG sekaligus).",
    )
    add_inventory_argument(p)
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
        help="PURGE TIPE 2: HAPUS HANYA config workdirs, hanya di host yang grupnya men-deploy service itu: /etc/nginx + /etc/keepalived di [monitoring], /etc/grafana di [grafana], /etc/prometheus di [prometheus], /etc/node_exporter di [node_exporter]. Host node_exporter-only tidak kehilangan /etc/nginx miliknya. /etc/agra di control node tidak disentuh; data persist DITAHAN.",
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
    p.add_argument("-t", "--tags", action="append", default=[])
    p.add_argument("--skip-tags", action="append", default=[])
    p.add_argument("-e", "--extra-vars", action="append", default=[])
    p.add_argument("-v", "--verbose", action="count", default=0)
    p.set_defaults(func=run_destroy)
    return p


DESTROY_CLI_VARS = ("destroy_confirm", "destroy_purge_data", "destroy_purge_config")


def run_destroy(args: argparse.Namespace) -> int:
    # Purge hanya lewat flag --purge-* yang tampil di konfirmasi, bukan -e.
    check_extra_vars_conflicts(args.extra_vars, DESTROY_CLI_VARS)
    purge_data_eff = bool(getattr(args, "destroy_purge_data", False) or getattr(args, "purge_all", False))
    purge_config_eff = bool(getattr(args, "destroy_purge_config", False) or getattr(args, "purge_all", False))

    if not getattr(args, "yes_i_really_mean_it", False):
        error("DESTROY DIBLOKIR (SAFETY LAYER 1: TIDAK ADA FLAG --yes-i-really-mean-it).")
        print(f"\n{RED}{BOLD}Operasi destroy BERSIFAT DESTRUKTIF.{RESET}")
        print(f"Untuk melanjutkan, TAMBAHKAN FLAG: {YELLOW}{BOLD}--yes-i-really-mean-it{RESET}")
        print(f"Contoh: {MAGENTA}agra destroy --yes-i-really-mean-it{RESET}")
        print(f"Contoh FULL PURGE (data+config): {MAGENTA}agra destroy --yes-i-really-mean-it --purge-all{RESET}")
        if purge_data_eff:
            print(f"{RED}  + purge_data AKTIF → SELURUH data persist (grafana.db, prometheus TSDB) AKAN DIHAPUS PERMANEN.{RESET}")
        else:
            print(f"{YELLOW}  + purge_data TIDAK AKTIF → data_dir service DITAHAN (aman redeploy nanti tanpa kehilangan data).{RESET}")
        if purge_config_eff:
            print(f"{RED}  + purge_config AKTIF → config workdirs agra (per grup: /etc/nginx + /etc/keepalived hanya di [monitoring]) AKAN DIHAPUS PERMANEN.{RESET}")
        else:
            print(f"{YELLOW}  + purge_config TIDAK AKTIF → config workdirs /etc/<service> DITAHAN (aman redeploy nanti tanpa reconfig).{RESET}")
        print(f"\n{RED}Ansible TIDAK dipanggil sama sekali di abort ini.{RESET}")
        return 1

    section("RUN: destroy playbook (Safety LAYER 2 di-playbook assert destroy_confirm=true)")
    if purge_data_eff and purge_config_eff:
        warn(f"{RED}--purge-all AKTIF (DATA + CONFIG): SEMUA state agra (grafana.db / prom tsdb / config workdirs per grup) AKAN DIHAPUS PERMANEN{RESET}")
    else:
        if purge_data_eff:
            warn(f"{RED}--purge-data AKTIF: data persist (grafana_data_dir & prometheus_data_dir) AKAN DIHAPUS PERMANEN{RESET}")
        if purge_config_eff:
            warn(f"{RED}--purge-config AKTIF: config workdirs agra per grup (/etc/nginx + /etc/keepalived hanya di [monitoring]) AKAN DIHAPUS PERMANEN{RESET}")

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
