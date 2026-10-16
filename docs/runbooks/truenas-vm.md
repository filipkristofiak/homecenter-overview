# TrueNAS VM

## VM 100

TrueNAS SCALE runs as an appliance VM on pve-01. Guest identities: [IP addressing](../network/ip-addressing.md).

On pve-01, set the NIC's explicit VLAN tag and pass through both JMB582 controllers (the MAC below retains the public placeholder):

```bash
qm set 100 --net0 virtio=00:00:00:00:00:00,bridge=vmbr0,tag=27
qm set 100 --hostpci0 0000:03:00.0,pcie=1,rombar=0 --hostpci1 0000:05:00.0,pcie=1,rombar=0
```

Resulting passthrough configuration:

```text
hostpci0: 0000:03:00.0,pcie=1,rombar=0
hostpci1: 0000:05:00.0,pcie=1,rombar=0
```

## Pool and datasets

`spinners-01` is RAIDZ1 across 3×6 TB IronWolf disks, split 2+1 across the two JMB582 cards: `03:00.0` carries two members; `05:00.0` carries one member and has one free port. A failure of the two-member controller exceeds RAIDZ1's single-disk tolerance.

Datasets are `media` and `proxmox-backups`. Backup dataset settings: [set up or re-create](pve-01-backups.md#set-up-or-re-create).

## NFS exports

Configure the media export in TrueNAS SCALE under **Sharing → NFS**:

| Field | Value |
|---|---|
| Path | `/mnt/spinners-01/media` |
| Networks | `*.*.*.*/24` |
| Maproot User | `root` |
| Maproot Group | `wheel` (TrueNAS SCALE default for `root`, not `root` group) |

The Jellyfin client mounts this export read-only; see [client-side UID mapping and mount policy](jellyfin-lxc.md#truenas-nfs-export-settings). Configure the backups export per [pve-01 backups](pve-01-backups.md#set-up-or-re-create).

## Rebuild

1. Re-create or restore the TrueNAS boot/config disk; preserve the existing pool disks.
2. Set the NIC tag and `hostpci` lines on VM 100 as above, using the VM's own NIC MAC.
3. **Import** the existing `spinners-01` pool; never create it, since the disks hold data.
4. Recreate both NFS exports.
5. Verify from jellyfin with `findmnt /mnt/media`, and from pve-01 with `pvesm status | grep proxmox-backups`.

## Gotchas

- Don't pass through the onboard Intel controller `0000:00:17.0`: it has no FLR and causes DMAR faults ([incident](../journal/2026-08-01-truenas-sata-passthrough-fault.md)).
- JMB582 needs `rombar=0`, otherwise the guest sees no disks ([incident](../journal/2026-08-01-truenas-sata-passthrough-fault.md)).
- Guest and host log clocks differ, so compare timestamps with care ([incident](../journal/2026-08-01-truenas-sata-passthrough-fault.md)).

## Diagnostics

Run from a workstation with the `truenas` and `pve-01` SSH aliases. Replace disk names and time bounds with those for the fault being investigated; compare SMART cable-error counters against a recorded baseline.

```bash
# Pool state
ssh truenas -- 'zpool status -v spinners-01'

# Map disk serial (from TrueNAS alert) to /dev/sdX
ssh truenas -- "for d in /dev/sd?; do printf '%s: ' \$d; smartctl -i \$d | grep -E 'Serial Number|Device Model'; done"

# SMART health on a specific disk (199/UDMA_CRC is the cable-fault indicator)
ssh truenas -- "smartctl -a /dev/sdc | grep -E 'Reallocated|Pending|Uncorrectable|Command_Timeout|UDMA_CRC|SMART overall'"

# Kernel-level ATA/SCSI errors around a fault
ssh truenas -- "dmesg -T | grep -iE 'sdX|reset|error|timeout' | tail -60"

# TrueNAS VM's PCI passthrough config
ssh pve-01 -- "qm config 100"

# Host-side IOMMU/DMAR faults (account for the host/guest clock offset)
ssh pve-01 -- "journalctl -k --since '<pve-01-local-time>' --until '<pve-01-local-time>' | grep -iE 'vfio|iommu|reset|error|aer'"

# Map ata port -> PCI controller (to check which disks share a controller)
for d in sdb sdc sdd; do
  echo -n "$d -> "
  ssh truenas -- "readlink -f /sys/class/block/$d" | grep -oE 'ata[0-9]+'
done
ssh pve-01 -- "lspci -nn | grep -iE 'sata|ahci'"

# Screenshot a hung/headless VM console (read-only, safe)
ssh pve-01 -- "qm monitor 100" <<< "screendump /tmp/console.ppm"
scp pve-01:/tmp/console.ppm ./console.ppm

# recovery — not routine: force-stop and cold-start a wedged VM
ssh pve-01 -- "qm stop 100"
ssh pve-01 -- "qm start 100"

# recovery — not routine: post-recovery cleanup
ssh truenas -- "zpool scrub spinners-01"    # after resilver completes
ssh truenas -- "zpool clear spinners-01"    # after scrub reports 0 errors
```
