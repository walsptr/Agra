"""`agra genpwd [--force --yes-i-really-mean-it]` — generate random password, tulis /etc/agra/passwords.yml.
Safety: field yang sudah terisi tidak ditimpa. --force mengganti SEMUA secret yang
dibuat agra (destruktif: grafana_secret_key baru = data terenkripsi Grafana tidak
terbaca), jadi wajib --yes-i-really-mean-it (RULES §8).
"""
from __future__ import annotations
import argparse
from agra.utils.colors import error, info, warn
from agra.utils.run_playbook import run_playbook


def setup_parser(subparsers: "argparse._SubParsersAction") -> argparse.ArgumentParser:
    p: argparse.ArgumentParser = subparsers.add_parser(
        "genpwd", aliases=["generate-passwords", "gen-passwords"],
        help="Generate random passwords for secrets file etc/agra/passwords.yml",
        description="Generate random secrets ke /etc/agra/passwords.yml (plaintext chmod 0600, owner user pemanggil). Field yang sudah terisi tidak ditimpa kecuali --force.",
    )
    p.add_argument("--force", action="store_true",
                   help="Generate ulang SEMUA secret yang dibuat agra (file lama di-backup). Wajib --yes-i-really-mean-it.")
    p.add_argument("--yes-i-really-mean-it", dest="yes_i_really_mean_it", action="store_true",
                   help="Konfirmasi --force (destruktif).")
    p.add_argument("-v", "--verbose", action="count", default=0)
    p.set_defaults(func=run_genpwd)
    return p


def run_genpwd(args: argparse.Namespace) -> int:
    from agra.constants import PASSWORDS_FILE

    if args.force and not getattr(args, "yes_i_really_mean_it", False):
        error("genpwd --force DIBLOKIR: tanpa --yes-i-really-mean-it.")
        warn("--force mengganti semua secret: grafana_secret_key baru membuat password datasource dan "
             "data terenkripsi lain di database Grafana tidak terbaca; grafana_database_password baru "
             "harus di-set juga di database eksternal; semua sesi login berakhir.")
        warn("Untuk mengisi field yang kosong saja: agra genpwd (tanpa --force).")
        return 1

    evars = {"genpwd_force": bool(args.force), "genpwd_confirm": bool(getattr(args, "yes_i_really_mean_it", False))}

    rc = run_playbook(
        "genpwd",
        extra_vars=evars,
        verbosity=args.verbose,
        description="Generate Random Passwords (agra genpwd)",
        abort_on_nonzero=False,
        load_etc_vars=False,
    )
    if rc == 0:
        info("Passwords generated OK di " + str(PASSWORDS_FILE), bold=True)
    return rc
