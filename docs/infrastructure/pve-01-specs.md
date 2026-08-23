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
- **500 GB *** NVMe**  
  - Used for Proxmox OS  
  - VM boot disks  
  - Not used for NAS pool

### **NAS Pool Drives**
- **3× Seagate IronWolf 6 TB**  
  - ZFS RAIDZ1 pool (`spinners`), dataset `media`
  - Connected to SATA III ports, passed through via full SATA controller passthrough to TrueNAS SCALE VM
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
[`sata-port-allocation-ssd-hdd.md`](sata-port-allocation-ssd-hdd.md)

---

## 🌐 Networking

- **Integrated Realtek 2.5 GbE NIC**  
  - Suitable for SMB/NFS traffic  
  - Can be upgraded with PCIe NIC if required (10 GbE etc.)

---

## 🔌 Expansion & Passthrough Notes

### **PCIe layout**
- **1× PCIe x16** slot (GPU, HBA, NIC)
- **2× PCIe x1** slots  
  - Available for additional SATA cards, NICs, etc.

### **SATA controller passthrough**
- The board includes **4× SATA ports** on a single controller.  
- For TrueNAS SCALE:  
  - Pass through the **entire SATA controller** for reliable ZFS operation.  
  - Avoid individual drive passthrough when possible.

---

## 📦 Current Role

- **Proxmox virtualization host** (NVMe)  
- **TrueNAS SCALE VM** (`*.*.*.*`) with full SATA controller passthrough — `spinners` RAIDZ1 pool, `media` dataset  
- Home Assistant, Jellyfin, Monitoring, NUT Server LXC containers  

---
