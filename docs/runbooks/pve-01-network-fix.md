# Proxmox VLAN Networking Fix — pve-01

## Problem

LXC containers could not reach the gateway (`*.*.*.1`) or any external network.
The Proxmox host itself worked fine, but all containers had no connectivity from day one.

## Root Cause

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

**Current host configuration (the original fix used `bridge-vids 27-28`; VLAN 39 was added later):**
```
iface nic0 inet manual

auto vmbr0
iface vmbr0 inet manual
    bridge-ports nic0
    bridge-stp off
    bridge-fd 0
    bridge-vlan-aware yes
    bridge-vids 27 39

auto vmbr0.27
iface vmbr0.27 inet static
    address *.*.*.*/24
    gateway *.*.*.1
```

The bridge VLAN list above matches the live `/etc/network/interfaces` on
`pve-01`. Keep VLAN 39 when rebuilding the host: VM 203 uses it for Home
Assistant. The original fix allowed VLANs 27 and 28; the later home automation rollout
replaced 28 with 39 on this host and its switch port.

### 2. UniFi port profile

The original fix changed the port connected to pve-01; the After column below reflects the later VLAN 39 update as recorded in the UniFi snapshot:

| Setting | Before | After |
|---|---|---|
| Native VLAN | 27 | 23 |
| Tagged VLANs | — | 27, 39 |

With this change, VLAN 27 traffic arrives at UniFi **tagged** (from `vmbr0.27`) and is correctly placed on VLAN 27. VLAN 23 is native but unused by this host.

## Why This Works

```
Container (tagged VLAN 27)
    → vmbr0 bridge
    → nic0 (passes tagged VLAN 27)
    → UniFi port (VLAN 23 native, VLAN 27 tagged) ✓
    → VLAN 27 network / gateway *.*.*.1
```

Previously the host IP was on `vmbr0` directly, sending untagged traffic. UniFi native VLAN 27 accepted that, but couldn't also accept tagged VLAN 27 from containers on the same port. Moving the host IP to `vmbr0.27` makes all traffic from this host explicitly tagged — no ambiguity.

## Post-Fix: Container veth VLAN

After `ifreload -a`, container veth interfaces may need VLAN 27 added manually (this should be persistent across reboots via the LXC config `tag=27`):

```bash
bridge vlan add dev veth200i0 vid 27 pvid untagged
```

Verify with:
```bash
bridge vlan show dev veth200i0
```

## Network Summary

| Host | IP | VLAN |
|---|---|---|
| pve-01 (Proxmox) | *.*.*.*/24 | 27 |
| Gateway | *.*.*.1 | 27 |
| nut-01 (LXC 200) | *.*.*.*/24 | 27 |

## Post-Apply: Verify LXC VLAN Assignments

On 2026-10-10, all three running LXCs had VLAN 27 `PVID Egress Untagged`
**without** `vlan-fixup.service` installed. The old claim that every reboot or
Terraform apply loses this assignment is not established for the current host.
Check after a reboot or apply; fix only an assignment that is actually missing:

```bash
pct list  # current LXCs: 200, 201, 205; VM 203 is not an LXC
bridge vlan show dev veth200i0
bridge vlan show dev veth201i0
bridge vlan show dev veth205i0

# Run only the command(s) for running containers missing VLAN 27:
bridge vlan add dev veth200i0 vid 27 pvid untagged
bridge vlan add dev veth201i0 vid 27 pvid untagged
bridge vlan add dev veth205i0 vid 27 pvid untagged
```

VM 203 uses VLAN 39 through `vmbr0` and needs no LXC veth command.
The affected container must be running for its veth interface to exist.

## TODO

- Consider moving Proxmox host to VLAN 23 (UniFi management network) long-term for cleaner separation between hypervisor management and workloads
