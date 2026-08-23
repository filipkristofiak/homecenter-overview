# SATA Port Allocation — New SSD (k3s PV tier) + HDD ("Storage Destroyer")

Status: **proposed, not yet executed** (2026-08-22). Decision record for adding two
drives — a 1TB SSD and the WD Red 4TB "Storage Destroyer" — given no free PCIe
slots and no bare-metal rework (no new cards, no BIOS/slot changes).

Related: [`docs/runbooks/truenas-sata-passthrough-fault.md`](../runbooks/truenas-sata-passthrough-fault.md)
(controller-passthrough incident + fix), [`docs/architecture/k3s-node-plan.md`](../architecture/k3s-node-plan.md)
(original Tier 2 PV plan), [`pve-01-specs.md`](pve-01-specs.md) (bare-metal inventory).

## Current topology (post 2026-08-03 fix)

| Bus | Owner | Occupancy |
|---|---|---|
| PCIe x1 slot 1 → JMB582 `0000:03:00.0` | TrueNAS VM (whole-controller VFIO) | 2/2 ports used — `spinners-01` members ***, *** |
| PCIe x1 slot 2 → JMB582 `0000:05:00.0` | TrueNAS VM (whole-controller VFIO) | 1/2 ports used — `spinners-01` member ***. **1 free port.** |
| PCIe x16 | reserved, future GPU | not available |
| Onboard `0000:00:17.0` (4 ports) | Proxmox host (returned after the fix — currently **unused**) | 0/4 used |

The onboard controller is the one that suspended `spinners-01` under sustained
write when whole-controller-passed to a VM (DMAR faults, no FLR — see fault
runbook). That failure mode is specific to **VFIO/IOMMU whole-device
passthrough**; the same controller is fine for host-native use (that's what
the fault doc means by "harmless on bare metal").

## Decision

| Drive | Target | Mechanism |
|---|---|---|
| **1TB SSD** (k3s PV tier) | Onboard `00:17.0`, individual disk into TrueNAS VM | `virtio-scsi` raw block passthrough (`qm set 100 -scsiN /dev/disk/by-id/ata-<ssd-serial>,backup=0`) — **not** the free port on `05:00.0` |
| **HDD** ("Storage Destroyer") | Onboard `00:17.0`, host-native | Proxmox owns it directly; attach as a virtual disk to whichever VM/LXC consumes it (`qm set <vmid> -scsiN /dev/disk/by-id/ata-<hdd-serial>`), or format host-side and bind-mount into an LXC |

Both new drives land on the onboard controller, used in two different ways —
host-native for the HDD, raw single-disk passthrough for the SSD. Neither
goes through `hostpci`/VFIO, so neither can reproduce the incident's fault
signature (that required an IOMMU-mediated DMA path; a QEMU-emulated
virtio-scsi backend and plain host I/O don't take that path).

## Option considered and rejected: SSD on the free `05:00.0` port

Simplest option on paper — plug the SSD into the spare port on the
already-passed-through card, TrueNAS just sees a new disk, no new passthrough
config. Rejected for two compounding reasons:

1. **Blast radius.** `05:00.0` also carries `spinners-01` member ***.
   The fault runbook's entire rationale for splitting the raidz1 across two
   controllers (line 69) was to stop one controller fault from threatening
   multiple pool members at once. Putting the PV pool's only disk behind the
   *same* controller as a raidz1 member reintroduces a correlated-failure
   path: a `05:00.0` fault now takes out a raidz1 member and all k3s
   persistent volumes in the same incident, right as you're also resilvering.
   `spinners-01` would survive (raidz1 tolerates 1 of 3), but you'd be
   handling two simultaneous incidents instead of one.
2. **Shared bandwidth.** JMB582 is native PCIe 3.0 x1 (~985 MB/s raw, less in
   practice) shared across both ports on the card. A SATA III SSD (up to
   ~550 MB/s) sustained-writing PV data while *** is resilvering or
   scrubbing (~200+ MB/s) pushes close to the link ceiling — degrading both
   at once under exactly the sustained-write conditions that caused the
   original incident.

Isolating the SSD onto the onboard controller (physically separate bus)
avoids both: no shared controller with any raidz1 member, no shared PCIe
link with pool I/O.

## Why not host-native ZFS/LVM for the SSD instead (skip TrueNAS entirely)

Would also solve the isolation/bandwidth problem, and is the more
conventional pattern for a second local-path-style disk. Not chosen because
the stated goal is specifically to run this SSD **as a TrueNAS-managed
service** (single-disk pool → `democratic-csi` → iSCSI/NFS storage class),
matching `k3s-node-plan.md` Tier 2 and functioning as the learning target for
TrueNAS-driven CSI. If that goal changes, host-native LVM-thin/ZFS on
`00:17.0` feeding k3s's local-path provisioner directly is the fallback with
zero TrueNAS/iSCSI dependency in the data path.

## Accepted trade-offs

- **SMART visibility on the SSD degrades in the TrueNAS guest** — individual
  disk (virtio-scsi) passthrough doesn't reliably forward SMART/SAT commands
  through to the guest (same caveat `truenas-init-notes.md` §1/§9 already
  documents for this pattern). Mitigation: monitor SSD SMART/wear from the
  **Proxmox host** (`smartctl -a /dev/disk/by-id/ata-<ssd-serial>`), which
  still has full native access to the controller — add to the existing
  node_exporter/SMART monitoring on `pve-01` rather than relying on TrueNAS's
  own SMART UI for this disk specifically.
- **Flush/cache ordering is weaker than full-controller passthrough** for
  both new drives. Acceptable: the SSD is explicitly "replaceable data only"
  per `k3s-node-plan.md` (TrueNAS downtime already hangs any pod mounting
  these volumes — same document already scopes this drive as non-critical),
  and the HDD never goes through ZFS at all in the recommended path.
- **HDD gets no ZFS/TrueNAS integration.** By design — the drive is already
  scoped in `pve-01-specs.md` as disposable/learning (pet-cam stream, HDD
  maintenance labs), so raw host ownership is not a downgrade from intended use.

## Verification before trusting either drive under real load

```bash
# Confirm both new disks land on the onboard controller, not the JMB582 cards
ssh pve-01 -- "ls -l /dev/disk/by-id/ | grep -iE '<ssd-serial>|<hdd-serial>'"
ssh pve-01 -- "readlink -f /sys/class/block/sdX"   # expect ata port under 00:17.0, not 03:00.0/05:00.0

# After wiring the SSD into TrueNAS via virtio-scsi, confirm the incident's DMAR
# fault signature does NOT reappear under sustained write (decisive re-test,
# same method as the original fix):
ssh pve-01 -- "journalctl -k --since '<local-time>' | grep -iE 'vfio|iommu|dmar'"

# SMART from the host side for the SSD (guest visibility is degraded by design)
ssh pve-01 -- "smartctl -a /dev/disk/by-id/ata-<ssd-serial> | grep -E 'Wear_Leveling|Media_Wearout|SMART overall'"
```
