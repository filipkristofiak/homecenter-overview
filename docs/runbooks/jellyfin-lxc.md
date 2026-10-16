# Jellyfin Media Server LXC — pve-01

Jellyfin runs as a privileged LXC and reads its TrueNAS media share through a read-only NFS mount.
Ansible installs the server and manages first-run setup, libraries and the restricted `kodi` playback user through its HTTP API.

Why Jellyfin gets its own LXC instead of a VM or a spot on `k3s-01`: see
[k3s-node-plan.md non-goals](../architecture/k3s-node-plan.md#non-goals) —
iGPU device-passthrough is trivial to bind-mount into an LXC, but needs full
passthrough or SR-IOV into a VM/k3s node for no gain on a single-host lab.

---

## Pre-flight checklist

- [ ] Debian 12 template available on pve-01: [template prerequisites](pve-01-rebuild.md#3-templates-on-pve-01)
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

Enable nesting before Ansible: see the `lxc_jellyfin` comment in `terraform/pve-01/main.tf` (without it SSH logins take ~25 s, [journal](../journal/2026-04-13-lxc-ssh-slow.md)).

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

Export configuration: [TrueNAS NFS exports](truenas-vm.md#nfs-exports).

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
| CPU | 4 cores | Library scans and their follow-on metadata/artwork passes can saturate 2 cores and starve the API |
| RAM | 2048 MB | Comfortable for 1-2 simultaneous streams |
| Disk | 16 GB | OS + Jellyfin metadata, artwork, transcode temp (media is on TrueNAS) |
| NFS mount options | `defaults,ro,_netdev,nofail,x-systemd.automount` | Read-only: Jellyfin never writes into the library (state lives in `/var/lib/jellyfin`), so the client refuses writes at the kernel level regardless of what the NFS server would permit — makes `Maproot User: root` harmless. `ro` must come *after* `defaults` — `defaults` expands to `rw,suid,dev,exec,auto,nouser,async` and options are applied left-to-right, so a leading `ro` gets silently overridden by the trailing `rw` inside `defaults`. Verify post-deploy: `findmnt -no OPTIONS /mnt/media \| grep -ow ro` |

Hostname naming rationale: [service naming](../architecture/naming.md).

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
