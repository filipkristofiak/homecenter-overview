# pve-01 host

pve-01 runs node exporter, a scheduled NVMe SMART textfile collector and smartd; `pve-host.yml` also applies kernel tuning.
Prometheus evaluates drive-health and collector-freshness rules; alerts are visible in Prometheus but not pushed anywhere.

## Apply

```bash
cd ansible
ansible-playbook playbooks/pve-host.yml     # kernel tuning, collector + smartd on pve-01
ansible-playbook playbooks/monitoring.yml   # scrape target + alert rules on monitoring-01
```

Both playbooks are idempotent. The monitoring playbook restarts the docker-compose
stack when the config changes (brief Prometheus/Grafana blip).

## Kernel tuning

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

Verify on pve-01:

```bash
sysctl vm.swappiness
# expected: vm.swappiness = 10
```

## NVMe collector

pve-01 runs everything (hypervisor + all LXC/VM disks) from a single NVMe drive
(rated 160 TBW), so its health is monitored from three angles:

1. **SMART metrics in Prometheus** — a collector script on pve-01 reads the NVMe SMART
   health log every 5 minutes and exposes it via node exporter's textfile collector.
2. **Alert rules in Prometheus** — wear, spare capacity, media errors, temperature and
   the drive's own critical-warning flag.
3. **smartd** — independent periodic self-checks on the host, mails `root` on failure
   (second signal path that does not depend on the monitoring stack).

As a side effect, pve-01 now also runs a full node exporter, so host-level CPU, memory,
disk-latency and filesystem metrics are in Prometheus alongside the guests.

The `tools/pve/status.py` terminal overview (see [pve-status.md](pve-status.md)) shows
a one-line health summary parsed from the collector's output, with the same thresholds
as the alert rules.


On pve-01:

| Path | Purpose |
|---|---|
| `/usr/local/bin/nvme-metrics` | collector (parses `nvme smart-log -o json`) |
| `/etc/systemd/system/nvme-metrics.{service,timer}` | schedule |
| `/var/lib/prometheus/node-exporter/nvme.prom` | output read by node exporter |

---

## Verify

```bash
# metrics exposed on the host
ssh -i ~/.ssh/homelab_id ***@*.*.*.* \
  'curl -s localhost:9100/metrics | grep ^nvme_'

# Prometheus scrapes pve-01 (job=node, nodename=pve-01, health=up)
open http://*.*.*.*:9090/targets

# alert rules loaded and inactive
open http://*.*.*.*:9090/alerts

# timer status on the host
ssh -i ~/.ssh/homelab_id ***@*.*.*.* \
  'systemctl list-timers nvme-metrics.timer; systemctl status nvme-metrics.service'
```

---

## Metrics

All series carry `device`, `model`, `serial` labels (plus `nodename=pve-01` from the
scrape config).

| Metric | Meaning |
|---|---|
| `nvme_critical_warning` | Drive's own warning bitfield. **0 = healthy.** Bits: 0x01 spare below threshold, 0x02 temperature, 0x04 reliability degraded, 0x08 media read-only, 0x10 volatile backup failed |
| `nvme_percentage_used_percent` | Consumed endurance estimate (can exceed 100) — the single best "life left" number |
| `nvme_available_spare_percent` / `..._threshold_percent` | Remapped-block reserve vs. the level at which the drive raises a critical warning |
| `nvme_media_errors_total` | Unrecovered media/data-integrity errors — should stay 0 forever |
| `nvme_temperature_celsius` | Composite temperature (throttling starts ~70–80 °C) |
| `nvme_written_bytes_total` / `nvme_read_bytes_total` | Cumulative traffic (derived: 1 data unit = 512 000 bytes) |
| `nvme_data_units_written_total` etc. | Raw counters from the SMART log |
| `nvme_unsafe_shutdowns_total`, `nvme_power_cycles_total`, `nvme_power_on_hours_total`, `nvme_error_log_entries_total` | Informational |

Useful queries:

```promql
# write rate in GB/day — Proxmox is notorious for grinding SSDs with small writes
rate(nvme_written_bytes_total[6h]) * 86400 / 1e9

# projected years to rated endurance (160 TBW for this drive)
(160e12 - nvme_written_bytes_total) / (rate(nvme_written_bytes_total[7d]) * 86400 * 365)
```

## Alerts

Defined in `roles/monitoring/templates/alerts.yml.j2`, visible at
`http://*.*.*.*:9090/alerts`.

| Alert | Condition | Severity | Action |
|---|---|---|---|
| NvmeCriticalWarning | bitfield > 0 for 5m | critical | check `nvme smart-log /dev/nvme0n1` on pve-01; decode bits above |
| NvmeSpareLow | spare ≤ threshold + 5 for 15m | critical | flash is failing — replace the drive |
| NvmeMediaErrors | any increase in 24h | critical | verify backups, plan replacement |
| NvmeWearHigh | wear ≥ 80 % for 1h | warning | order a replacement before 100 % |
| NvmeHighTemperature | > 70 °C for 15m | warning | check airflow / heatsink |
| NvmeMetricsStale | `nvme.prom` older than 30m | warning | `systemctl status nvme-metrics.service` on pve-01 |

---

## Troubleshooting

**NvmeMetricsStale fires / metrics missing:**

```bash
ssh -i ~/.ssh/homelab_id ***@*.*.*.*
systemctl status nvme-metrics.service     # last run + errors
/usr/local/bin/nvme-metrics               # run manually, prints traceback on failure
nvme list -o json                         # collector depends on this output shape
```

The collector writes atomically (temp file + rename); a failed run leaves the previous
`nvme.prom` in place, which is what the staleness alert catches.

**Manual health check (bypasses the whole stack):**

```bash
nvme smart-log /dev/nvme0n1
smartctl -a /dev/nvme0n1
```

---

## Key decisions

| Decision | Value | Reason |
|---|---|---|
| Collection method | textfile collector + timer | reuses existing node_exporter role; no extra daemon (vs. smartctl_exporter) |
| Collector language | Python 3, stdlib only | always present on PVE; parses `nvme smart-log -o json` |
| Interval | 5 min | SMART values change slowly; no point scraping faster |
| smartd | enabled alongside | independent alerting path (mail to root) if the monitoring stack is down |
| Alerting | Prometheus rules only | no Alertmanager deployed yet — alerts are visible, not pushed |

---

## Limitations

- **SMART won't predict everything** — controllers die suddenly without warning.
  Weekly VM 203 backups to TrueNAS mitigate NVMe loss for Home Assistant; other
  guests and host configuration remain outside that backup. See
  [pve-01-backups.md](pve-01-backups.md).
