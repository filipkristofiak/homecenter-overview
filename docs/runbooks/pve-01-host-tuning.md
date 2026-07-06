# Host Tuning — pve-01

Host-level kernel and OS settings applied to `pve-01` via Ansible.

## Ansible Playbook

**Role:** `ansible/roles/pve_host`  
**Playbook:** `ansible/playbooks/pve-host.yml`  
**Target host:** `pve-01` in the `proxmox_hosts` inventory group

```bash
ansible-playbook ansible/playbooks/pve-host.yml
```

---

## Settings

### vm.swappiness = 10

**File:** `/etc/sysctl.d/99-pve.conf`

Proxmox default is 60. Lower swappiness reduces the kernel's tendency to swap host
processes to disk, keeping RAM available for VMs and LXC containers. At 60 the kernel
will proactively page out host memory even under moderate pressure, which can cause
latency spikes in running guests.

`/etc/sysctl.d/99-pve.conf` is used rather than `/etc/sysctl.conf` because:
- Drop-in files are easier to audit and remove without touching system-wide config.
- Files in `/etc/sysctl.d/` load in lexicographic order; the `99-` prefix ensures
  these settings load last and override any earlier defaults (Proxmox ships its own
  tuning in lower-numbered files such as `10-pve.conf`).

#### Verify

```bash
sysctl vm.swappiness
# expected: vm.swappiness = 10
```
