# Pinned Software Versions

Single place to check what version of each service is deliberately pinned, and how to
bump it. Existing to close a gap identified during an internal infrastructure review
(finding 7): `latest`/`stable` tags meant any `ansible-playbook` run could silently pull
a new major version.

---

## Pinned

Pinned tags live in `ansible/roles/monitoring/defaults/main.yml` (`*_image_tag`)
and `ansible/roles/homeassistant/defaults/main.yml`; those files are the only source.

The five pre-existing image versions were captured from running containers on
2026-07-21. Mosquitto and Zigbee2MQTT were pinned when the Zigbee stack was
deployed, from the published image tags. Bump a version deliberately in
`defaults/main.yml`, then follow the runbook below.

## Deliberately not pinned

| Component | Why not |
|---|---|
| Jellyfin (`jellyfin` apt package) | Not critical; would need an exact-version `apt` pin, different mechanism than the image-tag vars above — deferred. |
| k3s (`INSTALL_K3S_CHANNEL: stable`) | The install task is guarded by `creates: /usr/local/bin/k3s`, so re-running the playbook never re-triggers install/upgrade — `stable` doesn't cause the "upgrade on every run" risk the Docker `latest` tags did. Revisit (switch to `INSTALL_K3S_VERSION`) only if the node is ever rebuilt from scratch, since a bare `stable` rebuild could land many minor versions ahead — Kubernetes doesn't support skipping several minors in one jump. |

---

## Bumping a pinned version

1. Check the upstream release notes for the new tag.
2. Edit the `*_image_tag` var in the role's `defaults/main.yml`.
3. `ansible-playbook playbooks/<service>.yml` — compose recreates only the changed
   service.
4. Verify the service came up (see the relevant runbook).
5. Commit — the diff is exactly one line, which is the point of pinning.
