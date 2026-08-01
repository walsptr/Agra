# License — MIT License

Seluruh kode proyek agra (Ansible playbook, role, template, Python CLI wrapper) dirilis di bawah **MIT License**. Lisensi ini adalah lisensi open source paling permisif — sangat minim syarat, bebas pakai untuk apapun selama copyright notice tetap dipertahankan.

## Ringkasan Hak Pengguna (Human Readable Summary)

**Yang BOLEH Anda lakukan (tanpa royalti, permanen, worldwide, non-eksklusif):**
- ✅ **Komersial gunakan**: Gunakan agra di lingkungan production perusahaan, SaaS, proyek berbayar, maupun internal korporasi.
- ✅ **Modifikasi**: Ubah seluruh atau sebagian kode (playbook, role, template, CLI Python) sesuai kebutuhan organisasi Anda.
- ✅ **Distribusi**: Mendistribusikan salinan agra, baik asli maupun yang telah dimodifikasi, ke pihak ketiga.
- ✅ **Penggunaan pribadi / non-komersial**: Tentu saja boleh tanpa batas khusus apa pun.
- ✅ **Private use**: Anda TIDAK WAJIB mempublikasikan modifikasi Anda jika hanya dipakai internal (berbeda dengan copyleft GPL/AGPL yang mewajibkan source disclosure).

## Kewajiban Jika Anda Mendistribusikan (Satu-satunya Syarat — SANGAT RINGAN!)

Jika Anda **mendistribusikan** agra (asli / dimodifikasi / digabung ke proyek lain) ke pihak ketiga, Anda **hanya WAJIB** melakukan SATU hal:

1. **Sertakan pemberitahuan hak cipta (copyright notice) + SALINAN TEKS MIT LICENSE** yang asli dalam distribusi Anda. Jangan menghapus baris copyright `Copyright (c) 2025–2026 Agra Contributors` dan 2 paragraf Permission dari file.

Itu SAJA. Tidak perlu menyertakan file NOTICE terpisah, tidak perlu menandai setiap file diubah, tidak perlu disclose source code modifikasi Anda jika pakai private.

---

## Copyright + Full License Text

Full text MIT License (sama persis dengan yang ada di akhir README.md):

```
MIT License

Copyright (c) 2025–2026 Agra Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

Full text juga tersedia di **[`../README.md` bagian paling bawah (section MIT License)](../README.md)**.

---

## Third Party Attribution (Lisensi Komponen Eksternal)

agra **memanggil / menarik / depend** ke beberapa perangkat lunak pihak ketiga (third-party). Masing-masing memiliki lisensi sendiri — penting untuk Anda ketahui karena agra **TIDAK mendistribusikan ulang binary perangkat lunak tersebut** (hanya memanggilnya sebagai external tool atau menarik image atas nama Anda saat deploy):

| Komponen | License | Catatan Penting (Boundary Scope) |
|---|---|---|
| **Grafana OSS** | **GNU Affero General Public License v3.0 (AGPL-3.0)** | ⚠️ **agra TIDAK PERNAH mendistribusikan binary / docker image Grafana.** Selama deployment, image grafana/grafana-oss ditarik **langsung oleh user** dari Docker Hub atas nama user, bukan digabung / redistributed sebagai bagian dari release agra. Cara ini menjaga lisensi MIT agra **TIDAK TERINFEKSI copyleft AGPL v3** (infeksi hanya terjadi jika Anda redistribute binary AGPL ke pihak ketiga). Jika Anda meng-custom image Grafana lalu redistribute — silakan cek sendiri compliance AGPL v3. |
| **Prometheus** | **Apache License 2.0** | ✅ Kompatibel penuh dengan MIT agra. Prometheus static binary / docker image ditarik langsung oleh user saat deploy. |
| **Ansible Core** | **GNU General Public License v3.0 (GPL-3.0-only)** | ⚠️ **agra HANYA memanggil CLI `ansible` / `ansible-playbook` via `subprocess.run()`** (dynamic linking sebagai external tool, bukan static linking / import Python module Ansible ke kode agra sendiri). Sesuai interpretasi umum FSF dan Free Software Foundation, **pemanggilan CLI tool terpisah via subprocess TIDAK membuat karya agra menjadi turunan (derivative work) GPL v3**. Anda bertanggung jawab sendiri atas instalasi Ansible Core di virtual environment Anda (lihat `README.md` bagian Install → `pip install ansible-core>=2.16` di-install manual terpisah). |
| **Node Exporter** | **Apache License 2.0** | ✅ Kompatibel penuh dengan MIT agra, ditarik oleh user saat deploy. |
| **Nginx** | **BSD 2-Clause License** | ✅ Kompatibel MIT, ditarik / diinstall oleh user saat deploy. |
| **Keepalived** | **GNU General Public License v2.0+ (GPL-2.0-or-later)** | ⚠️ Sama seperti Ansible: dipanggil / diinstall sebagai system package OS terpisah atau docker image osixia/keepalived ditarik langsung oleh user. Bukan bagian dari binary agra. |
| **PyYAML** | **MIT License** | ✅ Dependency Python CLI agra, kompatibel penuh dengan MIT agra. |

Jika ada ketidaksesuaian interpretasi lisensi yang perlu diklarifikasi, silakan buat Issue di repo agra untuk didiskusikan.
