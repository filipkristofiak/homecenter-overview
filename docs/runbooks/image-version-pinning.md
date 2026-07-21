# Image Version Pinning — monitoring stack and Home Assistant

## What was done

Replaced `latest` (Prometheus, Grafana, PVE exporter), `alpine` (status-page nginx), and
`stable` (Home Assistant) image tags with explicit, deliberately-chosen versions.
`ansible-playbook` runs can no longer silently pull a newer major version mid-deploy —
upgrades now require a one-line diff.

Home Assistant's `docker-compose.yml` was also converted from a static file (`copy`d
verbatim, no variable substitution at all) to a Jinja template, matching the pattern
`monitoring`'s compose file already used — this was a prerequisite for the version var
to be injectable.

Versions were captured from what was **already running**, not from upstream "latest" at
the time of writing — so applying this change was a no-op for the running containers;
only future upgrades become deliberate. See
[`docs/architecture/image-versions.md`](../architecture/image-versions.md) for the
current pinned table and the bump procedure going forward.

---

## File layout

```
ansible/roles/monitoring/
  defaults/main.yml                 prometheus_image_tag, pve_exporter_image_tag,
                                     grafana_image_tag, nginx_image_tag
  templates/docker-compose.yml.j2   image: lines reference the vars above

ansible/roles/homeassistant/
  defaults/main.yml                 homeassistant_image_tag
  templates/docker-compose.yml.j2   new — replaces files/docker-compose.yml
  tasks/main.yml                    "Deploy docker-compose.yml" task: copy -> template
```

---

## How the pinned versions were determined

Not from Docker Hub/GHCR "latest" — read directly off the running containers, so the
pin matches reality exactly:

```bash
# Monitoring stack (CT 201, via pve-01)
ssh -i ~/.ssh/homelab_id ***@*.*.*.* 'pct exec 201 -- docker exec <container> <binary> --version'
# grafana server -v / prometheus --version / nginx -v
# pve-exporter version came from the dist-info directory (no --version flag):
#   pct exec 201 -- docker exec <container> sh -c \
#     'find / -iname "*pve_exporter*dist-info*" -maxdepth 8'

# Home Assistant (homeautomation-01)
ssh -i ~/.ssh/homelab_id ***@*.*.*.* 'docker exec <container> python3 -c \
  "import homeassistant.const as c; print(c.__version__)"'
```

---

## Verify

```bash
ansible-playbook playbooks/monitoring.yml
ansible-playbook playbooks/homeassistant.yml -l homeautomation-01
```

Expected: no container recreation, since the pinned tags match what's already deployed —
a diff-free run confirms the pin matches reality.

```bash
pct exec 201 -- docker ps --format '{{.Image}}'
```

Expect explicit tags (`grafana/grafana:12.4.2`, etc.) instead of `latest`/`alpine`.

**Result (2026-07-21):** ran clean, all services up, no unexpected restarts.

---

## Key decisions

| Decision | Value | Reason |
|---|---|---|
| Where versions live | Role `defaults/main.yml`, one var per image | Matches the existing pattern (`grafana_admin_password`, port vars) — no new file or layer needed |
| What to pin to | Currently-running version, read live off the containers | Guarantees the migration itself causes zero drift; upgrades become separate, deliberate commits |
| Plex | Left unpinned | Not a critical service; apt exact-version pinning is a different mechanism, deferred |
| k3s | Left unpinned | Install task guarded by `creates:`, so `stable` doesn't get re-resolved on every run the way Docker `latest` did; see [`docs/architecture/image-versions.md`](../architecture/image-versions.md) for the rebuild caveat |
