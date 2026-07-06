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
    address *.*.*.100/24
    gateway *.*.*.1
    bridge-ports nic0
    bridge-stp off
    bridge-fd 0
    bridge-vlan-aware yes
    bridge-vids 27-28
```

**After:**
```
iface nic0 inet manual

auto vmbr0
iface vmbr0 inet manual
    bridge-ports nic0
    bridge-stp off
    bridge-fd 0
    bridge-vlan-aware yes
    bridge-vids 27-28

auto vmbr0.27
iface vmbr0.27 inet static
    address *.*.*.*/24
    gateway *.*.*.1
```

### 2. UniFi port profile

Changed the port connected to pve-01:

| Setting | Before | After |
|---|---|---|
| Native VLAN | 27 | 23 |
| Tagged VLANs | — | 27, 28 |

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

## Post-Apply: Persist veth VLAN Assignments

The `bpg/proxmox` provider does not persist bridge VLAN assignments for veth interfaces. After every `terraform apply` (or container restart), run the following on **pve-01** to restore VLAN 27 tagging for each container:

```bash
# restart containers to createn bridge link
pct stop 200 && pct start 200
pct stop 201 && pct start 201
pct stop 202 && pct start 202
pct stop 203 && pct start 203

# nut-01 (CT 200)
bridge vlan add dev veth200i0 vid 27 pvid untagged

# monitoring-01 (CT 201)
bridge vlan add dev veth201i0 vid 27 pvid untagged

# plex-01 (CT 202)
bridge vlan add dev veth202i0 vid 27 pvid untagged

# homeautomation-01 (VM 203, VLAN 39) — VM, not LXC; VLAN tag handled by vmbr0 trunk, no manual veth fixup needed
```

Verify each with:

```bash
bridge vlan show dev veth200i0
bridge vlan show dev veth201i0
bridge vlan show dev veth202i0
bridge vlan show dev veth203i0
```

Expected output for each — VLAN 27 should appear with `PVID Egress Untagged`:

```
port              vlan-id
veth200i0         27 PVID Egress Untagged
```

> Note: the container must be running for its veth interface to exist.

## TODO

- Consider moving Proxmox host to VLAN 23 (UniFi management network) long-term for cleaner separation between hypervisor management and workloads
- Automate the veth VLAN fix above as an Ansible task targeting pve-01 (requires adding pve-01 to inventory)

<br>

+ *Investigate why Terraform `bpg/proxmox` provider does not persist bridge VLAN assignments for veth interfaces — may need a post-apply provisioner - That's a provider limitation, not a config error.*