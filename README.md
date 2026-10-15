# homecenter — a homelab run like production

Infrastructure-as-code for my single-node homelab that I designed, built, and operate
end-to-end: virtualization, storage, network segmentation, monitoring, and automation — 
Manages LXC containers and VMs on Proxmox using  Terraform and Ansible. Documented as
runbooks

The lab exists for two reasons: to run real services for my home, and to be a permanent
playground for infrastructure and data-platform skills.

<p align="center">
  <a href="docs/architecture/homelab-architecture.drawio.png">
    <img src="docs/architecture/homelab-architecture.drawio.png" alt="Homelab architecture diagram" width="850">
  </a>
</p>

---

## Project Structure

```
homecenter/
│
├── docs/
│   ├── architecture/         # naming conventions, overview
│   ├── infrastructure/       # hardware inventory, node specs
│   ├── network/              # network diagram
│   ├── runbooks/             # per-service recovery guides
│   └── future_planning/      # hardware repurposing, lab ideas
│
├── ansible/
│   ├── inventory/
│   │   └── hosts.yml
│   ├── playbooks/            # one playbook per service
│   └── roles/                # homeassistant, jellyfin, monitoring, nut
│
├── terraform/
│   └── pve-01/               # LXC/VM definitions for pve-01
│   
├── network/
│   └── unifi/
│       └── configs/              # JSON exports (device, networks, firewall, wlan, ports)
|
└── tools/
    ├── pve/
    │   ├── status.py             # resource-overview TUI
    │   ├── requirements.txt
    │   └── README.md             # setup and usage
    └── unifi/
        ├── fetch_config.py       # snapshots UniFi config via API
        ├── requirements.txt
        └── README.md             # setup and usage
```

---

## The stack at a glance

| Layer | Technology | What I do with it |
|---|---|---|
| Hypervisor | Proxmox VE on a 14-core / 20-thread Intel host | LXC containers + KVM virtual machines, PCI controller passthrough, CPU pinning |
| Provisioning | Terraform (`bpg/proxmox` provider) | Declarative container/VM definitions, cloud-init templates, API-token auth |
| Configuration | Ansible | One role per service, ansible-vault for secrets, idempotent re-runnable playbooks |
| Storage | TrueNAS SCALE VM, ZFS RAIDZ1 | Full SATA-controller passthrough for native disk access, NFS exports to services |
| Network | UniFi (2.5 GbE), VLAN-segmented | Zone-based firewall, isolated zones for untrusted workloads, trunked VLAN-aware bridge |
| Observability | Prometheus + Grafana + exporters | node-exporter fleet, Proxmox API exporter, custom textfile exporter, custom dashboards |
| Tooling | Python | UniFi config-snapshot tool with secret masking, terminal resource-overview TUI |

---

## Design decisions

**Everything is code, and the exceptions are documented.** Terraform provisions the
guests; Ansible configures the services inside them. Where the Proxmox API has genuine
gaps (raw LXC config entries, feature flags restricted to root), the manual steps are
written down as comments next to the exact resource they affect — so a rebuild is a
checklist, not archaeology.

**Blast radius drives placement.** Most services run as containers on the trusted
server VLAN. The home-automation stack — which runs third-party integrations and has a
web-facing UI — got a full VM on its own *isolated* VLAN instead, with an explicit
allowlist firewall policy (UI port in, SSH for Ansible, one port for Prometheus scraping;
the Zigbee coordinator lives inside the same VLAN, so its traffic never crosses the
firewall). The media player gets the same treatment: an isolated VLAN with exactly one
allow rule, to Jellyfin. Same hypervisor, deliberately different trust level.

**Root is the deployment user — deliberately.** Ansible connects as root with a
dedicated SSH key. The LXC appliance containers have no other users by design, so
sudo would add a layer without adding a boundary. The real privilege boundaries live
at the hypervisor and VLAN level, which is where the hardening effort goes.


**Storage gets native hardware.** ZFS wants to talk to real disks. The NAS VM receives
the entire SATA controller via PCI passthrough rather than virtualized disks — SMART,
cache flushing, and error reporting all work as if bare-metal, while the hypervisor
keeps its own NVMe boot pool untouched.

**Monitoring watches the platform, not just the apps.** Prometheus scrapes a
node-exporter on every guest (targets generated dynamically from the Ansible
inventory — adding a host to the inventory is the whole onboarding process), a
Proxmox-API exporter for hypervisor and per-guest metrics using a scoped read-only
token, and a small custom textfile exporter I wrote for UPS battery/load/runtime
metrics. Custom Grafana dashboards join guest names onto metrics with PromQL.

**Network config is version-controlled, even when the vendor doesn't help.** A Python
tool snapshots the UniFi controller configuration (networks, firewall zones and
policies, port profiles, WLANs) through its REST API into diffable JSON — with
recursive masking of secret fields — so network changes show up in `git diff` like
any other infrastructure change.

**Secrets are boring on purpose.** API tokens and passwords live in ansible-vault;
Terraform state and variable files are excluded from version control; the monitoring
exporter authenticates with a revocable read-only token rather than a user password.

---

## What it actually runs

- **Media**: Jellyfin in a container, serving libraries from a ZFS dataset over NFS and
  configured through its own HTTP API by Ansible (first-run wizard, libraries, a
  restricted playback user); the Kodi box sits on its own isolated Media VLAN whose
  only path inward is a single allow rule to Jellyfin's port
- **Home automation**: Home Assistant, Mosquitto and Zigbee2MQTT in an isolated VM; a
  PoE-powered network Zigbee coordinator sits on the same VLAN, so radio traffic never
  crosses a zone boundary, and the broker and Z2M frontend listen only on loopback
- **Power resilience**: NUT server monitoring a USB-attached UPS, exposing status
  network-wide and feeding Prometheus
- **Backups**: a weekly snapshot-mode `vzdump` of the Home Assistant VM to an NFS
  dataset on the TrueNAS pool — off the NVMe that runs everything, with the untested
  restore and the remaining gaps written down rather than glossed over
- **Observability**: the Prometheus/Grafana stack described above, monitoring
  everything including itself
- **Service health**: Periscope, a LAN-only dashboard and TUI on the monitoring
  container, checks every guest against a contract derived from the architecture
  diagrams — HTTP/TCP probes, Prometheus series, and a textfile collector on the HA VM
  reporting container health and Zigbee device availability
- **Kubernetes**: a single-node k3s cluster in a dedicated VM — a landing zone for
  stable home services and data-platform learning projects (Postgres, Redpanda,
  Dagster), with PVs on their own disk via the local-path provisioner

## Operations

Every service has a runbook: what was deployed, the key decisions and *why* (as a
decision table), pre-flight checklists, verification commands, and known follow-ups.
When something broke — containers apparently losing VLAN assignments after reboot, a
25-second SSH login delay traced through PAM into cgroup namespaces — the outcome was
a root-cause writeup and, where useful, an automated fix kept as code (e.g. a systemd
oneshot that re-derives VLAN assignments from container configs; a later re-check
showed the host no longer needs it, so it stays undeployed until the fault recurs).

The repo also tracks its own debt honestly: what's manual and why, what's not yet
automated, and the ordered plan to close each gap. I find that discipline — knowing
exactly where your infrastructure deviates from its description — is the actual skill;
the tools are interchangeable.

---

## Where it's heading

In-cluster workloads for the k3s node — Postgres, Redpanda (memory-capped), and
Dagster, tracked as code in this repo; a TrueNAS-backed storage class via
democratic-csi; Proxmox Backup Server on repurposed hardware; VPN-gated
remote access; and gradually pushing the remaining hand-managed pieces (NAS
configuration via its REST API, host network config) into code.

---

## Docs

- [Architecture diagram](docs/architecture/homelab-architecture.drawio.png) — editable in draw.io (embedded XML)
- [Milestones](#milestones)
- [Naming conventions](docs/architecture/naming.md)
- [Pinned image versions](docs/architecture/image-versions.md)
- [Git workflow](docs/git-workflow.md) — branch, commit and merge policy for humans and agents
- [IP addressing](docs/network/ip-addressing.md) - redacted
- [Hardware inventory](docs/infrastructure/hardware_inventory.md) - redacted
- [Network diagram](docs/network/diagram.md) - redacted
- [Home automation design](docs/home_automation/home-automation.md)
- Runbooks: [Home Automation](docs/runbooks/homeautomation-vm.md) · [Jellyfin](docs/runbooks/jellyfin-lxc.md) · [Monitoring](docs/runbooks/monitoring-lxc.md) · [Periscope](docs/runbooks/periscope.md) · [Service-health collector](docs/runbooks/service-health-collector.md) · [NUT](docs/runbooks/nut-server-lxc.md) · [TrueNAS](docs/runbooks/truenas-init-notes.md) · [TrueNAS SATA passthrough fault](docs/runbooks/truenas-sata-passthrough-fault.md) · [NVMe health](docs/runbooks/pve-01-nvme-health.md) · [pve-01 backups](docs/runbooks/pve-01-backups.md) · [k3s](docs/runbooks/k3s-vm.md) · [Image version pinning](docs/runbooks/image-version-pinning.md)

---

## Milestones

Key events from idea and blueprints to today's state.

<p align="center">
  <a href="docs/architecture/homecenter-milestones.png">
    <img src="docs/architecture/homecenter-milestones.png" alt="homecenter build timeline: from spec sheet to production" width="850">
  </a>
</p>