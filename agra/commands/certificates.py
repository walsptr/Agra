"""agra certificates — subcommands generate & info/check.
generate = self-signed RSA 2048 + x509 di control node /etc/agra/ssl (pre-deploy).
info/check = parse detail cert via openssl + expiry warning.
"""
from __future__ import annotations
import argparse
import os
import re
import socket
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from agra.utils.colors import info, warn, error, section, debug, BOLD, RESET, RED, YELLOW, GREEN, CYAN, MAGENTA, GRAY
from agra.utils.paths import load_globals_yaml
from agra.constants import AGRA_SSL_DIR, ETC_DIR


DEFAULT_DAYS = 3650
DEFAULT_CERT = str(AGRA_SSL_DIR / "agra.crt")
DEFAULT_KEY = str(AGRA_SSL_DIR / "agra.key")
DEFAULT_DHPARAM = str(AGRA_SSL_DIR / "dhparam.pem")
DEFAULT_CA = str(AGRA_SSL_DIR / "agra-ca.crt")


def _run_openssl(args_list: List[str], check_stderr: bool = False) -> Tuple[int, str, str]:
    """[DEPRECATED - USE _run_cmd DENGAN use_root=True untuk write].
    Lama: plain openssl. Baru: pakai _run_cmd auto-sudo untuk write (use_root=True default)."""
    return _run_cmd(["openssl"] + list(args_list), use_root=True, check_stderr=check_stderr)


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


def _is_root() -> bool:
    """Return True JIKA current EUID = 0 (root)."""
    try:
        return os.geteuid() == 0
    except Exception:
        return False


def _detect_sudo_capable() -> Tuple[bool, str]:
    """Cek apakah environment BISA menjalankan sudo NON-INTERACTIVE (tanpa prompt password).
    Return (capable: bool, reason_fail: str)
    capable=True BISA pakai sudo tanpa prompt (passwordless / sudoreplay cached).
    capable=False TIDAK BISA (reason_fail berisi deskripsi: tidak ada sudo binary,
    user tidak punya sudoers, but password prompt, dsb)."""
    import shutil
    if shutil.which("sudo") is None:
        return False, "sudo binary TIDAK DITEMUKAN di PATH. Install sudo package terlebih dahulu."
    try:
        proc = subprocess.run(["sudo", "-n", "true"], capture_output=True, text=True, check=False, timeout=15)
        if proc.returncode == 0:
            return True, ""
        stderr = (proc.stderr or "").strip()
        if "password is required" in stderr.lower():
            return False, ("Sudo MEMBUTUHKAN password, tapi command dijalankan non-interactive."
                           " Jalankan PAKAI SUDO eksplisit: sudo agra certificates generate ...")
        if "not allowed" in stderr.lower() or "not in the sudoers" in stderr.lower():
            return False, ("User saat ini TIDAK ADA di grup sudo / tidak punya sudoers privilege."
                           " Hubungi admin atau jalankan sebagai root: su -c 'agra certificates ...'")
        if stderr:
            return False, f"Sudo gagal non-interactive: {stderr[:200]}"
        return False, "Sudo non-interactive gagal (RC != 0, stderr kosong)."
    except subprocess.TimeoutExpired:
        return False, "Sudo timeout (>15s) menunggu response credential."
    except Exception as e:
        return False, f"Kesalahan detect sudo: {str(e)[:200]}"


def _run_cmd(args_list: List[str], *, use_root: bool = True,
             check_stderr: bool = False, timeout_s: int = 180) -> Tuple[int, str, str]:
    """Menjalankan shell command, OTOMATIS PREFIX SUDO jika use_root=True DAN user BUKAN root.
    use_root=True: SELALU tulis ke system-wide path (default untuk semua write file).
    use_root=False: plain command tanpa sudo (untuk read-only, mis. openssl x509 -text read cert).
    Return (rc, stdout, stderr)."""
    final_args: List[str] = list(args_list)
    is_root_now = _is_root()
    if use_root and not is_root_now:
        capable, fail_reason = _detect_sudo_capable()
        if not capable:
            box_w = 78
            print()
            print(f"{RED}{BOLD}{'─' * box_w}{RESET}")
            print(f"{RED}{BOLD}✗ CRITICAL: Butuh PRIVILEGE ROOT / SUDO untuk WRITE FILE ke /etc/agra/ssl (root-owned).{RESET}")
            print()
            print(f"{YELLOW}{BOLD}  Alasan Sudo tidak bisa dipakai otomatis:{RESET}")
            print(f"    {GRAY}- {fail_reason}{RESET}")
            print()
            print(f"{GREEN}{BOLD}  SOLUSI (PILIH SALAH SATU):{RESET}")
            print(f"    {BOLD}SOLUSI 1 (PALING MUDAH): Jalankan command DENGAN SUDO EKSPLISIT:{RESET}")
            print(f"      $ sudo agra certificates generate"
                  f"{' --include-dhparam' if 'dhparam' in ' '.join(args_list) else ''} [--force]")
            print(f"    {BOLD}SOLUSI 2 (Passwordless sudo untuk user sekarang, permanent):{RESET}")
            print(f"      Tambahkan line ini ke /etc/sudoers.d/agra (root):")
            print(f"        {GRAY}{os.environ.get('USER','<your-user>')} ALL=(ALL) NOPASSWD: "
                  f"/usr/bin/openssl, /bin/mkdir, /bin/chmod, /bin/chown{RESET}")
            print(f"    {BOLD}SOLUSI 3 (Jalankan sebagai root via su):{RESET}")
            print(f"      $ su -c \"agra certificates generate ...\"")
            print()
            print(f"{GRAY}  Catatan: /etc/agra dan /etc/agra/ssl sengaja dimiliki root:root"
                  f" untuk melindungi private key SSL (mode 0600).{RESET}")
            print(f"{RED}{BOLD}{'─' * box_w}{RESET}")
            print()
            return (3, "", "sudo_not_capable")
        final_args = ["sudo", "-n"] + list(args_list)
    try:
        proc = subprocess.run(final_args, capture_output=True, text=True, check=False, timeout=timeout_s)
        return (proc.returncode, proc.stdout or "", proc.stderr or "")
    except subprocess.TimeoutExpired:
        return (124, "", f"timeout ({timeout_s}s)")
    except Exception as e:
        return (1, "", str(e))


def _require_globals_yml() -> int:
    """GUARD KRITIS: Pastikan /etc/agra/globals.yml ADA sebelum generate/info baca domain/VIP.
    Return RC=2 dengan RED BOX error detail yang user-friendly JIKA file TIDAK ADA.
    Return RC=0 JIKA file ada.
    """
    path = ETC_DIR / "globals.yml"
    if path.exists() and path.is_file():
        return 0
    box_w = 78
    print()
    print(f"{RED}{BOLD}{'─' * box_w}{RESET}")
    print(f"{RED}{BOLD}✗ ERROR:{RESET} File konfigurasi WAJIB TIDAK DITEMUKAN.")
    print(f"{RED}{BOLD}  Path yang diharapkan (absolute Kolla-Ansible pattern):{RESET}")
    print(f"    {CYAN}{BOLD}/etc/agra/globals.yml{RESET}")
    print()
    print(f"{YELLOW}{BOLD}  Alasan kenapa WAJIB ADA:{RESET}")
    print(f"    - CN (Common Name) cert diambil dari: "
          f"{GREEN}grafana_domain{RESET} > "
          f"{GREEN}monitoring_vip{RESET} > hostname fallback")
    print(f"    - SAN (Subject Alt Names) cert disusun dari: "
          f"{GREEN}DNS:<grafana_domain/VIP>{RESET}, DNS:localhost, IP:127.0.0.1, "
          f"{GREEN}IP:<monitoring_vip>{RESET}")
    print(f"    - SSL default paths tls_cert_path, tls_key_path ada di globals.yml")
    print(f"    - TANPA globals.yml → CN/SAN cuma hostname doang (SALAH!), "
          f"jadi HENTIKAN sebelum dieksekusi.")
    print()
    print(f"{YELLOW}{BOLD}  SOLUSI (jalankan SALAH SATU dari repo agra root):{RESET}")
    print(f"    {BOLD}SOLUSI 1 (direkomendasikan via install.sh):{RESET}")
    print(f"      $ ./install.sh     # mkdir /etc/agra dan copy template globals/passwords idempotent")
    print(f"    {BOLD}SOLUSI 2 (manual copy):{RESET}")
    print(f"      $ sudo mkdir -p /etc/agra/config /etc/agra/ssl")
    print(f"      $ sudo chmod 0755 /etc/agra /etc/agra/config")
    print(f"      $ sudo chmod 0750 /etc/agra/ssl")
    print(f"      $ sudo cp -n ./etc/agra/globals.yml   /etc/agra/globals.yml")
    print(f"      $ sudo cp -n ./etc/agra/passwords.yml /etc/agra/passwords.yml")
    print(f"      $ sudo cp -rn ./etc/agra/config/*     /etc/agra/config/ 2>/dev/null || true")
    print(f"    {BOLD}SOLUSI 3 (cek file exist):{RESET}")
    print(f"      $ ls -la /etc/agra/globals.yml && echo OK")
    print()
    print(f"{GRAY}  Setelah file /etc/agra/globals.yml tersedia, edit value: $EDITOR /etc/agra/globals.yml")
    print(f"  → Set `grafana_domain` (domain, prioritas TERTINGGI untuk CN/SAN) dan/atau")
    print(f"    `monitoring_vip` (VIP IP untuk HA keepalived).{RESET}")
    print(f"{RED}{BOLD}{'─' * box_w}{RESET}")
    print()
    return 2


def _resolve_paths(args: argparse.Namespace) -> Tuple[str, str, str, str]:
    g = load_globals_yaml()
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


def cmd_generate(args: argparse.Namespace) -> int:
    section("agra certificates generate — Self-Signed RSA 2048 + x509")
    rc_req = _require_globals_yml()
    if rc_req != 0: return rc_req
    g = load_globals_yaml()
    cert, key, dh, ca = _resolve_paths(args)
    is_custom, reason = _detect_custom(g, cert, key)
    if is_custom:
        error("Custom TLS certificate TERDETEKSI, agra certificates generate HANYA untuk self-signed default /etc/agra/ssl.")
        print(f"\n{YELLOW}{BOLD}Alasan deteksi custom cert:{RESET}")
        print(f"  {GRAY}- {reason}{RESET}")
        print(f"\n{MAGENTA}{BOLD}Saran:{RESET}")
        print(f"  {MAGENTA}Gunakan {BOLD}agra deploy --tags nginx{RESET}{MAGENTA} untuk reload custom cert anda.{RESET}")
        return 2
    force = getattr(args, "force", False)
    if not force and Path(cert).exists() and Path(key).exists():
        info("Already exists. Nothing to do. Use --force to regenerate.")
        return 0
    ssl_dir = Path(cert).parent
    if _is_root():
        ssl_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(str(ssl_dir), 0o750)
            os.chown(str(ssl_dir), 0, 0)
        except Exception as e:
            debug(f"chmod/chown ssl dir skipped: {e}")
    else:
        info(f"Ensure ssl dir exists: mkdir -p {ssl_dir} (using sudo if available)")
        rc_mk, _, err_mk = _run_cmd(["mkdir", "-p", str(ssl_dir)], use_root=True)
        if rc_mk != 0:
            error(f"Gagal mkdir ssl dir '{ssl_dir}' (rc={rc_mk}).")
            if err_mk.strip() and "sudo_not_capable" not in err_mk:
                print(f"{RED}{err_mk.strip()}{RESET}")
            return rc_mk
        rc_chm, _, _ = _run_cmd(["chmod", "0750", str(ssl_dir)], use_root=True)
        if rc_chm == 0:
            _run_cmd(["chown", "root:root", str(ssl_dir)], use_root=True)
    cn = _resolve_cn(args, g)
    san: List[str] = [f"DNS:{cn}", "DNS:localhost", "IP:127.0.0.1"]
    vip = (g.get("monitoring_vip") or "").strip()
    if len(vip) > 0: san.append(f"IP:{vip}")
    seen: set = set()
    final_san: List[str] = []
    for x in san:
        if x not in seen:
            seen.add(x)
            final_san.append(x)
    san_str = ",".join(final_san)
    C = g.get("tls_self_signed_country", "ID") or "ID"
    ST = g.get("tls_self_signed_state", "Jakarta") or "Jakarta"
    L = g.get("tls_self_signed_locality", "Jakarta") or "Jakarta"
    O = g.get("tls_self_signed_org", "agra-monitoring") or "agra-monitoring"
    OU = g.get("tls_self_signed_ou", "it") or "it"
    info(f"Generate RSA 2048-bit private key: {key}")
    rc_k, _, err_k = _run_openssl(["genrsa", "-out", key, "2048"])
    if rc_k != 0:
        error(f"Gagal generate private key (rc={rc_k}).")
        if err_k.strip(): print(f"{RED}{err_k.strip()}{RESET}")
        return rc_k
    if _is_root():
        try: os.chmod(key, 0o600)
        except Exception as e: debug(f"chmod key 0600 skipped: {e}")
    else:
        _run_cmd(["chmod", "0600", key], use_root=True)
        _run_cmd(["chown", "root:root", key], use_root=True)
    info("Private key OK — chmod 0600.")
    days_int = getattr(args, "days", DEFAULT_DAYS)
    if not isinstance(days_int, int) or days_int <= 0: days_int = DEFAULT_DAYS
    days_str = str(days_int)
    subj = f"/C={C}/ST={ST}/L={L}/O={O}/OU={OU}/CN={cn}"
    info(f"Generate self-signed x509 cert: {cert}")
    rc_c, _, err_c = _run_openssl([
        "req", "-new", "-x509", "-sha256", "-nodes",
        "-days", days_str, "-key", key, "-out", cert,
        "-subj", subj, "-addext", f"subjectAltName={san_str}",
    ])
    if rc_c != 0:
        error(f"Gagal generate self-signed cert (rc={rc_c}).")
        if err_c.strip(): print(f"{RED}{err_c.strip()}{RESET}")
        return rc_c
    if _is_root():
        try: os.chmod(cert, 0o644)
        except Exception as e: debug(f"chmod cert 0644 skipped: {e}")
    else:
        _run_cmd(["chmod", "0644", cert], use_root=True)
        _run_cmd(["chown", "root:root", cert], use_root=True)
    info("Self-signed cert OK — chmod 0644.")
    include_dh = getattr(args, "include_dhparam", False)
    if include_dh:
        warn(f"{YELLOW}Generate DH 2048-bit (LAMA ~10-60s, mohon tunggu){RESET}")
        info(f"Generate DH param: {dh}")
        rc_d, _, err_d = _run_openssl(["dhparam", "-out", dh, "2048"])
        if rc_d != 0:
            warn(f"Gagal generate dhparam (rc={rc_d}). Lanjut tanpa dhparam.")
            if err_d.strip(): print(f"{YELLOW}{err_d.strip()}{RESET}")
        else:
            if _is_root():
                try: os.chmod(dh, 0o644)
                except Exception as e: debug(f"chmod dh 0644 skipped: {e}")
            else:
                _run_cmd(["chmod", "0644", dh], use_root=True)
                _run_cmd(["chown", "root:root", dh], use_root=True)
            info("DH param OK — chmod 0644.")
    section("Ringkasan Hasil Generate Self-Signed Certificate")
    print(f"  {BOLD}Cert Path   :{RESET} {GREEN}{cert}{RESET}")
    print(f"  {BOLD}Key Path    :{RESET} {CYAN}{key}{RESET} {YELLOW}(chmod 0600 — JANGAN disebarkan!){RESET}")
    if include_dh: print(f"  {BOLD}DH Param    :{RESET} {dh}")
    print(f"  {BOLD}Valid Days  :{RESET} {days_str} hari (~{int(int(days_str)/365)} tahun)")
    print(f"  {BOLD}CN          :{RESET} {GREEN}{BOLD}{cn}{RESET}")
    print(f"  {BOLD}SAN List    :{RESET} {', '.join(final_san)}")
    print(f"  {BOLD}Subject     :{RESET} {subj}")
    print()
    info("Certificate self-signed generate SELESAI. Siap dipakai pre-deploy di control node.")
    info(f"Untuk deploy ke managed host, jalankan: {MAGENTA}{BOLD}agra deploy --tags nginx{RESET}")
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    section("agra certificates info — Certificate Information")
    rc_req = _require_globals_yml()
    if rc_req != 0: return rc_req
    ec = getattr(args, "cert_path", None)
    if isinstance(ec, str) and ec.strip():
        cert_path = ec.strip()
    else:
        g = load_globals_yaml()
        fg = g.get("tls_cert_path", "") or ""
        cert_path = fg.strip() if isinstance(fg, str) and fg.strip() else DEFAULT_CERT
    print(f"{BOLD}Cert path (resolved):{RESET} {CYAN}{cert_path}{RESET}")
    p = Path(cert_path)
    if not p.exists():
        warn(f"File cert TIDAK DITEMUKAN di: {cert_path}")
        print(f"{GRAY}Tips: Gunakan {BOLD}agra certificates generate{RESET}{GRAY} untuk membuat self-signed cert default.{RESET}")
        print(f"{GRAY}Tips: Gunakan --cert-path /path/custom.crt untuk cek cert di lokasi lain.{RESET}")
        return 1
    rc, out, err = _run_cmd(["openssl", "x509", "-in", str(p), "-noout", "-issuer", "-subject", "-dates", "-ext", "subjectAltName"], use_root=False)
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
        rc2, out2, _ = _run_cmd(["openssl", "x509", "-in", str(p), "-noout", "-text"], use_root=False)
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
        if days_remaining < 0 or days_remaining < 7:
            print()
            if days_remaining < 0: error("CERT SUDAH EXPIRED!")
            else: error("CERT AKAN EXPIRED KURANG DARI 7 HARI! (RED CRITICAL)")
            g2 = load_globals_yaml()
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
            g2 = load_globals_yaml()
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
    p_gen.add_argument("--days", type=int, default=DEFAULT_DAYS, dest="days", help=f"Jumlah hari valid cert (default: {DEFAULT_DAYS})")
    p_gen.add_argument("--cn", dest="cn", help="Override CN (default: grafana_domain > monitoring_vip > hostname)")
    p_gen.add_argument("-f", "--force", dest="force", action="store_true", help="Force regenerate meskipun cert & key sudah ada")
    p_gen.add_argument("--include-dhparam", dest="include_dhparam", action="store_true", help="Generate juga DH 2048-bit (~10-60s). Default FALSE.")
    p_gen.add_argument("-c", "--cert-path", dest="cert_path", help="Override path cert output")
    p_gen.add_argument("-k", "--key-path", dest="key_path", help="Override path key output")
    p_gen.add_argument("-d", "--dhparam-path", dest="dhparam_path", help="Override path dhparam output")
    p_gen.set_defaults(func=cmd_generate)
    p_info = sub.add_parser("info", aliases=["check", "status"], help="Print detail certificate: path, issuer, subject, CN, SAN, dates, days_remaining + WARNING expiry.")
    p_info.add_argument("-c", "--cert-path", dest="cert_path", help=f"Path cert file (default: globals.yml tls_cert_path atau {DEFAULT_CERT})")
    p_info.set_defaults(func=cmd_info)
    p.set_defaults(func=cmd_info, certificates_command="info")
    return p
