# pve-01 Tuning Ideas

Candidates for the `pve_host` Ansible role. Not yet implemented unless noted.

---

## Memory

### vm.dirty_ratio / vm.dirty_background_ratio

Controls how much dirty page cache accumulates before the kernel flushes to disk.
Defaults (20% / 10%) are tuned for desktops. Lower values reduce write latency spikes
under I/O load on a hypervisor.

---

## CPU governor

Current Proxmox default is `powersave` — slow to ramp up, can cause latency on sudden
bursts (e.g. a Jellyfin transcode starting).

`performance` locks CPU at max frequency permanently — unnecessary power draw on a
mostly-idle host.

**Recommendation: `schedutil`** — scales frequency based on actual scheduler load,
reacts fast enough for bursts, idles low. Best fit for a mostly-idle homelab.
`ondemand` is a viable alternative but `schedutil` is strictly better on modern kernels.

---

## Networking

### BBR + fq — skip for this setup

BBR (TCP congestion control) and fq (packet scheduler) are designed for WAN traffic
with variable latency and packet loss. All traffic in this lab is LAN-local — NFS
between Jellyfin and TrueNAS, inter-container calls, monitoring scrapes. Latency is
sub-millisecond and packet loss is zero; TCP congestion is never the bottleneck.

These settings would not interfere with the VLAN bridge setup (different layers —
BBR/fq are L3/L4, VLAN tagging is L2), but the benefit is negligible for local
workloads. Not worth the extra variable given networking is already fragile.

If applied, the sysctl entries would be:

```
net.ipv4.tcp_congestion_control = bbr
net.core.default_qdisc = fq
```

---

## Proxmox-specific

### No-subscription apt repo

If not subscribed to Proxmox Enterprise, the enterprise repo is enabled by default and
throws errors on every `apt update` — which surfaces as noise in every Ansible run
that touches the host. Switch to the no-subscription repo.

### Subscription nag removal

Cosmetic. Removes the nag dialog from the Proxmox web UI on login.

---

## ZFS (if pools are ever added to pve-01 directly)

ZFS ARC will consume all available RAM by default. Cap it before adding any pool,
otherwise guests will be starved of memory under read-heavy workloads.
