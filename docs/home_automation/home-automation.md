# Home Automation Deployment

## Overview

Home automation stack running on an existing Proxmox homelab server. All services run as Docker containers inside a dedicated Debian 12 VM managed by Proxmox. The Zigbee coordinator is a network-attached device (no USB passthrough required).

---

## Hardware

### Homelab Server (Proxmox host)
- CPU: Intel i5-13500T
- Storage: 3× 6TB Seagate IronWolf 5400 RPM
- Max power draw: ~150W (including disk spinup peaks)
- Hypervisor: Proxmox VE
- Network: Ubiquiti UniFi

### Zigbee Coordinator
- Device: **SLZB-06U** (Smlight) — radio TI **CC2652P** (device reports `model: SLZB-06U`, `zb_hw: CC2652P` at `http://*.*.*.*/ha_info`)
- Firmware: Z-Stack (Texas Instruments) coordinator firmware — Zigbee2MQTT adapter `zstack`, not `ember`
- Connection: Ethernet, 802.3af PoE from UDR7 Port 1 (`UDR7 Port 1 - Zigbee`: native network VLAN 39, tagged VLANs blocked)
- Network ports: TCP 6638 (serial-over-network, used by Z2M), HTTP 80 (device web UI)
- Placement: **VLAN 39**, `*.*.*.*` — fixed UniFi DHCP reservation, as confirmed by the owner. The coordinator shares HA's subnet; Z2M → TCP 6638 stays inside the VLAN and needs no firewall rule.
- Physical: keep it 1–2 m+ from the UDR7 — the router is also the 2.4 GHz Wi-Fi AP.

### Zigbee Devices (planned)

| Category | Purpose | Protocol |
|---|---|---|
| Smart plugs with power monitoring | Main PC workstation, homelab server, TV hub, Rancilio espresso machine | Zigbee |
| Radiator TRVs | Per-room radiator thermostat control | Zigbee |
| mmWave presence sensors | Motion/presence detection for night lighting | Zigbee |
| RGBW LED (red, floor level) | Night lighting triggered by presence | Zigbee |

**Smart plug notes:** Verify max current rating per plug (most are 16A/3680W — sufficient for all listed devices). The homelab server plug should be monitored-only, not switched.

**TRV notes:** Standard M30×1.5 thread fits most European radiator valves; adapters available for others.

**Presence sensor notes:** mmWave (e.g. Aqara FP2 or Tuya mmWave modules) preferred over PIR — detects stationary presence, not only movement.

---

## Proxmox VM

- **VM ID:** 203
- **Hostname:** `homeautomation-01`
- **OS:** Debian 12 (Bookworm) — provisioned via cloud-init image (not LXC template)
- **vCPUs:** 2 (affinity pinned to E-cores 12–19 via `qm set 203 --affinity 12-19` after provisioning)
- **RAM:** 2 GB
- **Disk:** 32 GB virtio (HA recorder database grows over time; resize with `qm disk resize`)
- **IP:** `*.*.*.*/24` — VLAN 39, gateway `*.*.*.1`
- **Network:** virtio NIC on `vmbr0`, VLAN tag 39. Isolated zone — explicit firewall rules for all cross-VLAN access (see Network section).
- **Runtime:** Docker + Compose plugin (no Docker Desktop, no Portainer required)
- **Terraform resource:** `proxmox_virtual_environment_vm` (not `proxmox_virtual_environment_container`)

---

## Services

All three services are managed by `ansible/roles/homeassistant` and deployed to
`/opt/homeassistant/docker-compose.yml` on VM 203. HA keeps its existing config volume.

### Mosquitto (MQTT broker)
- Image: `eclipse-mosquitto:2.1.2-alpine`
- Role: routes MQTT publish/subscribe messages between Zigbee2MQTT and Home Assistant; it does not manage Zigbee pairing.
- Port: `1883` bound to `127.0.0.1` on the VM for host-networked HA. Z2M reaches `mosquitto:1883` over Docker's bridge.
- Volumes: `./mosquitto/config` (read-only) and `./mosquitto/data`.
- Anonymous access disabled; two distinct accounts, `z2m` and `homeassistant`, are created by Ansible.

### Zigbee2MQTT
- Image: `koenkk/zigbee2mqtt:2.14.2`
- Role: pairs Zigbee devices via the SLZB-06U on TCP 6638, then translates their commands and reports to MQTT.
- Depends on Mosquitto; its broker password and Zigbee network key come from vaulted Ansible host variables.
- Data/config volume: `./zigbee2mqtt/data` (included in the VM backup).
- Zigbee radio adapter: `zstack` (TI CC2652P), channel 20. Ansible seeds the PAN IDs and channel on first install; Zigbee2MQTT owns `configuration.yaml` afterward. The network key remains in Ansible-managed `secret.yaml`. Do not regenerate it once devices are paired.
- Frontend: enabled on port 8080, published **only to VM loopback**. From an internal workstation, use `ssh -i ~/.ssh/homelab_id -L 8080:127.0.0.1:8080 ***@*.*.*.*` and open `http://127.0.0.1:8080`. No UniFi rule for 8080 is required.
- Time zone: `Europe/Prague`.

### Home Assistant
- Image: `ghcr.io/home-assistant/home-assistant:2026.5.4`
- Install type: **HA Container** (plain Docker container — no Supervisor or add-on store).
- Role: automation engine and UI. Add the MQTT integration once at **Settings → Devices & services**, broker `localhost:1883`, user `homeassistant`; then Z2M's MQTT discovery makes paired devices appear in HA.
- Network mode: `host` for mDNS and device discovery.
- Volumes: `./config:/config`, `/etc/localtime` (read-only).
- **No `privileged: true` required** — Zigbee is TCP-based, not USB passthrough.

---

## Docker Compose

Ansible renders the actual Compose file from
`ansible/roles/homeassistant/templates/docker-compose.yml.j2`. HA's web UI
is reachable on VLAN 39; Mosquitto 1883 and the Z2M frontend 8080 bind to VM
loopback. HA (host networking) connects to `localhost:1883`, while Z2M (Docker
bridge) connects to `mosquitto:1883`.

---

## Network / UniFi Notes

### VLAN placement rationale

The VM runs on **VLAN 39** — a dedicated isolated zone, not on VLAN 27.

VLAN 27 has unrestricted inter-zone traffic with VLAN 23 and VLAN 28. Placing HA there would give a compromised VM direct access to the Proxmox host (`*.*.*.*`), TrueNAS (`*.*.*.*`), and family PCs on VLAN 28. HA runs third-party integrations and has a web-facing UI — its blast radius must be contained.

VLAN 39 is a new isolated zone (same policy as IoT/Guest): outbound internet allowed, no unsolicited inbound from other VLANs, cross-VLAN access only via explicit firewall rules.

### VLAN 39

| Field | Value |
|---|---|
| VLAN ID | 39 |
| Subnet | `*.*.*.*/24` |
| Gateway | `*.*.*.1` |
| DHCP range | `*.*.*.*–.254` |
| Zone | Isolated |
| VM IP | `*.*.*.*` (static, `homeautomation-01`) |
| Zigbee coordinator | `*.*.*.*` (SLZB-06U, PoE from UDR7 Port 1) |

### Required UniFi firewall rules

All cross-VLAN traffic to/from VLAN 39 is denied by default (isolated zone). Add these explicit allow rules:

| Direction | Source | Destination | Port | Purpose |
|---|---|---|---|---|
| Inbound | VLAN 23, 27, 28 | `*.*.*.*` | TCP 8123 | HA web UI |
| Inbound | `*.*.*.*` (monitoring-01) | `*.*.*.*` | TCP 9100 | Prometheus scraping |
| Inbound | management host | `*.*.*.*` | TCP 22 | Ansible SSH |
| Outbound | `*.*.*.*/24` | WAN | TCP 443 | Cloud integrations, updates |

Everything else from VLAN 39 toward internal VLANs is dropped.

No rule is needed for the Zigbee coordinator: Z2M and the SLZB-06U are both on VLAN 39, so TCP 6638 never crosses the firewall. Its web UI (`http://*.*.*.*`) is reachable from internal VLANs through the zone policy `Allow trafic to Isolated` (Internal → Isolated, all ports).

### Proxmox bridge

`vmbr0` must be VLAN-aware with a trunk port to the UniFi switch. The VM's virtio NIC gets VLAN tag 39. No change to the bridge config is needed if VLAN 27 tagging already works (same bridge, different tag).

---

## Components and message flow

![Dark component diagram: on pve-01, Home Assistant exchanges MQTT messages with Zigbee2MQTT through Mosquitto inside VM 203. Zigbee2MQTT reaches the SLZB-06U over VLAN 39 via USW2.5 and UDR7; the coordinator exchanges Zigbee messages with the SONOFF plug.](home-automation-components.png)

[Editable draw.io source](home-automation-components.drawio).

---

## Planned Automations

| Automation | Trigger | Action |
|---|---|---|
| Night lighting | Presence detected, time between ~23:00–07:00 | Turn on floor-level red LED at low brightness |
| Night light off | No presence detected | Turn off red LED after short delay |
| Radiator schedule | Time-based / presence-based | Adjust TRV setpoints per room |
| Power alerts | Plug reports wattage above threshold | Mobile notification |
| Energy dashboard | Continuous | Track kWh and cost per device in HA Energy panel |

---

## MQTT credentials and Zigbee network identity

The three secrets (`z2m_mqtt_password`, `ha_mqtt_password`, and
`zigbee_network_key`) are encrypted in
`ansible/inventory/host_vars/homeautomation-01.yml`. Ansible creates the Mosquitto
password file with salted hashes and keeps Z2M's `secret.yaml` root-readable
only. It seeds Z2M's `configuration.yaml` just once: Zigbee2MQTT writes to this
file itself, and subsequent playbook runs must not overwrite its network state.
The broker has `allow_anonymous false`. Changing a vaulted MQTT password
regenerates both broker accounts and restarts the broker and Z2M; changing the
Zigbee network key after devices join requires re-pairing them.

To complete HA's MQTT integration in its UI, retrieve the HA account password
from the root-only file `/opt/homeassistant/mosquitto/ha-mqtt-password` on VM 203.
Do not put it in HA's `configuration.yaml`; the MQTT integration stores its
credentials through the HA UI.

---

## HA Core Limitations vs Supervised

Since this runs HA Core (Docker), the following are relevant:

- No add-on store — Z2M and Mosquitto run as separate Compose services
- No Supervisor UI — upgrade by changing image tags in Ansible and rerunning the playbook
- HACS (community integrations) can still be installed manually
- HA integrations and automations configured in the UI persist in `./config`
- This is intentional: HA Container inside a Debian VM keeps the host generic.

---

## Directory Layout (deployed)

```text
/opt/homeassistant/
├── docker-compose.yml
├── config/                  # Home Assistant state
├── mosquitto/
│   ├── config/             # mosquitto.conf and hashed passwd
│   ├── data/               # broker persistence
│   └── ha-mqtt-password    # root-only; enter once in HA UI
└── zigbee2mqtt/
    └── data/               # configuration.yaml, secret.yaml, device state, coordinator backup
```