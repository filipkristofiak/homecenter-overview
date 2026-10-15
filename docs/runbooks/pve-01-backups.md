# pve-01 — Home Assistant backup to TrueNAS

## Purpose and current state

Protect Home Assistant's UI-configured integrations, automations, secrets, and database
against failure of pve-01's NVMe. VM 203 (`homeautomation-01`) runs from `local-lvm`
on that NVMe; its Docker `/config` bind mount is `/opt/homeassistant/config` inside
the VM. Terraform and Ansible can rebuild the VM and container but not that live
application state.

As deployed on 2026-10-10:

| Setting | Value |
|---|---|
| Source | VM 203 only; 32 GB virtual disk on `local-lvm` |
| Destination | TrueNAS VM 100 (`*.*.*.*`), dataset `spinners-01/proxmox-backups` on the passed-through HDD pool |
| Proxmox storage | NFS ID `proxmox-backups`, export `/mnt/spinners-01/proxmox-backups`, content **Backup** only, node `pve-01` |
| Job | Enabled, `pve-01`, VM 203 only, **Saturday 03:00**, snapshot mode, ZSTD compression, keep last **1** |
| First archive | `vzdump-qemu-203-2026_10_10-13_31_16.vma.zst`, 4,580,322,554 bytes (~4.27 GiB), listed on the NFS storage |

The dataset is owned by `root:root` with Unix permissions `700`, LZ4 compression,
and **no 500 GB quota or reservation**. It shares the existing `spinners-01` pool
with `media`; the pool's available space, not a separate 500 GB disk, is the limit.
The NFS export is writable, restricted to client **`*.*.*.*`** (pve-01),
with Maproot User/Group `root:root` and Mapall blank. The media export is separate.

The storage and job were configured in the TrueNAS and Proxmox UIs, **not in
Terraform or Ansible**. Re-create them after a host reinstall using the settings
above. On Proxmox, the definitions reside in `/etc/pve/storage.cfg` and
`/etc/pve/jobs.cfg`; do not assume these files survive an NVMe failure.

## Set up or re-create

1. In TrueNAS **Datasets**, create the Generic dataset `proxmox-backups` under
   `spinners-01`. Set owner/group to `root:root`, owner Read/Write/Execute,
   Group/Other no permissions (`700`). Do not alter `spinners-01/media`.
2. In **Shares → Unix (NFS) Shares**, export
   `/mnt/spinners-01/proxmox-backups`. Set **Allowed Hosts** to `*.*.*.*`
   (the client, **not** TrueNAS's own `*.*.*.*`); leave Networks empty,
   Read-Only off, Maproot User `root`, Maproot Group `root`, Mapall fields blank.
   Start NFS and enable its automatic start in **System → Services**.
3. In Proxmox **Datacenter → Storage → Add → NFS**, use ID `proxmox-backups`,
   server `*.*.*.*`, export `/mnt/spinners-01/proxmox-backups`, node
   `pve-01`, and content **Backup** only. Proxmox manages the mount: do not add
   a separate `/etc/fstab` entry. Confirm storage status is Active.
4. Run an initial backup under **VM 203 → Backup → Backup now** to that storage,
   snapshot mode, ZSTD. Then in **Datacenter → Backup → Add**, select node
   `pve-01`, **VM 203 only**, this storage, Saturday 03:00 (`sat 03:00`),
   snapshot mode, ZSTD, retention **Keep Last: 1**. Never select TrueNAS VM 100:
   it serves the backup destination, and its passed-through HDD pool is not
   included in a Proxmox VM backup.

## Check and restore

After the first run and periodically after scheduled runs:

- In Proxmox **Datacenter → Tasks**, check the VM 203 backup task completed
  successfully. **`proxmox-backups` → Backups** should show the latest VM 203
  archive. On the host, `pvesm list proxmox-backups --content backup` lists it.
- Check the archive's timestamp. With Saturday-only backups, loss of up to a
  week of HA changes is expected; missed/failed jobs make that window longer.
  The job currently does **not** repeat missed runs after downtime.
- Keep enough pool space to finish a new archive while the previous one exists;
  `keep-last=1` controls retained completed backups, not peak space during a run.
  The configured VM disk is 32 GB, while the first compressed archive was ~4.27 GiB.
- **A restore has not yet been demonstrated.** To test, use the archive's
  **Restore** action to a *different*, unused VM ID on `local-lvm`, with networking
  disabled or isolated to avoid duplicate IP/service conflicts. Boot that VM,
  verify HA starts and integrations/config are present, then remove the test VM.
  Never overwrite VM 203 just to test a backup.

On an actual NVMe failure, the TrueNAS HDD pool still contains the archive, but
its server is VM 100 on the failed host. Reinstall Proxmox and restore host
networking and the TrueNAS VM's PCI-controller passthrough first; re-create or
restore TrueNAS's boot/config disk, import `spinners-01`, and make the NFS export
available. Then re-add the Proxmox NFS storage and restore VM 203 from the archive.
The manual host/network steps are documented in
[pve-01-network-fix.md](pve-01-network-fix.md) and
[truenas-sata-passthrough-fault.md](truenas-sata-passthrough-fault.md).
Keep a TrueNAS configuration export, Proxmox host-specific config, Terraform
state, and the Ansible vault password somewhere **outside this NVMe**; this VM
backup does not contain them.

## Scope and limitations

This is one latest **full VM** backup per week, not a backup of all guests or
TrueNAS data. No k3s PVs, monitoring history, or Jellyfin metadata are covered.
Home Assistant's live database may only be crash-consistent under snapshot mode;
a successful restore test is the proof needed before relying on the archive.
The backup is on separate HDDs from the NVMe, so it addresses NVMe failure,
but both the source host and the destination TrueNAS VM occupy the same chassis.
It does not protect against loss of the whole machine/pool or accidental damage
to the sole retained copy. RAIDZ1 is disk redundancy, not another backup.
