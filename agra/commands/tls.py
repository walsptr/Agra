"""agra tls — subcommands regenerate & info/check.

tls regenerate = `agra certificates generate --force` di control node, lalu
                 `agra deploy --tags nginx` untuk mendistribusikan cert baru ke
                 managed host (copy berbasis checksum — tidak perlu hapus file
                 lama di host). Custom cert (user-provided) tidak di-regenerate.

tls info / check = alias `agra certificates info`.
"""
from __future__ import annotations
import argparse
import os

from agra.commands import certificates
from agra.utils.colors import info, warn, error, section, BOLD, RESET, YELLOW, MAGENTA, GRAY
from agra.utils.paths import load_globals_file
from agra.utils.cli_args import add_inventory_argument
from agra.utils.run_playbook import build_ansible_command, run_playbook

REGENERATE_CONFIRM = "REGENERATE"


def cmd_regenerate(args: argparse.Namespace) -> int:
    section("agra tls regenerate — Self-Signed Certificate Regenerate")

    g = load_globals_file()
    cert, key, _, _ = certificates._resolve_paths(args)
    is_custom, reason = certificates._detect_custom(g, cert, key)
    if is_custom:
        error("Custom TLS certificate tidak dikelola oleh agra regenerate (anda menyediakan cert sendiri).")
        print(f"  {GRAY}- {reason}{RESET}")
        print(f"Perbarui cert custom anda manual, lalu: {MAGENTA}{BOLD}agra deploy --tags nginx{RESET}")
        return 1

    deploy_kwargs = dict(
        inventory=getattr(args, "inventory", None),
        tags=["nginx"],
        limit=getattr(args, "limit", None),
        extra_vars_raw=getattr(args, "extra_vars", None) or None,
        verbosity=getattr(args, "verbose", 0),
    )
    # Semua yang bisa menggagalkan distribusi di control node (inventory,
    # globals/passwords, ansible, -e) dicek SEBELUM cert diganti — kalau gagal
    # sesudahnya, cert di control node sudah baru sementara host masih memakai
    # yang lama, dan cert lama tidak bisa dikembalikan.
    build_ansible_command("deploy", **deploy_kwargs)

    interactive = os.environ.get("AGRA_NON_INTERACTIVE", "") != "1" and not getattr(args, "auto_yes", False)
    if interactive:
        warn(f"Cert self-signed {cert} + key akan DIGANTI, lalu nginx di semua host [monitoring] di-reload.")
        try:
            resp = input(f"{YELLOW}Ketik '{BOLD}{REGENERATE_CONFIRM}{RESET}{YELLOW}' untuk melanjutkan: ").strip()
        except (EOFError, KeyboardInterrupt):
            error("\nTLS regenerate dibatalkan user.")
            return 1
        if resp != REGENERATE_CONFIRM:
            error(f"Konfirmasi tidak cocok (input={resp!r}). TLS regenerate dibatalkan.")
            return 1

    args.force = True
    rc = certificates.cmd_generate(args)
    if rc != 0:
        error(f"agra certificates generate --force gagal (rc={rc}). Cert di managed host tidak diubah.")
        return rc

    info("Cert baru siap di control node. Distribusi ke managed host via deploy --tags nginx ...")
    rc = run_playbook(
        "deploy",
        **deploy_kwargs,
        description="Deploy --tags nginx (copy cert baru control node → managed host + reload nginx)",
        abort_on_nonzero=False,
    )
    if rc != 0:
        error(f"Cert baru sudah ada di {cert}, tetapi belum sampai ke semua host. Perbaiki penyebabnya, lalu "
              "jalankan ulang distribusinya saja (JANGAN regenerate lagi): agra deploy -i <inventory> --tags nginx")
    return rc


def setup_parser(subparsers: "argparse._SubParsersAction") -> argparse.ArgumentParser:
    p = subparsers.add_parser(
        "tls",
        help="TLS certificate management (subcommands: regenerate | info | check | status).",
        description="agra tls regenerate (self-signed: generate --force + deploy --tags nginx) | agra tls info (alias agra certificates info).",
    )
    add_inventory_argument(p)
    p.add_argument("-l", "--limit", dest="limit")
    p.add_argument("-e", "--extra-vars", action="append", default=[], dest="extra_vars")
    p.add_argument("-v", "--verbose", action="count", default=0, dest="verbose")

    sub = p.add_subparsers(dest="tls_command", required=False, metavar="{regenerate | info | check | status}")
    sub.default = "info"

    p_regen = sub.add_parser(
        "regenerate", aliases=["regen"],
        help="(Self-signed default saja) Generate ulang cert di control node lalu distribusi via deploy --tags nginx.",
    )
    # Opsi yang juga ada di `agra tls` — default milik parent (cli_args.py).
    add_inventory_argument(p_regen)
    p_regen.add_argument("-l", "--limit", dest="limit", default=argparse.SUPPRESS)
    p_regen.add_argument("--include-dhparam", action="store_true", dest="include_dhparam",
                         help="Generate ulang dhparam.pem juga (2048-bit, ~10-60s).")
    p_regen.add_argument("--days", type=int, default=None, dest="days",
                         help=f"Jumlah hari valid cert baru (default: tls_self_signed_days_valid di globals.yml, atau {certificates.DEFAULT_DAYS}).")
    p_regen.add_argument("--cn", dest="cn",
                         help="Override CN (default: grafana_domain > monitoring_vip > hostname).")
    p_regen.add_argument("-y", "--yes", dest="auto_yes", action="store_true",
                         help="Skip konfirmasi (CI: AGRA_NON_INTERACTIVE=1 setara).")
    p_regen.add_argument("-e", "--extra-vars", action="append", default=argparse.SUPPRESS, dest="extra_vars")
    p_regen.add_argument("-v", "--verbose", action="count", default=argparse.SUPPRESS, dest="verbose")
    p_regen.set_defaults(func=cmd_regenerate)

    p_info = sub.add_parser("info", aliases=["check", "status"],
                            help="Alias `agra certificates info`: issuer, CN, SAN, tanggal, sisa hari + warning expiry.")
    p_info.add_argument("-c", "--cert-path", dest="cert_path",
                        help=f"Path cert (default: tls_cert_path di globals.yml atau {certificates.DEFAULT_CERT})")
    p_info.set_defaults(func=certificates.cmd_info)

    p.set_defaults(func=certificates.cmd_info, tls_command="info")
    return p
