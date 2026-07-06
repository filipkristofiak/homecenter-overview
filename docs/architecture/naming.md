# Homelab Naming Conventions

This document defines naming conventions for all infrastructure components, virtual machines, containers, VLANs, and DNS in the homelab.  
The goal is **clarity, scalability, and role-based abstraction**.

---

## 1. Physical Workload Nodes

Physical servers or devices that **run services directly**, including containers.

| Prefix  | Example    | Description |
|---------|------------|-------------|
| `lab-*` | `lab-01`   | General-purpose node, Raspberry Pi, small servers, running direct workloads (containers, apps). |

**Notes:**
- Two-digit numbering (`01`, `02`) is sufficient for <100 nodes.
- Names are **hardware-agnostic**. Hardware details are documented separately in `docs/infrastructure/hardware.md`.
- Example: `lab-01` (Pi running Home Assistant, Prometheus/Grafana), `lab-02` (Pi media server).

---

## 2. Hypervisors / Virtualization Hosts

Physical machines that **host virtual machines**.  
These are infrastructure layer devices.

| Prefix   | Example    | Description |
|----------|------------|-------------|
| `pve-*`  | `pve-01`   | Proxmox hypervisor host |

**Notes:**
- Two-digit numbering works for up to 99 hypervisors.
- Hypervisors never host direct services themselves (except for orchestration/management).
- Examples:
  - `pve-01` – Laptop running Proxmox
  - `pve-02` – Mac Mini hypervisor

---

## 3. Virtual Machines (VMs)

Virtual machines deployed on hypervisors.  
Name after the **service** it runs or the **purpose** it serves — whichever is clearer.

**Patterns:**

| Pattern | Example | When to use |
|---------|---------|-------------|
| `<service>` | `truenas` | Single well-known service with its own identity |
| `<purpose>-<role>-XX` | `dwh-master-01`, `dwh-compute-03` | Cluster or multi-VM workload with a shared purpose |
| `<purpose>-<role>-<env>-XX` | `dwh-master-prod-01` | Optional: add environment when staging/prod separation matters |

**Roles examples:**
- `core` → main apps/services  
- `monitor` → Prometheus/Grafana, monitoring stack  
- `auth` → Home Assistant, authentication services  
- `db` → Database servers  
- `proxy` → Reverse proxy / Traefik / Nginx

**Notes:**
- No `vm-` prefix required — the hypervisor inventory provides that context.
- Use two-digit numbering (`01`, `02`) when multiple VMs share a purpose.
- VM host is **documented in inventory**; not reflected in name.

---

## 4. Containers

Containers are **service instances** inside a host or VM.

| Prefix      | Example          | Description |
|-------------|------------------|-------------|
| `<service>` | `home-assistant` | Service container name |

**Notes:**
- Containers do **not get host-level prefixes**.
- Naming reflects the **service/application**, not the host.
- Examples: `home-assistant`, `prometheus`, `grafana`, `nginx`.

---

## 5. VLANs

Logical segmentation of the network.

| VLAN ID | Name    | Purpose         | Notes |
|---------|---------|-----------------|-------|
| *       | ***     | Management      | UniFi controller, management traffic — `*.*.*.*/24` |
| *       | ***     | Homelab nodes   | All pve-01 LXC containers and VMs — `*.*.*.*/24` |
| *       | ***     | Trusted devices | Family laptops and PCs — `*.*.*.*/24` |
| *       | ***     | Guest Wi-Fi     | Internet only, isolated from internal networks — `*.*.*.*/24` |
| *       | ***     | IoT isolation   | Smart home devices, isolated from internal networks (internet allowed) — `*.*.*.*/24` |
| *       | ***     | Home automation | Home automation VM, isolated zone, explicit firewall rules — `*.*.*.*/24` |

**Notes:**
- VLAN names are human-readable, lowercase.
- IP subnets and static assignments: [`docs/network/ip-addressing.md`](../network/ip-addressing.md).

---

## 6. Internal DNS / Hostnames

Use fully qualified names within the lab network: (`lab.***`)

**Examples:**
- `lab-01.***` – Pi node
- `pve-01.***` – Proxmox hypervisor host
- `truenas.***` – TrueNAS VM
- `dwh-master-01.***` – multi-VM workload
- Containers use hostnames + service names internally: `home-assistant.lab-01.***`

**Notes:**
- Maintains uniqueness across physical and virtual hosts.
- Supports clean DNS resolution, reverse lookups, and inventory mapping.

---

## 7. Optional Future Expansions

- Add `nas-*` prefix for dedicated storage devices.

---

## Summary

| Layer           | Prefix             | Example                  |
|-----------------|--------------------|--------------------------|
| Physical node   | `lab-*`            | `lab-01`                 |
| Hypervisor host | `pve-*`            | `pve-01`                 |
| Virtual machine | `<service>` or `<purpose>-<role>-XX` | `truenas`, `dwh-master-01` |
| Container       | `<service>`        | `prometheus`             |
| VLAN            | `<name>`           | `***`                  |
| Internal DNS    | `<hostname>.lab.***` | `pve-01.lab.***`   |
