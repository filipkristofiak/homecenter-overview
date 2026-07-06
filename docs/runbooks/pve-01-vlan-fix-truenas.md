# Proxmox Update & TrueNAS Network Fix — April 2026

## What was done

- Switched Proxmox from enterprise to no-subscription repository
- Ran `apt dist-upgrade` — routine update including kernel 6.17.2 → 6.17.13, ZFS 2.3.4 → 2.4.1, and various security patches
- Rebooted Proxmox host

## Issue: TrueNAS unreachable after reboot

TrueNAS VM came up on the wrong VLAN (management VLAN 23 instead of servers VLAN 27).

**Root cause:** The TrueNAS VM network config was missing the VLAN tag:
```
net0: virtio=00:00:00:00:00:00,bridge=vmbr0   ← no tag
```

**Fix applied:**
```bash
qm set 100 --net0 virtio=00:00:00:00:00:00,bridge=vmbr0,tag=27
```

## Lessons learned

- Always shut down TrueNAS cleanly from its UI before stopping the VM in Proxmox (ZFS doesn't like forced shutdowns)
- VLAN tags must be explicitly set on VM network interfaces in Proxmox — they don't persist implicitly
- Before future updates: snapshot VMs, shut down TrueNAS gracefully, then reboot

## Key IPs
- Proxmox: `*.*.*.***`
- TrueNAS: `*.*.*.***`
- Gateway: `*.*.*.1`