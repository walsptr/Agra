# License — Apache 2.0

Seluruh kode proyek agra (Ansible playbook, role, template, Python CLI wrapper) dirilis di bawah **Apache License, Version 2.0**. Lisensi ini memberikan hak luas kepada pengguna sambil tetap memberikan perlindungan hukum yang wajar bagi kontributor.

## Ringkasan Hak Pengguna (Human Readable Summary)

**Yang BOLEH Anda lakukan (tanpa royalti, permanen, worldwide, non-eksklusif):**
- ✅ **Komersial gunakan**: Gunakan agra di lingkungan production perusahaan, SaaS, proyek berbayar, maupun internal korporasi.
- ✅ **Modifikasi**: Ubah seluruh atau sebagian kode (playbook, role, template, CLI Python) sesuai kebutuhan organisasi Anda.
- ✅ **Distribusi**: Mendistribusikan salinan agra, baik asli maupun yang telah dimodifikasi, ke pihak ketiga.
- ✅ **Penggunaan Paten**: Lisensi ini secara eksplisit memberikan hak paten dari kontributor ke pengguna (patent grant), sehingga Anda tidak perlu khawatir akan klaim paten di masa depan atas kontribusi yang telah diterima ke upstream.
- ✅ **Penggunaan pribadi / non-komersial**: Tentu saja boleh tanpa batas khusus apa pun.

## Kewajiban Jika Anda Mendistribusikan (Penting!)

Jika Anda **mendistribusikan** agra (asli / dimodifikasi / digabung ke proyek lain) ke pihak ketiga, Anda **WAJIB** melakukan ketiga hal berikut:

1. **Sertakan pemberitahuan hak cipta (copyright notice)** yang asli beserta daftar perubahan yang Anda buat (statement of changes). Jangan menghapus header copyright yang ada di file.
2. **Sertakan salinan lengkap teks Apache License 2.0** dalam distribusi Anda. Teks lengkap lisensi disimpan di file **[`../README.md`](../README.md)** bagian paling bawah (setelah section dokumentasi).
3. **Jika ada file NOTICE yang disertakan oleh upstream**, sertakan juga file NOTICE tersebut dalam distribusi Anda.

---

## Copyright

```
Copyright 2025-2026 Agra Contributors
```

Lisensi Apache 2.0 FULL TEKS (9 section resmi dari Apache Foundation): **[klik di sini (bagian akhir README.md)](../README.md#end-of-terms-and-conditions)**.

---

## Third Party Attribution (Lisensi Komponen Eksternal)

agra **memanggil / menarik / depend** ke beberapa perangkat lunak pihak ketiga (third-party). Masing-masing memiliki lisensi sendiri — penting untuk Anda ketahui karena agra **TIDAK mendistribusikan ulang binary perangkat lunak tersebut** (hanya memanggilnya sebagai external tool atau menarik image atas nama Anda saat deploy):

| Komponen | License | Catatan Penting (Boundary Scope) |
|---|---|---|
| **Grafana OSS** | **GNU Affero General Public License v3.0 (AGPL-3.0)** | ⚠️ **agra TIDAK PERNAH mendistribusikan binary / docker image Grafana.** Selama deployment, image grafana/grafana-oss ditarik **langsung oleh user** dari Docker Hub atas nama user, bukan digabung / redistributed sebagai bagian dari release agra. Cara ini menjaga lisensi Apache 2.0 agra **TIDAK TERINFEKSI copyleft AGPL v3** (infeksi hanya terjadi jika Anda redistribute binary AGPL ke pihak ketiga). Jika Anda meng-custom image Grafana lalu redistribute — silakan cek sendiri compliance AGPL v3. |
| **Prometheus** | **Apache License 2.0** | ✅ Kompatibel penuh dengan agra. Prometheus static binary / docker image ditarik langsung oleh user saat deploy. |
| **Ansible Core** | **GNU General Public License v3.0 (GPL-3.0-only)** | ⚠️ **agra HANYA memanggil CLI `ansible` / `ansible-playbook` via `subprocess.run()`** (dynamic linking sebagai external tool, bukan static linking / import Python module Ansible ke kode agra sendiri). Sesuai interpretasi umum FSF dan Free Software Foundation, **pemanggilan CLI tool terpisah via subprocess TIDAK membuat karya agra menjadi turunan (derivative work) GPL v3**. Anda bertanggung jawab sendiri atas instalasi Ansible Core di virtual environment Anda (lihat `README.md` bagian Install → `pip install ansible-core>=2.16` di-install manual terpisah). |
| **Node Exporter** | **Apache License 2.0** | ✅ Kompatibel penuh dengan agra, ditarik oleh user saat deploy. |
| **Nginx** | **BSD 2-Clause License** | ✅ Kompatibel, ditarik / diinstall oleh user saat deploy. |
| **Keepalived** | **GNU General Public License v2.0+ (GPL-2.0-or-later)** | ⚠️ Sama seperti Ansible: dipanggil / diinstall sebagai system package OS terpisah atau docker image osixia/keepalived ditarik langsung oleh user. Bukan bagian dari binary agra. |
| **PyYAML** | **MIT License** | ✅ Dependency Python CLI agra, kompatibel penuh dengan Apache 2.0. |

Jika ada ketidaksesuaian interpretasi lisensi yang perlu diklarifikasi, silakan buat Issue di repo agra untuk didiskusikan.
