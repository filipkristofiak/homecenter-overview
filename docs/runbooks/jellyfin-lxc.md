# Jellyfin Media Server LXC — pve-01

## What was done

Provisioned Jellyfin Media Server as a privileged LXC container on pve-01
(CT 205, `jellyfin`, `*.*.*.*`). Media is served from TrueNAS via NFS
(pool: spinners-01, dataset: media, mounted read-only at `/mnt/media` inside
the container).

Deployed and verified 2026-08-22: `jellyfin` service active, NFS mount
confirmed `ro`, library visible at `/mnt/media/movies`, web UI reachable on
`:8096`.

Why Jellyfin gets its own LXC instead of a VM or a spot on `k3s-01`: see
[k3s-node-plan.md non-goals](../architecture/k3s-node-plan.md#non-goals) —
iGPU device-passthrough is trivial to bind-mount into an LXC, but needs full
passthrough or SR-IOV into a VM/k3s node for no gain on a single-host lab.

---

## File layout

```
terraform/pve-01/
  variables.tf              added jellyfin_lxc_id, jellyfin_lxc_ip, jellyfin_truenas_nfs_server
  main.tf                   LXC container resource (jellyfin, CT 205, VLAN 27)
  terraform.tfvars.example  added jellyfin vars

ansible/
  inventory/hosts.yml       added jellyfin (pve_lxc group, *.*.*.*)
  inventory/host_vars/jellyfin.yml  vaulted jellyfin_admin_password, jellyfin_kodi_password
  playbooks/jellyfin.yml    entry-point playbook
  roles/jellyfin/
    defaults/main.yml       NFS source, mount path, mount options, Jellyfin repo URL,
                            API settings, libraries, playback users and their policy
    tasks/main.yml          install prerequisites, add Jellyfin repo, install, NFS mount, start service
    tasks/configure.yml     server state via the Jellyfin API: first-run wizard,
                            libraries, non-admin playback users
    handlers/main.yml       restart jellyfin, refresh apt cache
```

---

## Pre-flight checklist

- [ ] Debian 12 template on pve-01: `pveam update && pveam download local debian-12-standard_12.12-1_amd64.tar.zst`
- [ ] CT ID `205` is free: `pct list`
- [ ] IP `*.*.*.*` is not in use: `ping -c1 *.*.*.*`
- [ ] TrueNAS NFS share exported: pool `spinners-01`, dataset `media`, path `/mnt/spinners-01/media`
- [ ] TrueNAS NFS export allows VLAN 27 subnet (`*.*.*.*/24`)
- [ ] SSH key added to `terraform.tfvars`

---

## Deploy order

### 1. Provision the container (Terraform)

```bash
cd terraform/pve-01
terraform apply
```

### 2. Enable LXC nesting (manual, root@pam only)

The Terraform API token can't set the `features` block on privileged
containers — `main.tf` deliberately ignores drift on it
(`lifecycle { ignore_changes = [features] }`). Run this once, on pve-01, as
`root@pam` (not via the API token):

```bash
pct set 205 --features nesting=1
pct shutdown 205 && pct start 205
```

Without this, `systemd-logind` can't start inside the container and every
SSH login — including each Ansible task in the next step — stalls ~25s. Root
cause: [`lxc-ssh-slow.md`](lxc-ssh-slow.md).

### 3. Configure Jellyfin (Ansible)

```bash
cd ansible
ansible-playbook playbooks/jellyfin.yml
```

Override NFS variables if they differ from defaults:

```bash
ansible-playbook playbooks/jellyfin.yml \
  -e jellyfin_truenas_nfs_server=*.*.*.* \
  -e jellyfin_truenas_nfs_path=/mnt/spinners-01/media
```

The playbook also configures the server through the Jellyfin HTTP API
(`tasks/configure.yml`), so no first-run clicks are needed:

- **Wizard** (fresh install only): admin `jellyfin` with the vaulted
  `jellyfin_admin_password`, metadata language `en`, country `CZ`.
- **Libraries**: `Movies` → `/mnt/media/movies`, `TV Shows` →
  `/mnt/media/tv_shows`, created when missing and scanned once after a change.
  Default library options, so Jellyfin identifies titles itself (TMDB/OMDb).
- **Playback users**: `kodi` (pi5), created with `jellyfin_kodi_password`;
  policy enforced every run: not admin, no deletion, no remote control of
  other users, all libraries.

Every step reads first and writes only on drift; a second run reports
`changed=0`. `--check` runs the reads but skips the API writes.

---

## TrueNAS NFS export settings

Already exists, verified live via `midclt call sharing.nfs.query` on TrueNAS
(id 1) — no new export needed, no changes required for Jellyfin:

| Field | Value |
|---|---|
| Path | `/mnt/spinners-01/media` |
| Networks | `*.*.*.*/24` |
| Maproot User | `root` |
| Maproot Group | `wheel` (TrueNAS SCALE default for `root`, not `root` group) |

> **UID mapping note**: the Debian package creates the `jellyfin` system user
> at install time with a dynamically assigned UID — check `id jellyfin`
> inside the container after install. Simplest approach: set Maproot User to
> `root` during initial setup, then tighten once confirmed working.

Mounting `ro` (see [Key decisions](#key-decisions)) is what actually makes
`root` maproot safe here: the container can't write to `/mnt/media` at all,
so it doesn't matter what UID the NFS server would let it write as. A
dedicated TrueNAS user scoped to Jellyfin's UID would only matter if you
later enable a Jellyfin option that writes metadata/artwork back into the
media folders — at that point, mount read-write and revisit maproot.

---

## Key decisions

| Decision | Value | Reason |
|---|---|---|
| Deployment target | Privileged LXC (not VM, not k3s) | iGPU passthrough — bind-mounting `/dev/dri` into an LXC is two lines; into a VM/k3s node it's full passthrough or SR-IOV for no gain on a single-host lab |
| Hostname | `jellyfin` (no `-XX` suffix) | Matches `naming.md` §3 `<service>` pattern — single well-known service with its own identity, same as `truenas` |
| CT ID | `205` | Next free after k3s-01 (204) |
| IP | `*.*.*.*/24` | VLAN 27, static; next free after k3s-01 (.14) |
| CPU | 4 cores | Raised from 2 on 2026-10-13: with a library of ~3,900 media files, each library scan and its follow-on metadata/artwork pass held 2 cores at 100% for 45–90 min and starved the API. Applied live by Terraform, no container restart |
| RAM | 2048 MB | Comfortable for 1-2 simultaneous streams |
| Disk | 16 GB | OS + Jellyfin metadata, artwork, transcode temp (media is on TrueNAS) |
| NFS mount options | `defaults,ro,_netdev,nofail,x-systemd.automount` | Read-only: Jellyfin never writes into the library (state lives in `/var/lib/jellyfin`), so the client refuses writes at the kernel level regardless of what the NFS server would permit — makes `Maproot User: root` harmless. `ro` must come *after* `defaults` — `defaults` expands to `rw,suid,dev,exec,auto,nouser,async` and options are applied left-to-right, so a leading `ro` gets silently overridden by the trailing `rw` inside `defaults`. Verify post-deploy: `findmnt -no OPTIONS /mnt/media \| grep -ow ro` |

---

## Optional: Hardware transcoding (Intel Quick Sync)

pve-01 has an Intel iGPU. Jellyfin's hardware acceleration is free — no paid
tier required.

1. After `terraform apply`, add to `/etc/pve/lxc/205.conf` on pve-01:

```
lxc.cgroup2.devices.allow: c 226:* rwm
lxc.mount.entry: /dev/dri dev/dri none bind,optional,create=dir
```

2. Restart the container: `pct shutdown 205 && pct start 205`

3. Verify the GPU is visible inside: `pct enter 205 && ls /dev/dri`

4. Add the `jellyfin` user to the container's `render`/`video` groups so
   ffmpeg can open `/dev/dri` without running as root:
   `usermod -aG render,video jellyfin`

5. In Jellyfin Dashboard → Playback → Transcoding, set Hardware acceleration
   to `Intel QuickSync (QSV)` and select `/dev/dri/renderD128`.

---

## Migration history

Replaces Plex (`plex-01`, CT 202). Plex was decommissioned 2026-08-22 after
Jellyfin was verified working end-to-end: Terraform destroyed the container,
`ansible/roles/plex` and `playbooks/plex.yml` were removed, and every
inventory/doc reference to it was swept from the repo.
