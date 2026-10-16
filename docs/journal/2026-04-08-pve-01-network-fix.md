# Proxmox VLAN Networking Fix — pve-01 (2026-04-08)

> State as of 2026-10-10, not maintained. Current procedures: [pve-01 network](../runbooks/pve-01-network.md).

## Symptom

LXC containers could not reach the gateway (`*.*.*.1`) or any external network.
The Proxmox host itself worked fine, but all containers had no connectivity from day one.

## Cause

A VLAN tagging mismatch between Proxmox and UniFi:

- Proxmox `vmbr0` had the host IP directly on the bridge (untagged traffic)
- UniFi port had VLAN 27 as native — so untagged traffic from the host landed on VLAN 27 correctly
- But container traffic was sent **tagged as VLAN 27** through `nic0`
- UniFi cannot accept tagged VLAN 27 on a port where VLAN 27 is already native — so container packets were dropped

## Fix

Two changes were required:

### 1. Proxmox `/etc/network/interfaces`

Moved the host IP off the raw bridge onto a VLAN 27 subinterface. This makes host traffic explicitly tagged as VLAN 27 instead of untagged.

**Before:**
```
auto vmbr0
iface vmbr0 inet static
    address *.*.*.*/24
    gateway *.*.*.1
    bridge-ports nic0
    bridge-stp off
    bridge-fd 0
    bridge-vlan-aware yes
    bridge-vids 27-28
```

Current bridge configuration: [pve-01 network](../runbooks/pve-01-network.md#host-bridge).

### 2. UniFi port profile

The port connected to pve-01 used native VLAN 27 with no tagged VLANs. The fix changed native VLAN 27 to VLAN 23 and allowed VLAN 27 tagged, matching the host's explicitly tagged traffic. The later VLAN 39 addition is recorded in the [current switch profile](../runbooks/pve-01-network.md#switch-port).

With this change, VLAN 27 traffic arrives at UniFi **tagged** (from `vmbr0.27`) and is correctly placed on VLAN 27. VLAN 23 is native but unused by this host.

### Why This Works

```
Container (tagged VLAN 27)
    → vmbr0 bridge
    → nic0 (passes tagged VLAN 27)
    → UniFi port (VLAN 23 native, VLAN 27 tagged) ✓
    → VLAN 27 network / gateway *.*.*.1
```

Previously the host IP was on `vmbr0` directly, sending untagged traffic. UniFi native VLAN 27 accepted that, but couldn't also accept tagged VLAN 27 from containers on the same port. Moving the host IP to `vmbr0.27` makes all traffic from this host explicitly tagged — no ambiguity.

## Lessons

2026-10-10: all running LXCs had correct VLAN tags without any fixup service; the 'lost after every reboot/apply' claim was never reproduced.

A `pve_vlan_fixup` role (2026-04-09) was never installed on pve-01 and was removed in 2026-10.
