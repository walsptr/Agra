"""agra certificates — subcommands generate & info/check.
generate = self-signed RSA 2048 + x509 di control node /etc/agra/ssl (pre-deploy).
info/check = parse detail cert via openssl + expiry warning.

Berjalan sebagai operator user pemilik /etc/agra (ARCHITECTURE.md §8.2) —
tidak ada sudo / re-exec root. Masalah permission = perbaiki ownership.
"""
from __future__ import annotations
import argparse
import os
import re
import socket
import platform
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from agra.utils.colors import info, warn, error, section, BOLD, RESET, RED, YELLOW, GREEN, CYAN, MAGENTA, GRAY
from agra.utils.paths import load_globals_file
from agra.constants import AGRA_SSL_DIR, ETC_DIR, GLOBALS_FILE


DEFAULT_DAYS = 3650
DEFAULT_CERT = str(AGRA_SSL_DIR / "agra.crt")
DEFAULT_KEY = str(AGRA_SSL_DIR / "agra.key")
DEFAULT_DHPARAM = str(AGRA_SSL_DIR / "dhparam.pem")
DEFAULT_CA = str(AGRA_SSL_DIR / "agra-ca.crt")


def _run_openssl(args_list: List[str]) -> Tuple[int, str, str]:
    """Jalankan openssl sebagai user saat ini (operator owner /etc/agra — tanpa sudo)."""
    try:
        proc = subprocess.run(["openssl"] + list(args_list), capture_output=True, text=True, check=False, timeout=300)
        return (proc.returncode, proc.stdout or "", proc.stderr or "")
    except FileNotFoundError:
        return (127, "", "openssl tidak ditemukan di PATH")
    except subprocess.TimeoutExpired:
        return (124, "", "openssl timeout (300s)")


def _parse_openssl_date(s: str) -> Optional[datetime]:
    s = s.strip()
    fmts = ["%b %d %H:%M:%S %Y %Z", "%b %e %H:%M:%S %Y %Z", "%Y-%m-%d %H:%M:%S%z"]
    for fmt in fmts:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            pass
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(s)
        if dt is not None:
            if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
            return dt
    except Exception:
        pass
    return None


def _sanitize(s: str) -> str:
    return s.replace("\x00", "").strip()


def _require_globals_yml() -> int:
    """Pastikan /etc/agra/globals.yml ada — CN/SAN cert diambil dari grafana_domain/monitoring_vip."""
    if GLOBALS_FILE.is_file():
        return 0
    error(f"{GLOBALS_FILE} tidak ditemukan. CN/SAN cert diambil dari grafana_domain / monitoring_vip di file ini.")
    print("Jalankan ./install.sh dari root repo agra, lalu edit grafana_domain / monitoring_vip.")
    return 2


def _ssl_permission_hint(path: Path) -> None:
    error(f"Tidak bisa menulis/membaca {path} sebagai user saat ini.")
    print(f'Perbaiki ownership (/etc/agra milik operator user): sudo chown -R "$USER:$USER" {ETC_DIR}')


def _resolve_paths(args: argparse.Namespace) -> Tuple[str, str, str, str]:
    g = load_globals_file()
    explicit_cert = getattr(args, "cert_path", None)
    if isinstance(explicit_cert, str) and explicit_cert.strip():
        cert = explicit_cert.strip()
    else:
        fg = g.get("tls_cert_path", None)
        cert = fg.strip() if isinstance(fg, str) and fg.strip() else DEFAULT_CERT
    explicit_key = getattr(args, "key_path", None)
    if isinstance(explicit_key, str) and explicit_key.strip():
        key = explicit_key.strip()
    else:
        fg = g.get("tls_key_path", None)
        key = fg.strip() if isinstance(fg, str) and fg.strip() else DEFAULT_KEY
    explicit_dh = getattr(args, "dhparam_path", None)
    if isinstance(explicit_dh, str) and explicit_dh.strip():
        dh = explicit_dh.strip()
    else:
        fg = g.get("tls_dhparam_path", None)
        dh = fg.strip() if isinstance(fg, str) and fg.strip() else DEFAULT_DHPARAM
    fg_ca = g.get("tls_ca_path", None)
    ca = fg_ca.strip() if isinstance(fg_ca, str) and fg_ca.strip() else DEFAULT_CA
    return cert, key, dh, ca


def _detect_custom(g: Dict[str, Any], cert: str, key: str) -> Tuple[bool, str]:
    tls_cert_globals = g.get("tls_cert_path", "") or ""
    tls_key_globals = g.get("tls_key_path", "") or ""
    reasons: List[str] = []
    if isinstance(tls_cert_globals, str) and tls_cert_globals.strip():
        nu = tls_cert_globals.strip()
        if nu != DEFAULT_CERT:
            reasons.append(f"tls_cert_path diset ke CUSTOM PATH: '{nu}' (default: '{DEFAULT_CERT}')")
    if isinstance(tls_key_globals, str) and tls_key_globals.strip():
        nu = tls_key_globals.strip()
        if nu != DEFAULT_KEY:
            reasons.append(f"tls_key_path diset ke CUSTOM PATH: '{nu}' (default: '{DEFAULT_KEY}')")
    ssl_dir_default = Path(DEFAULT_CERT).parent
    if Path(cert).parent != ssl_dir_default and cert != DEFAULT_CERT:
        reasons.append(f"Cert path ke luar AGRA_SSL_DIR: '{cert}'")
    if Path(key).parent != ssl_dir_default and key != DEFAULT_KEY:
        reasons.append(f"Key path ke luar AGRA_SSL_DIR: '{key}'")
    if reasons:
        return True, " ; ".join(reasons)
    return False, ""


def _resolve_cn(args: argparse.Namespace, g: Dict[str, Any]) -> str:
    ecn = getattr(args, "cn", None)
    if isinstance(ecn, str) and ecn.strip():
        return ecn.strip()
    gd = g.get("grafana_domain", "") or ""
    if isinstance(gd, str) and len(gd.strip()) > 0:
        return gd.strip()
    mv = g.get("monitoring_vip", "") or ""
    if isinstance(mv, str) and len(mv.strip()) > 0:
        return mv.strip()
    try:
        hn = socket.gethostname().strip()
        if hn: return hn
    except Exception:
        pass
    try:
        pn = platform.node().strip()
        if pn: return pn
    except Exception:
        pass
    return "localhost"


def _write_atomic(steps: List[Tuple[List[str], str, int]], ssl_dir: Path) -> int:
    """Jalankan openssl ke file temp di ssl_dir (umask 077), lalu os.replace ke tujuan.

    steps: [(openssl_args_with_{out}_placeholder, final_path, mode)]. Semua langkah
    harus sukses sebelum file tujuan diganti — key & cert tidak pernah tidak cocok.
    Placeholder {key} di args diganti path temp key (untuk `req -key`).
    """
    temps: List[Tuple[str, str, int]] = []
    old_umask = os.umask(0o077)
    try:
        tmp_key = ""
        for args_list, final, mode in steps:
            fd, tmp = tempfile.mkstemp(dir=str(ssl_dir), prefix=".agra-", suffix=".tmp")
            os.close(fd)
            temps.append((tmp, final, mode))
            argv = [a.replace("{out}", tmp).replace("{key}", tmp_key) for a in args_list]
            rc, _, err = _run_openssl(argv)
            if rc != 0:
                error(f"openssl gagal untuk {final} (rc={rc}).")
                if err.strip():
                    print(f"{RED}{err.strip()}{RESET}")
                return rc or 1
            if final.endswith(".key"):
                tmp_key = tmp
        for tmp, final, mode in temps:
            os.chmod(tmp, mode)
        for tmp, final, _ in temps:
            os.replace(tmp, final)
        temps.clear()
        return 0
    finally:
        os.umask(old_umask)
        for tmp, _, _ in temps:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def cmd_generate(args: argparse.Namespace) -> int:
    section("agra certificates generate — Self-Signed RSA 2048 + x509")
    rc_req = _require_globals_yml()
    if rc_req != 0:
        return rc_req
    g = load_globals_file()
    cert, key, dh, ca = _resolve_paths(args)
    is_custom, reason = _detect_custom(g, cert, key)
    if is_custom:
        error("Custom TLS certificate terdeteksi — `agra certificates generate` hanya untuk self-signed default di /etc/agra/ssl.")
        print(f"  {GRAY}- {reason}{RESET}")
        print(f"Perbarui cert custom anda manual, lalu: {MAGENTA}{BOLD}agra deploy --tags nginx{RESET}")
        return 2
    force = getattr(args, "force", False)
    if not force and Path(cert).exists() and Path(key).exists():
        info("Cert & key sudah ada. Tidak ada yang dilakukan (pakai --force untuk regenerate).")
        return 0

    ssl_dir = Path(cert).parent
    try:
        ssl_dir.mkdir(mode=0o750, parents=True, exist_ok=True)
        os.chmod(ssl_dir, 0o750)
    except PermissionError:
        _ssl_permission_hint(ssl_dir)
        return 3
    if not os.access(ssl_dir, os.W_OK | os.X_OK):
        _ssl_permission_hint(ssl_dir)
        return 3

    cn = _resolve_cn(args, g)
    san: List[str] = [f"DNS:{cn}", "DNS:localhost", "IP:127.0.0.1"]
    vip = str(g.get("monitoring_vip") or "").strip()
    if vip:
        san.append(f"IP:{vip}")
    final_san = list(dict.fromkeys(san))
    san_str = ",".join(final_san)
    C = g.get("tls_self_signed_country") or "ID"
    ST = g.get("tls_self_signed_state") or "Jakarta"
    L = g.get("tls_self_signed_locality") or "Jakarta"
    O = g.get("tls_self_signed_organization") or "agra-monitoring"
    OU = g.get("tls_self_signed_organizational_unit") or "it"
    days = getattr(args, "days", None) or g.get("tls_self_signed_days_valid") or DEFAULT_DAYS
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = DEFAULT_DAYS
    subj = f"/C={C}/ST={ST}/L={L}/O={O}/OU={OU}/CN={cn}"

    info(f"Generate RSA 2048 key + self-signed x509 ({days} hari): {key}, {cert}")
    rc = _write_atomic([
        (["genrsa", "-out", "{out}", "2048"], key, 0o600),
        (["req", "-new", "-x509", "-sha256", "-days", str(days), "-key", "{key}", "-out", "{out}",
          "-subj", subj, "-addext", f"subjectAltName={san_str}"], cert, 0o644),
    ], ssl_dir)
    if rc != 0:
        return rc

    include_dh = getattr(args, "include_dhparam", False)
    if include_dh:
        warn(f"{YELLOW}Generate DH 2048-bit (~10-60s){RESET}")
        if _write_atomic([(["dhparam", "-out", "{out}", "2048"], dh, 0o644)], ssl_dir) != 0:
            warn("Gagal generate dhparam. Lanjut tanpa dhparam.")
            include_dh = False

    section("Ringkasan Self-Signed Certificate")
    print(f"  {BOLD}Cert Path   :{RESET} {GREEN}{cert}{RESET} (0644)")
    print(f"  {BOLD}Key Path    :{RESET} {CYAN}{key}{RESET} {YELLOW}(0600 — JANGAN disebarkan){RESET}")
    if include_dh:
        print(f"  {BOLD}DH Param    :{RESET} {dh}")
    print(f"  {BOLD}Valid Days  :{RESET} {days}")
    print(f"  {BOLD}CN          :{RESET} {GREEN}{BOLD}{cn}{RESET}")
    print(f"  {BOLD}SAN List    :{RESET} {', '.join(final_san)}")
    print(f"  {BOLD}Subject     :{RESET} {subj}")
    print()
    info(f"Distribusikan ke managed host: {MAGENTA}{BOLD}agra deploy --tags nginx{RESET}")
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    section("agra certificates info — Certificate Information")
    ec = getattr(args, "cert_path", None)
    if isinstance(ec, str) and ec.strip():
        cert_path = ec.strip()
    else:
        g = load_globals_file()
        fg = g.get("tls_cert_path", "") or ""
        cert_path = fg.strip() if isinstance(fg, str) and fg.strip() else DEFAULT_CERT
    print(f"{BOLD}Cert path (resolved):{RESET} {CYAN}{cert_path}{RESET}")
    p = Path(cert_path)
    if not p.exists():
        if not os.access(p.parent, os.X_OK):
            _ssl_permission_hint(p.parent)
            return 3
        warn(f"File cert TIDAK DITEMUKAN di: {cert_path}")
        print(f"{GRAY}Tips: Gunakan {BOLD}agra certificates generate{RESET}{GRAY} untuk membuat self-signed cert default.{RESET}")
        print(f"{GRAY}Tips: Gunakan --cert-path /path/custom.crt untuk cek cert di lokasi lain.{RESET}")
        return 1
    rc, out, err = _run_openssl(["x509", "-in", str(p), "-noout", "-issuer", "-subject", "-dates", "-ext", "subjectAltName"])
    if rc != 0:
        error(f"Gagal baca cert via openssl x509 (rc={rc}).")
        if err.strip(): print(f"{RED}{err.strip()}{RESET}")
        return rc
    issuer = subject = not_before = not_after = san_str = ""
    for raw_line in out.splitlines():
        line = raw_line.strip()
        if line.startswith("issuer="): issuer = _sanitize(line[len("issuer="):])
        elif line.startswith("subject="): subject = _sanitize(line[len("subject="):])
        elif line.startswith("notBefore="): not_before = _sanitize(line[len("notBefore="):])
        elif line.startswith("notAfter="): not_after = _sanitize(line[len("notAfter="):])
        elif "Subject Alternative Name" in line or line.startswith(("DNS:", "IP Address:", "IP:")):
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
                    in_san = False if "," not in line and line.startswith(("DNS:", "IP")) else True
    cn = ""
    m = re.search(r'(?:^|[,/])\s*CN\s*=\s*([^,/]+)', subject)
    if m: cn = _sanitize(m.group(1))
    else:
        m2 = re.search(r'CN\s*=\s*([^\n,]+)', subject)
        if m2: cn = _sanitize(m2.group(1))
    san_list: List[str] = []
    for m in re.finditer(r'(DNS|IP(?: Address)?):\s*([^,\s]+)', san_str):
        san_list.append(f"{m.group(1).replace(' Address', '')}:{m.group(2)}")
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
        if days_remaining < 0 or days_remaining < 7:
            print()
            if days_remaining < 0: error("CERT SUDAH EXPIRED!")
            else: error("CERT AKAN EXPIRED KURANG DARI 7 HARI! (RED CRITICAL)")
            g2 = load_globals_file()
            ict, _ = _detect_custom(g2, cert_path, "")
            if ict:
                warn("Cert ini adalah CUSTOM cert. Update custom cert anda MANUAL, lalu jalankan:")
                print(f"  {MAGENTA}{BOLD}agra deploy --tags nginx{RESET}")
            else:
                warn("Regenerate self-signed cert default SEKARANG:")
                print(f"  {MAGENTA}{BOLD}agra certificates generate --force{RESET}")
            return 2
        elif days_remaining < 30:
            print()
            warn("CERT AKAN EXPIRED KURANG DARI 30 HARI! (YELLOW WARNING) — segera regenerate cert.")
            g2 = load_globals_file()
            ict, _ = _detect_custom(g2, cert_path, "")
            if ict:
                info("Cert ini adalah CUSTOM cert. Update custom cert manual lalu `agra deploy --tags nginx`.")
            else:
                info("Regenerate self-signed cert default: `agra certificates generate --force`")
            return 0
    print()
    info("Cert validity OK.")
    return 0


def setup_parser(subparsers: "argparse._SubParsersAction") -> argparse.ArgumentParser:
    p = subparsers.add_parser(
        "certificates",
        help="Self-signed certificate management (pre-deploy generate + info) di control node /etc/agra/ssl.",
        description="Self-signed certificate lifecycle: generate (RSA 2048 + x509 pre-deploy) | info/check/status (detail cert + expiry warning).",
    )
    p.add_argument("-c", "--cert-path", dest="cert_path", help="Override path cert file")
    p.add_argument("-k", "--key-path", dest="key_path", help="Override path key file")
    p.add_argument("-d", "--dhparam-path", dest="dhparam_path", help="Override path dhparam file")
    sub = p.add_subparsers(dest="certificates_command", required=False, metavar="{generate | gen | info | check | status}")
    sub.default = "info"
    p_gen = sub.add_parser("generate", aliases=["gen"], help="Generate self-signed RSA 2048 + x509 cert di control node /etc/agra/ssl (pre-deploy). SAFETY: Custom cert TIDAK boleh di-generate. Idempotent tanpa --force.")
    p_gen.add_argument("--days", type=int, default=None, dest="days", help=f"Jumlah hari valid cert (default: tls_self_signed_days_valid di globals.yml, atau {DEFAULT_DAYS})")
    p_gen.add_argument("--cn", dest="cn", help="Override CN (default: grafana_domain > monitoring_vip > hostname)")
    p_gen.add_argument("-f", "--force", dest="force", action="store_true", help="Force regenerate meskipun cert & key sudah ada")
    p_gen.add_argument("--include-dhparam", dest="include_dhparam", action="store_true", help="Generate juga DH 2048-bit (~10-60s). Default FALSE.")
    # Opsi yang juga ada di `agra certificates` — default milik parent (cli_args.py).
    p_gen.add_argument("-c", "--cert-path", dest="cert_path", default=argparse.SUPPRESS, help="Override path cert output")
    p_gen.add_argument("-k", "--key-path", dest="key_path", default=argparse.SUPPRESS, help="Override path key output")
    p_gen.add_argument("-d", "--dhparam-path", dest="dhparam_path", default=argparse.SUPPRESS, help="Override path dhparam output")
    p_gen.set_defaults(func=cmd_generate)
    p_info = sub.add_parser("info", aliases=["check", "status"], help="Print detail certificate: path, issuer, subject, CN, SAN, dates, days_remaining + WARNING expiry.")
    p_info.add_argument("-c", "--cert-path", dest="cert_path", default=argparse.SUPPRESS, help=f"Path cert file (default: globals.yml tls_cert_path atau {DEFAULT_CERT})")
    p_info.set_defaults(func=cmd_info)
    p.set_defaults(func=cmd_info, certificates_command="info")
    return p
