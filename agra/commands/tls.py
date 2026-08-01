"""agra tls — subcommands regenerate & info/check.

tls regenerate = Hapus self-signed cert default (trigger creates guard idempotent),
                 lalu re-run deploy --tags nginx dengan tls_self_signed_generate=true.
                 SAFETY: custom cert (user-provided) TIDAK boleh di-regenerate otomatis.

tls info / check = Pure Python panggil openssl CLI, parse & print detail cert
                   (issuer, subject, CN, SAN, dates, days_remaining) + warning expiry.
"""
from __future__ import annotations
import argparse
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from agra.utils.colors import info, warn, error, section, debug, BOLD, RESET, RED, YELLOW, GREEN, CYAN, MAGENTA, GRAY
from agra.utils.paths import resolve_inventory, ansible_env, load_globals_yaml
from agra.utils.run_playbook import run_playbook, _check_ansible_available
from agra.constants import CONFIG_DIR


NGINX_CONFIG_DIR_SSL_DEFAULT = "/etc/nginx/ssl"
DEFAULT_CERT_PATH = f"{NGINX_CONFIG_DIR_SSL_DEFAULT}/agra.crt"
DEFAULT_KEY_PATH = f"{NGINX_CONFIG_DIR_SSL_DEFAULT}/agra.key"
DEFAULT_DHPARAM_PATH = f"{NGINX_CONFIG_DIR_SSL_DEFAULT}/dhparam.pem"
CUSTOM_CERT_OVERRIDE_PATH = CONFIG_DIR / "nginx" / "ssl" / "agra.crt"

REGENERATE_CONFIRM = "REGENERATE"


def _run_ansible_adhoc_delete(inventory: Optional[str], limit: Optional[str], paths_to_delete: List[str]) -> int:
    """Jalankan ansible ad-hoc (module file state=absent) untuk hapus file cert di monitoring hosts."""
    _check_ansible_available()
    try:
        inv_path = resolve_inventory(inventory)
    except FileNotFoundError as e:
        error(str(e))
        return 2

    argv: List[str] = ["ansible", "monitoring"]
    argv += ["-i", str(inv_path)]
    if limit:
        argv += ["--limit", limit]

    joined_paths = ",".join(paths_to_delete)
    argv += [
        "-m", "file",
        "-a", f"path={{ item }} state=absent",
        "--forks", "10",
    ]
    argv += ["--extra-vars", f'{{"item_list": [{", ".join(repr(p) for p in paths_to_delete)}]}}']

    env = ansible_env()

    section(f"Hapus file cert/key default di hosts inventory: {joined_paths}")
    print(f"{BOLD}Inventory:{RESET} {inv_path}")
    print(f"{BOLD}Command   :{RESET} {shlex.join(argv)}")

    paths_json = "[" + ",".join(f'"{p}"' for p in paths_to_delete) + "]"

    argv2: List[str] = ["ansible", "monitoring"]
    argv2 += ["-i", str(inv_path)]
    if limit:
        argv2 += ["--limit", limit]
    argv2 += [
        "-m", "ansible.builtin.file",
        "-a", f"path={{{{ item }}}} state=absent",
        "--forks", "10",
        "-e", f'{{"items_to_delete": {paths_json}}}',
    ]

    loop_wrapper = [
        "ansible", "monitoring",
        "-i", str(inv_path),
    ]
    if limit:
        loop_wrapper += ["--limit", limit]
    loop_wrapper += [
        "-m", "ansible.builtin.shell",
        "-a", f"rm -f {' '.join(paths_to_delete)} && echo 'deleted OK:' {' '.join(paths_to_delete)}",
        "--forks", "10",
    ]

    final_argv = loop_wrapper
    print(f"{BOLD}Effective :{RESET} {shlex.join(final_argv)}")

    try:
        proc = subprocess.Popen(
            final_argv,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=True,
            text=True,
        )
    except FileNotFoundError as e:
        error(f"Failed exec ansible: {e}")
        return 2

    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            s = line.rstrip()
            if any(x in s.lower() for x in ("failed", "fatal", "error")) and "skipped" not in s.lower():
                print(f"{BOLD}{s}{RESET}", flush=True)
            else:
                print(s, flush=True)
    except KeyboardInterrupt:
        warn("Interrupted by user (Ctrl+C). Terminating ansible...")
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        return 130

    rc = proc.wait()
    if rc == 0:
        info("File cert/key default berhasil dihapus di semua hosts monitoring.", bold=True)
    else:
        warn(f"Ansible ad-hoc delete selesai dengan rc={rc} (beberapa host mungkin belum punya file). Lanjut ke regenerate...")
    return 0


def _detect_custom_cert() -> Tuple[bool, str]:
    """Cek dua kondisi OR apakah user pakai custom cert (bukan self-signed default agra).

    Returns: (is_custom, reason_string)
    """
    globals_data = load_globals_yaml()

    tls_cert_from_globals = globals_data.get("tls_cert_path", "") or ""
    nginx_config_dir = globals_data.get("nginx_config_dir", "/etc/nginx")
    default_cert_computed = f"{nginx_config_dir.rstrip('/')}/ssl/agra.crt"

    cond_a_reason = ""
    cond_a = False
    if isinstance(tls_cert_from_globals, str) and tls_cert_from_globals.strip():
        normalized_user = tls_cert_from_globals.strip()
        normalized_default = DEFAULT_CERT_PATH
        normalized_default2 = default_cert_computed
        if normalized_user != normalized_default and normalized_user != normalized_default2:
            cond_a = True
            cond_a_reason = (
                f"tls_cert_path di globals.yml diset ke CUSTOM PATH: '{normalized_user}' "
                f"(default agra: '{normalized_default}')"
            )

    cond_b_reason = ""
    cond_b = False
    try:
        if CUSTOM_CERT_OVERRIDE_PATH.exists():
            cond_b = True
            cond_b_reason = f"Custom override cert ADA di control node: {CUSTOM_CERT_OVERRIDE_PATH}"
    except Exception:
        pass

    if cond_a or cond_b:
        reasons = []
        if cond_a_reason:
            reasons.append(cond_a_reason)
        if cond_b_reason:
            reasons.append(cond_b_reason)
        return True, " ; ".join(reasons)

    return False, ""


def cmd_regenerate(args: argparse.Namespace) -> int:
    section("agra tls regenerate — Self-Signed Certificate Regenerate")

    is_custom, reason = _detect_custom_cert()
    if is_custom:
        error("Custom TLS certificate TIDAK dikelola oleh agra regenerate (anda menyediakan cert sendiri).")
        print(f"\n{YELLOW}{BOLD}Alasan deteksi custom cert:{RESET}")
        print(f"  {GRAY}- {reason}{RESET}")
        print(f"\n{RED}{BOLD}Custom TLS certificate TIDAK dikelola oleh agra regenerate (anda menyediakan cert cert sendiri).{RESET}")
        print(f"{YELLOW}Update cert custom anda MANUAL, lalu jalankan:{RESET}")
        print(f"  {MAGENTA}{BOLD}agra deploy --tags nginx{RESET}")
        print(f"untuk restart service nginx dan reload cert baru.")
        return 1

    interactive = (os.environ.get("AGRA_NON_INTERACTIVE", "") != "1") and not getattr(args, "auto_yes", False)
    if interactive:
        section(f"{RED}{BOLD}TLS REGENERATE — KONFIRMASI (typed sentence WAJIB){RESET}")
        warn("Perintah ini AKAN MENGHAPUS cert self-signed default LALU regenerate cert BARU via role nginx.")
        warn(f"Cert default yang akan dihapus: {DEFAULT_CERT_PATH} + {DEFAULT_KEY_PATH}")
        if getattr(args, "include_dhparam", False):
            warn(f"{RED}+ --include-dhparam AKTIF: dhparam.pem JUGA akan dihapus & regenerate (2048bit ~10-60s per host){RESET}")
        else:
            info("dhparam.pem TIDAK dihapus (default, karena generate lama). Gunakan --include-dhparam untuk regenerate DH juga.")
        print(f"\n{YELLOW}{BOLD}Ketik KATA BERIKUT INI PERSIS (case-sensitive=UPPERCASE), lalu tekan ENTER:{RESET}\n")
        print(f"    {MAGENTA}{BOLD}{REGENERATE_CONFIRM}{RESET}\n")
        try:
            resp = input(f"{YELLOW}> ").strip()
        except (EOFError, KeyboardInterrupt):
            error("\nTLS regenerate dibatalkan user (Ctrl+C).")
            return 1
        if resp != REGENERATE_CONFIRM:
            error(f"KONFIRMASI TIDAK COCOK. Expected: '{REGENERATE_CONFIRM}' (UPPERCASE), got: '{resp}'. TLS regenerate dibatalkan.")
            return 1
        info("Konfirmasi cocok. Lanjutkan ke penghapusan cert default.")

    paths_to_delete: List[str] = [DEFAULT_CERT_PATH, DEFAULT_KEY_PATH]
    if getattr(args, "include_dhparam", False):
        paths_to_delete.append(DEFAULT_DHPARAM_PATH)
        warn(f"{RED}--include-dhparam AKTIF: dhparam.pem IKUT dihapus (generate ulang 2048bit membutuhkan waktu ~10-60s per host){RESET}")

    info(f"File yang akan dihapus di monitoring hosts: {', '.join(paths_to_delete)}")
    rc_del = _run_ansible_adhoc_delete(
        inventory=getattr(args, "inventory", None),
        limit=getattr(args, "limit", None),
        paths_to_delete=paths_to_delete,
    )
    if rc_del != 0 and rc_del != 130:
        warn(f"Ansible ad-hoc delete selesai dengan rc={rc_del} (mungkin file belum ada). Lanjut regenerate cert baru...")
    elif rc_del == 130:
        return 130

    section("RUN: deploy playbook dengan tags=nginx + extra_vars tls_self_signed_generate=true")
    info("Extra var tls_self_signed_generate=true memastikan block self-signed di role nginx AKTIF (creates: tidak ada → regenerate baru).")
    info("Hanya role nginx yang di-re-run (idempotent creates guard → TRIGGER regenerate).")

    extra_vars: Dict[str, Any] = {
        "tls_self_signed_generate": True,
    }

    rc_pb = run_playbook(
        "deploy",
        inventory=getattr(args, "inventory", None),
        tags=["nginx"],
        skip_tags=None,
        limit=getattr(args, "limit", None),
        extra_vars=extra_vars,
        extra_vars_raw=getattr(args, "extra_vars", None) or None,
        verbosity=getattr(args, "verbose", 0),
        description="Re-run deploy playbook TAGS=nginx SAJA (self-signed cert regenerate via creates guard idempotent)",
        abort_on_nonzero=False,
    )

    if rc_pb == 0:
        section("Regenerate selesai — Cek tanggal cert BARU via openssl x509 -dates")
        local_cert = Path(DEFAULT_CERT_PATH)
        if local_cert.exists():
            info(f"Cert default ditemukan di control node ({DEFAULT_CERT_PATH}), cek via openssl local:")
            rc_d, out_d, _ = _run_openssl(["x509", "-in", str(local_cert), "-noout", "-dates"])
            if rc_d == 0:
                print(out_d.strip())
            cn_tmp = ""
            rc_sn, out_sn, _ = _run_openssl(["x509", "-in", str(local_cert), "-noout", "-subject", "-issuer"])
            if rc_sn == 0:
                print(out_sn.strip())
        else:
            info(f"Cert file tidak ada di control node ({DEFAULT_CERT_PATH}) — wajar jika deploy di remote host.")
            info("Jalankan perintah berikut di managed host untuk cek cert baru:")
            print(f"  {MAGENTA}openssl x509 -in {DEFAULT_CERT_PATH} -noout -dates -subject -issuer{RESET}")
            info("Atau jalankan: `agra tls info --cert-path <path>` jika cert dicopy ke control node.")

    return rc_pb


def _run_openssl(args_list: List[str], check_stderr: bool = False) -> Tuple[int, str, str]:
    """Run openssl CLI, return (rc, stdout, stderr)."""
    import shutil
    if shutil.which("openssl") is None:
        error("openssl CLI TIDAK TERSEDIA di PATH. Install openssl terlebih dahulu.")
        return (127, "", "openssl not found")
    try:
        proc = subprocess.run(
            ["openssl"] + args_list,
            capture_output=True,
            text=True,
            check=False,
        )
        return (proc.returncode, proc.stdout or "", proc.stderr or "")
    except Exception as e:
        return (1, "", str(e))


def _parse_openssl_date(s: str) -> Optional[datetime]:
    """Parse openssl date format seperti 'Jan  1 00:00:00 2030 GMT' → datetime aware UTC."""
    s = s.strip()
    fmts = [
        "%b %d %H:%M:%S %Y %Z",
        "%b %e %H:%M:%S %Y %Z",
        "%Y-%m-%d %H:%M:%S%z",
    ]
    for fmt in fmts:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            pass
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(s)
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
    except Exception:
        pass
    return None


def _resolve_cert_path_from_args(args: argparse.Namespace) -> str:
    """Resolve cert path untuk tls info: --cert-path > globals.yml > default."""
    explicit = getattr(args, "cert_path", None)
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    g = load_globals_yaml()
    from_globals = g.get("tls_cert_path", "") or ""
    if isinstance(from_globals, str) and from_globals.strip():
        return from_globals.strip()
    return DEFAULT_CERT_PATH


def _sanitize(s: str) -> str:
    return s.replace("\x00", "").strip()


def cmd_info(args: argparse.Namespace) -> int:
    section("agra tls info — TLS Certificate Information")

    cert_path = _resolve_cert_path_from_args(args)
    print(f"{BOLD}Cert path (resolved):{RESET} {CYAN}{cert_path}{RESET}")

    p = Path(cert_path)
    if not p.exists():
        warn(f"File cert TIDAK DITEMUKAN di: {cert_path}")
        print(f"{GRAY}Tips: Jika deploy via docker, cert ada di dalam container nginx (jalankan di host yang menjalankan nginx native, atau copy keluar dulu).{RESET}")
        print(f"{GRAY}Tips: Gunakan --cert-path /path/custom.crt untuk cek cert di lokasi lain.{RESET}")
        return 1

    rc, out, err = _run_openssl(["x509", "-in", str(p), "-noout", "-issuer", "-subject", "-dates", "-ext", "subjectAltName"])
    if rc != 0:
        error(f"Gagal baca cert via openssl x509 (rc={rc}).")
        if err.strip():
            print(f"{RED}{err.strip()}{RESET}")
        return rc

    issuer = ""
    subject = ""
    not_before = ""
    not_after = ""
    san_str = ""

    for raw_line in out.splitlines():
        line = raw_line.strip()
        if line.startswith("issuer="):
            issuer = _sanitize(line[len("issuer="):])
        elif line.startswith("subject="):
            subject = _sanitize(line[len("subject="):])
        elif line.startswith("notBefore="):
            not_before = _sanitize(line[len("notBefore="):])
        elif line.startswith("notAfter="):
            not_after = _sanitize(line[len("notAfter="):])
        elif "Subject Alternative Name" in line or line.startswith("DNS:") or line.startswith("IP Address:") or line.startswith("IP:"):
            san_str += (" " if san_str else "") + line

    if not san_str:
        rc2, out2, _ = _run_openssl(["x509", "-in", str(p), "-noout", "-text"])
        if rc2 == 0:
            in_san = False
            for raw_line in out2.splitlines():
                line = raw_line.strip()
                if "Subject Alternative Name" in line:
                    in_san = True
                    continue
                if in_san:
                    if ":" not in line or line.startswith("X509v3"):
                        break
                    san_str += (" " if san_str else "") + line
                    in_san = False if "," not in line and (line.startswith("DNS:") or line.startswith("IP")) else True

    cn = ""
    m = re.search(r'(?:^|[,/])\s*CN\s*=\s*([^,/]+)', subject)
    if m:
        cn = _sanitize(m.group(1))
    else:
        m2 = re.search(r'CN\s*=\s*([^\n,]+)', subject)
        if m2:
            cn = _sanitize(m2.group(1))

    san_list: List[str] = []
    for m in re.finditer(r'(DNS|IP(?: Address)?):\s*([^,\s]+)', san_str):
        san_list.append(f"{m.group(1).replace(' Address', '')}:{m.group(2)}")

    dt_nb = _parse_openssl_date(not_before) if not_before else None
    dt_na = _parse_openssl_date(not_after) if not_after else None
    days_remaining: Optional[int] = None
    now = datetime.now(timezone.utc)
    if dt_na is not None:
        delta = dt_na - now
        days_remaining = int(delta.total_seconds() // 86400)

    print()
    print(f"{BOLD}{'─' * 50}{RESET}")
    print(f"  {BOLD}File Path      :{RESET} {CYAN}{cert_path}{RESET}")
    print(f"  {BOLD}Issuer         :{RESET} {_sanitize(issuer) or '-'}")
    print(f"  {BOLD}Subject        :{RESET} {_sanitize(subject) or '-'}")
    print(f"  {BOLD}Common Name    :{RESET} {GREEN}{BOLD}{cn or '-'}{RESET}")
    print(f"  {BOLD}SAN            :{RESET} {', '.join(san_list) if san_list else '-'}")
    print(f"  {BOLD}notBefore      :{RESET} {not_before or '-'}")
    print(f"  {BOLD}notAfter       :{RESET} {not_after or '-'}")
    if days_remaining is not None:
        if days_remaining < 0:
            print(f"  {BOLD}Days Remaining :{RESET} {RED}{BOLD}{days_remaining} days (EXPIRED){RESET}")
        elif days_remaining < 7:
            print(f"  {BOLD}Days Remaining :{RESET} {RED}{BOLD}{days_remaining} days (KURANG DARI 7 HARI — SEGERA REGENERATE CERT){RESET}")
        elif days_remaining < 30:
            print(f"  {BOLD}Days Remaining :{RESET} {YELLOW}{BOLD}{days_remaining} days (< 30 hari — segera regenerate cert){RESET}")
        else:
            print(f"  {BOLD}Days Remaining :{RESET} {GREEN}{BOLD}{days_remaining} days{RESET}")
    else:
        print(f"  {BOLD}Days Remaining :{RESET} - (gagal parse notAfter)")
    print(f"{BOLD}{'─' * 50}{RESET}")

    if days_remaining is not None:
        if days_remaining < 0:
            print()
            error("CERT SUDAH EXPIRED!")
            is_custom, _ = _detect_custom_cert()
            if is_custom:
                warn("Cert ini adalah CUSTOM cert (user-provided cert). Update cert custom anda MANUAL, lalu jalankan:")
                print(f"  {MAGENTA}{BOLD}agra deploy --tags nginx{RESET}")
            else:
                warn("Gunakan perintah berikut untuk regenerate self-signed cert default:")
                print(f"  {MAGENTA}{BOLD}agra tls regenerate{RESET}")
            return 2
        elif days_remaining < 7:
            print()
            error("CERT AKAN EXPIRED KURANG DARI 7 HARI! (RED CRITICAL)")
            is_custom, _ = _detect_custom_cert()
            if is_custom:
                warn("Cert ini adalah CUSTOM cert. Update cert custom anda MANUAL, lalu jalankan:")
                print(f"  {MAGENTA}{BOLD}agra deploy --tags nginx{RESET}")
            else:
                warn("Regenerate self-signed cert default SEKARANG:")
                print(f"  {MAGENTA}{BOLD}agra tls regenerate --yes{RESET}")
            return 2
        elif days_remaining < 30:
            print()
            warn("CERT AKAN EXPIRED KURANG DARI 30 HARI! (YELLOW WARNING) — segera regenerate cert.")
            is_custom, _ = _detect_custom_cert()
            if is_custom:
                info("Cert ini adalah CUSTOM cert. Update custom cert manual lalu `agra deploy --tags nginx`.")
            else:
                info("Regenerate self-signed cert default: `agra tls regenerate`")
            return 0

    print()
    info("Cert validity OK.")
    return 0


def setup_parser(subparsers: "argparse._SubParsersAction") -> argparse.ArgumentParser:
    p = subparsers.add_parser(
        "tls",
        help="TLS certificate management (subcommands: regenerate | info | check | status).",
        description="TLS / SSL certificate lifecycle: agra tls regenerate (hapus self-signed default & regenerate via role nginx creates guard) | agra tls info / check (baca detail cert via openssl + expiry warning).",
    )
    p.add_argument("-i", "--inventory", dest="inventory")
    p.add_argument("-l", "--limit", dest="limit")
    p.add_argument("-e", "--extra-vars", action="append", default=[], dest="extra_vars")
    p.add_argument("-v", "--verbose", action="count", default=0, dest="verbose")

    sub = p.add_subparsers(dest="tls_command", required=False, metavar="{regenerate | info | check | status}")
    sub.default = "info"

    p_regen = sub.add_parser(
        "regenerate", aliases=["regen"],
        help="(SELF-SIGNED DEFAULT ONLY) Hapus cert self-signed default lalu re-run role nginx untuk regenerate cert baru via creates guard idempotent. SAFETY: Custom cert user TIDAK boleh di-regenerate.",
    )
    p_regen.add_argument("-i", "--inventory", dest="inventory")
    p_regen.add_argument("-l", "--limit", dest="limit")
    p_regen.add_argument(
        "--include-dhparam",
        action="store_true",
        dest="include_dhparam",
        help="HAPUS JUGA dhparam.pem & regenerate (2048bit ~10-60s per host). DEFAULT FALSE: dhparam.pem di-skip karena generate lama.",
    )
    p_regen.add_argument("-y", "--yes", dest="auto_yes", action="store_true", help="Skip interactive typed 'REGENERATE' confirm (CI: AGRA_NON_INTERACTIVE=1 juga setara).")
    p_regen.add_argument("-e", "--extra-vars", action="append", default=[], dest="extra_vars")
    p_regen.add_argument("-v", "--verbose", action="count", default=0, dest="verbose")
    p_regen.set_defaults(func=cmd_regenerate)

    p_info = sub.add_parser(
        "info", aliases=["check", "status"],
        help="Print detail TLS certificate: path, issuer, subject, CN, SAN, notBefore, notAfter, days_remaining + WARNING expiry < 30h | < 7d.",
    )
    p_info.add_argument("-c", "--cert-path", dest="cert_path", help=f"Path cert file (default: resolved dari globals.yml tls_cert_path atau {DEFAULT_CERT_PATH})")
    p_info.set_defaults(func=cmd_info)

    p.set_defaults(func=cmd_info, tls_command="info")
    return p
