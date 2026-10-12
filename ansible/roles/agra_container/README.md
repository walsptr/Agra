# Role: agra_container (internal)

Helper dipakai semua role service (grafana, prometheus, node_exporter, nginx,
keepalived) untuk menjalankan satu container — satu-satunya tempat logic
`docker run`. Bukan role yang dipanggil langsung dari playbook.

| Variabel | Default | Deskripsi |
|---|---|---|
| `agra_container_name` | `""` | Nama container |
| `agra_container_image` | `""` | `<image>:<tag>` |
| `agra_container_options` | `[]` | Opsi `docker run` sebelum image (tanpa `--name`/`--label`) |
| `agra_container_command` | `[]` | Argumen setelah image |
| `agra_container_stable_seconds` | `5` | Lama container wajib tetap `running` tanpa restart setelah role jalan (0 = skip) |

Perilaku: pull jika image belum ada → container dibuat ulang jika image id,
spec (hash `options + image + command`, disimpan di label `agra.spec`) atau
status running berbeda → handler pending dari role pemanggil di-flush →
container wajib tetap running.

```yaml
- name: Grafana (Docker) - Run container
  ansible.builtin.include_role:
    name: agra_container
    apply:
      tags: ['grafana', 'docker', 'container']
  vars:
    agra_container_name: "{{ grafana_container_name }}"
    agra_container_image: "{{ grafana_image }}:{{ grafana_tag }}"
    agra_container_options: [--restart=always, --network=host, ...]
  tags: ['grafana', 'docker', 'container']
```
