# UniFi Network — pve-01 Deployment Notes

Not a strict runbook. Things to keep in mind when provisioning new services on pve-01
so the network side doesn't become a surprise later.

> The authoritative UniFi config snapshots live in `network/unifi/configs/` (fetched via `tools/unifi/fetch_config.py`).
> This doc reflects the current state: all-UniFi switches, zone-based firewall.

---

## Network overview

| Network | VLAN | Subnet | Notes |
|---------|------|--------|-------|
| Default | untagged | `*.*.*.1/24` | Management, UniFi controller, workstations |
| *** | 27 | `*.*.*.1/24` | All pve-01 LXC containers and VMs live here |
| *** | 28 | `*.*.*.1/24` | Family zone |
| HomeAuto | 39 | `*.*.*.1/24` | For homeAutomation with 3rd party integrations. Firewall rules |
| *** | 38 | `*.*.*.1/24` | Isolated; smart home devices |
| *** | 32 | `*.*.*.1/24` | Isolated; guest WiFi |

pve-01 itself sits on VLAN 27. All LXC containers are on VLAN 27.

---

## How pve-01 connects to the network

pve-01 has a single 2.5 GbE NIC connected to the **UDR7**.
Proxmox uses a VLAN-aware Linux bridge (`vmbr0`) — all VLANs are trunked over
that one physical link and tagged at the Proxmox level.

**The switch port pve-01 is connected to must be configured as a trunk** (tagged
for every VLAN pve-01 needs to carry). In UniFi this means the port profile should
have VLAN 27 — and any future VLANs — in the tagged list.
Native/untagged VLAN on that port should match however Proxmox management is set up
(usually the Default/untagged network so the Proxmox UI is reachable without VLAN tags).

If you add a container on a new VLAN later, the switch port profile needs updating
before the container can reach the network — easy to forget.

---

## IP allocation on VLAN 27

DHCP range starts at `.6` — the `.1–.5` block is effectively reserved for
infrastructure (gateway `.1`, etc.). Static assignments for LXC containers start at `.*`.

| IP | Host | Service |
|----|------|---------|
| `*.*.*.1` | UDR 7 | VLAN 27 gateway |
| `*.*.*.*` | nut-01 (CT 200) | NUT UPS server |
| `*.*.*.*` | monitoring-01 (CT 201) | Grafana + Prometheus |
| `*.*.*.*` | plex-01 (CT 202) | Plex Media Server |
| `*.*.*.*` | TrueNAS VM | NAS |


When provisioning a new container, claim the next `.*x` address and CT ID before
running `terraform apply` — nothing enforces this automatically.

---

## Zone-based firewall

UniFi now uses zone-based firewall policies (not the old per-VLAN rule tables).
A few things to keep in mind when adding new services:

[REDACTED]

---

## mDNS / local discovery

mDNS is enabled on VLAN 27 (`mdns_enabled: true` in the network config). This means:

- Home Assistant's host networking and mDNS-based device discovery (Chromecast,
  Apple TV, etc.) works on VLAN 27 without extra configuration.
- IoT devices on VLAN 38 are on a separate L2 segment — mDNS does **not** cross
  VLANs automatically. If HA needs to discover IoT devices via mDNS, enable the
  UniFi mDNS proxy between IoT and VLAN 27 in Network → Settings → Multicast DNS.

---

## Adding a new LXC container — network checklist

1. Claim the next free static IP (currently `.*`) and CT ID (`204`).
2. Add the IP and CT ID to `terraform/pve-01/variables.tf` and `terraform.tfvars`.
3. Confirm the `vlan_id = 27` is set in the Terraform `network_interface` block.
4. If the container needs to be on a different VLAN, update the switch trunk profile
   on the port pve-01 is connected to.
5. If the new service needs to be reachable from IoT or WAN, add zone policy rules
   before the service goes live — don't rely on defaults.
6. Update the IP allocation table above.
