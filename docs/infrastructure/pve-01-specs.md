# 🖥️ Bare Metal Inventory – Homelab Node

This document lists the complete physical hardware configuration of the homelab server, including storage, memory, CPU, motherboard, and expansion capabilities. It serves as the authoritative manifest for infrastructure‑as‑code, documentation, automation, and future expansion planning.

---

## 🔧 System Summary

| Component | Model / Description |
|----------|---------------------|
| **CPU** | Intel Core i5‑13500T (Raptor Lake‑S, 14 cores / 20 threads, 35W TDP) |
| **Motherboard** | Gigabyte B760 DS3H (ATX, LGA1700, 2× PCIe, 4× SATA, dual M.2) |
| **Memory (installed)** | 4× 16 GB DDR4 Kingston Fury 3200 MHz (64 GB) |
| **Primary Storage** | 500 GB NVMe – *** |
| **NAS Storage** | 3× 6 TB Seagate IronWolf HDDs |
| **Networking** | Integrated 2.5 GbE NIC |
| **PCIe Expansion** | 1× PCIe x16 slot, 2× PCIe x1 slots |

---

## 🧠 CPU — Intel Core i5‑13500T (LGA1700)

Specs verified from TechPowerUp and other CPU databases.  
*Reference: i5‑13500T — 14 cores (6P+8E), 20 threads, 35W TDP, 4.6 GHz boost*  
[1](https://www.techpowerup.com/cpu-specs/core-i5-13500t.c3005)

### **Key Specifications**
- **Architecture:** Raptor Lake‑S (10 nm)  
- **Cores/Threads:** 14 cores (6 P‑cores + 8 E‑cores), 20 threads  
- **Base Clock:** 1.6 GHz  
- **Max Turbo:** 4.6 GHz  
- **E‑core turbo:** up to 3.2 GHz  
- **Cache:** 24 MB L3  
- **TDP:** 35 W (PL1), up to 92 W turbo power (PL2)  
- **Socket:** LGA1700  
- **Memory Support:** DDR4‑3200 / DDR5‑4800  
- **PCIe Support:** PCIe 5.0 (CPU lanes)  
- **Integrated GPU:** Intel UHD Graphics 770  
- **Virtualization:** VT‑x, VT‑d supported  

---

## 🧩 Motherboard — Gigabyte B760 DS3H

Specs verified from Gigabyte’s official page.  
*Reference: 4 DDR slots, 2 M.2 slots (PCIe 4.0), 4 SATA ports, LGA1700 support*  
[2](https://www.gigabyte.com/Motherboard/B760-DS3H-rev-10)

### **Key Specifications**
- **Chipset:** Intel B760  
- **Form Factor:** ATX  
- **Socket:** LGA1700  
- **Supported CPUs:** 12th, 13th, 14th Gen Intel Core processors  
- **Memory Support:**  
  - 4× DIMM slots  
  - DDR5 on some variants, but *your model is DDR4* (per your RAM selection)  
  - Up to **128 GB** total RAM  
- **Storage Options:**  
  - **2× M.2 PCIe 4.0 x4** slots  
  - **4× SATA III 6 Gbps** ports  
- **Expansion Slots:**  
  - **1× PCIe x16 Gen4** (for GPUs or future HBA/NVMe bifurcation card)  
  - **2× PCIe x1 Gen3**  
- **Networking:** 2.5 GbE LAN  
- **Rear I/O Highlights:**  
  - HDMI + DisplayPort  
  - USB‑C 20 Gbps depending on revision  
- **Power:** 8+2+1 VRM phases (sufficient for i5‑13500T)

---

## 💾 Memory Configuration

### **Installed**
- 4× 16 GB Kingston Fury DDR4‑3200 (dual‑channel, 64 GB total)

This respects the motherboard’s maximum memory (128 GB).

---

## 🗄️ Storage

### **Primary (OS + VM storage)**
- **500 GB *** NVMe** (DRAM-less, single disk, no mirror)
  - Used for Proxmox OS  
  - VM boot disks  
  - Not used for NAS pool

### **NAS Pool Drives**
- **3× Seagate IronWolf 6 TB**  
  - ZFS RAIDZ1 pool (`spinners-01`), dataset `media`
  - Connected to two PCIe x1 JMB582 SATA cards (`0000:03:00.0`: 2 drives, `0000:05:00.0`: 1 drive + 1 free port); both cards are passed through whole to the TrueNAS SCALE VM (`hostpci0`/`hostpci1` on VM 100)
  - TrueNAS reachable at `*.*.*.*`

### **Planned**
- **1× WD Red 4 TB - 10y operational - a.k.a. Storage Destroyer**
  - Connected to onboard SATA ports (host-native, not passed through — see
    port allocation decision below)
  - Intended
    - after media migrated to nas drives
    - Pet camera stream
    - HDD maintenance labs (as it is reaching end of life)

- **1× 1TB SSD** — TrueNAS-managed single-disk pool for k3s persistent
  volumes (see `k3s-node-plan.md` Tier 2)

Port/passthrough allocation for both drives (why not full-controller
passthrough, why not the free JMB582 port):
[`sata-port-allocation-ssd-hdd.md`](../architecture/sata-port-allocation-ssd-hdd.md)

---

## 🌐 Networking

- **Integrated Realtek 2.5 GbE NIC**  
  - Suitable for SMB/NFS traffic  
  - Can be upgraded with PCIe NIC if required (10 GbE etc.)

---

## 🔌 Expansion & Passthrough Notes

### **PCIe layout**
- **1× PCIe x16** slot — free, reserved for a future GPU
- **2× PCIe x1** slots — both occupied by JMB582 2-port SATA cards, passed through to TrueNAS

### **SATA controllers**
| Controller | PCI address | Owner | Ports used |
|---|---|---|---|
| Onboard Intel (4 ports) | `0000:00:17.0` | Proxmox host (`ahci`) | 0/4 — free |
| JMB582 card, x1 slot 1 | `0000:03:00.0` | TrueNAS VM (`vfio-pci`) | 2/2 |
| JMB582 card, x1 slot 2 | `0000:05:00.0` | TrueNAS VM (`vfio-pci`) | 1/2 |

- The onboard controller is **not** passed through: whole-controller VFIO passthrough of it faulted under sustained write (no FLR, DMAR faults); see [TrueNAS SATA passthrough fault](../journal/2026-08-01-truenas-sata-passthrough-fault.md). It is fine for host-native use.
- `spinners-01` members are split 2+1 across the cards (`03:00.0`: 2, `05:00.0`: 1); a `03:00.0` fault still takes out two members, which RAIDZ1 does not survive.
- Allocation plan for new SATA drives: [SATA port allocation](../architecture/sata-port-allocation-ssd-hdd.md).

---

## 📦 Current Role

- **Proxmox virtualization host** (NVMe)  
- **TrueNAS SCALE VM** (`*.*.*.*`) with both PCIe SATA cards passed through — `spinners-01` RAIDZ1 pool, `media` dataset
- LXC containers: NUT Server, Monitoring, Jellyfin; VMs: Home Assistant (homeautomation-01), k3s-01

---
