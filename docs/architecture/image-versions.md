# Pinned Software Versions

Single place to check what version of each service is deliberately pinned, and how to
bump it. Exists to close a reproducibility gap: `latest`/`stable` tags meant any
`ansible-playbook` run could silently pull a new major version mid-deploy.

---

## Pinned

| Component | Var | Role defaults file | Current version |
|---|---|---|---|
| Prometheus | `prometheus_image_tag` | `ansible/roles/monitoring/defaults/main.yml` | `v3.11.1` |
| PVE Exporter | `pve_exporter_image_tag` | `ansible/roles/monitoring/defaults/main.yml` | `3.9.0` |
| Grafana | `grafana_image_tag` | `ansible/roles/monitoring/defaults/main.yml` | `12.4.2` |
| status-page nginx | `nginx_image_tag` | `ansible/roles/monitoring/defaults/main.yml` | `1.31.2-alpine` |
| Home Assistant | `homeassistant_image_tag` | `ansible/roles/homeassistant/defaults/main.yml` | `2026.5.4` |

All five vars were set to whatever was already running in production at the time of
pinning (2026-07-21) — see [`docs/runbooks/image-version-pinning.md`](../runbooks/image-version-pinning.md)
for how each was discovered. Bumping a version is a deliberate, one-line diff to the
relevant `defaults/main.yml`, followed by a normal playbook run.

## Deliberately not pinned

| Component | Why not |
|---|---|
| Plex (`plexmediaserver` apt package) | Not a critical service; would need an exact-version `apt` pin (`name: "plexmediaserver={{ version }}"`), different mechanism than the image-tag vars above — deferred. |
| k3s (`INSTALL_K3S_CHANNEL: stable`) | The install task is guarded by `creates: /usr/local/bin/k3s`, so re-running the playbook never re-triggers install/upgrade — `stable` doesn't cause the "upgrade on every run" risk the Docker `latest` tags did. Currently running `v1.36.2+k3s1` on k3s-01. Revisit (switch to `INSTALL_K3S_VERSION`) only if the node is ever rebuilt from scratch, since a bare `stable` rebuild could land many minor versions ahead — Kubernetes doesn't support skipping several minors in one jump. |

---

## Bumping a pinned version

1. Check the upstream release notes for the new tag.
2. Edit the `*_image_tag` var in the role's `defaults/main.yml`.
3. `ansible-playbook playbooks/<service>.yml` — compose recreates only the changed
   service.
4. Verify the service came up (see the relevant runbook).
5. Commit — the diff is exactly one line, which is the point of pinning.
6. Update the version in the table above.
