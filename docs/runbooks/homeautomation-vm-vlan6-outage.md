# Home Automation VM Unreachable — VLAN 39 Uplink Missing Tag (2026-07-20)

## Symptom

Prometheus target health showed:
```
Error scraping target: Get "http://*.*.*.*:9100/metrics": dial tcp *.*.*.*:9100: connect: no route to host
```

`homeautomation-01` (VM 203, VLAN 39, `*.*.*.*`) was completely unreachable:
- No ping from local Mac
- No ping from pve-01
- No curl to any port

## Investigation

Checked and ruled out on pve-01:
- `qm config 203` — VM network interface config was correct (VLAN 39 tag present)
- `vmbr0` bridge config — correctly VLAN-aware, trunking VLAN 39

Traffic path is: pve-01 → USW2.5 (Homelab switch) → UDR7 Port 2 (uplink) → back down to pve-01/VM.
Since ICMP/TCP failed even from pve-01 itself to the VM, and local config looked fine, the problem
had to be on the switch/router path rather than the VM or Proxmox network config.

**Diagnostic step — put pve-01 directly on VLAN 39 to bypass the VM and test L2/L3 reachability
independent of the VM:**
```bash
bridge vlan add dev vmbr0 vid 39 self
ip link add link vmbr0 name vmbr0.39 type vlan id 39
ip addr add *.*.*.*/24 dev vmbr0.39
ip link set vmbr0.39 up
ping -c3 *.*.*.1   # gateway — this failed too
```
Gateway itself was unreachable from pve-01 on VLAN 39, which pointed at the switch/router uplink
rather than anything specific to the VM.

## Root Cause

**UDR7 Port 2 (the active switch uplink) had a per-VLAN exclusion list, and VLAN 39 was on it.**

This is a known gotcha in this network (see `docs/runbooks/unifi-network-pve01.md`):
UDR7 Port 2 excludes specific VLANs from the trunk by default. When VLAN 39 (HomeAuto) was created,
it was never removed from Port 2's exclusion list. Layer-2 frames tagged VLAN 39 were silently
dropped between the UDR7 router and the USW2.5 switch — before ever reaching pve-01 or the VM.
Nothing on the Proxmox side could have shown this; the outage was entirely on the router→switch
uplink.

This had likely been broken since VLAN 39 was originally created — unrelated to any recent change
on pve-01 or the VM itself.

## Fix

In UniFi, on UDR7 Port 2's port profile: removed VLAN 39 from the excluded-networks list (i.e.
allowed VLAN 39 across the uplink). The VM was immediately reachable and node-exporter scraped
successfully right after the change — no VM or Proxmox-side changes were needed.

## Cleanup

Removed the diagnostic VLAN 39 interface from pve-01 (no longer needed once the uplink was fixed):
```bash
ip link del vmbr0.39
bridge vlan del dev vmbr0 vid 39 self
```

## Lessons learned

- "no route to host" (not "connection refused") on a scrape target usually means an active
  network-layer block (ICMP reject / silently dropped frames) rather than a dead service —
  check the path before checking the service.
- When a whole VLAN is unreachable and local bridge/VM config checks out, test one layer up:
  put the Proxmox host itself on the suspect VLAN via a throwaway `vmbr0.<vid>` interface and
  ping the gateway. If even the gateway doesn't respond, the problem is upstream of Proxmox
  entirely (switch/router), not a VM or container config issue.
- **UDR7 Port 2 has a per-VLAN exclusion list that must be updated by hand whenever a new VLAN
  is added anywhere in the network** — this is easy to forget since nothing about creating a
  VLAN in UniFi warns you the uplink needs a matching update. Confirmed as the second time this
  exact class of bug has caused an outage.
- Diagnostic VLAN interfaces added to pve-01 for testing (`vmbr0.<vid>`) should be removed once
  the real fix is confirmed — they're not part of the permanent config and would be confusing
  clutter left behind.

## Key IPs

- pve-01 (Proxmox): `*.*.*.*`
- homeautomation-01 (VM 203, VLAN 39): `*.*.*.*`
- VLAN 39 gateway: `*.*.*.1`
