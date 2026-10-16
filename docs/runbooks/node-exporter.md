# Node Exporter — pve_lxc guests and pve-01

Node exporter supplies Linux metrics to Prometheus on TCP 9100 from every `pve_lxc` guest and pve-01.
Scrape targets are generated from `groups['pve_lxc'] + groups['proxmox_hosts']`.

---

## Deploy order

### 1. Install node exporter on all `pve_lxc` guests

```bash
cd ansible
ansible-playbook playbooks/node-exporter.yml
```

Ansible will install `prometheus-node-exporter` from the Debian apt repository and
enable it as a systemd service on each guest. The exporter listens on `0.0.0.0:9100`.

### 2. Redeploy Prometheus config

```bash
ansible-playbook playbooks/monitoring.yml
```

This pushes the updated `prometheus.yml` (with the `node` scrape job) and recreates
the Prometheus container to pick up the new config.

Alternatively, live-reload without restarting the container:

```bash
curl -X POST http://*.*.*.*:9090/-/reload
```

---

## Verify

Check that Prometheus can reach each target:

- Open `http://*.*.*.*:9090/targets` in a browser
- Every node target shows **State: UP**

Or query directly:

```bash
# from any host on VLAN 27 — spot-check one target
curl -s http://*.*.*.*:9100/metrics | head -5

# check Prometheus sees all targets as UP
curl -s 'http://*.*.*.*:9090/api/v1/targets' \
  | python3 -m json.tool \
  | grep -E '"job"|"health"'
```

---

## What works out of the box vs. what still needs configuration

### Works immediately after deploy

Node exporter exposes ~1000 metrics per host from the Linux kernel. Prometheus scrapes
and stores them with 30-day retention. No further config is needed for collection to work.

Metrics collected by default:

| Category | Examples |
|---|---|
| CPU | usage per core, idle, iowait |
| Memory | used, free, cached, buffers, swap |
| Disk I/O | read/write throughput, IOPS per device |
| Filesystem | used/free space per mount point |
| Network | bytes in/out, errors, drops per interface |
| System | load average, open file descriptors, uptime, running processes |

You can query raw data immediately at `http://*.*.*.*:9090/graph`. Example: paste
`100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)` to see
CPU usage across all scraped hosts.

### Not yet configured — needs follow-up

**Grafana dashboards** — data is stored but not visualised. The standard community
dashboard covers everything node exporter exposes and takes ~1 minute to import:

1. Open Grafana → Dashboards → Import
2. Enter ID `1860` (Node Exporter Full) → Load → select the Prometheus datasource

Only pve-01 NVMe rules exist today ([pve-01-host.md#alerts](pve-01-host.md#alerts)); proposed guest rules: [backlog](../backlog/ops-follow-ups.md).

---

## Key decisions

| Decision | Value | Reason |
|---|---|---|
| Package | `prometheus-node-exporter` (apt) | Ships in Debian repos, no manual binary download needed |
| Port | `9100` | Default for node exporter; no config change required |
| Firewall | None on VLAN 27; VLAN 39 rule for homeautomation-01 | VLAN 27 is a trusted zone. homeautomation-01 is on isolated VLAN 39, where TCP 9100 is one of its explicit UniFi allow rules |
| Target generation | Jinja2 loop over `groups['pve_lxc'] + groups['proxmox_hosts']` | Stays in sync with inventory; adding a new host to `hosts.yml` is enough |

---

## Adding a new container to scraping

1. Add the host to `pve_lxc` in `ansible/inventory/hosts.yml`
2. Run the node exporter playbook against the new host:
   ```bash
   ansible-playbook playbooks/node-exporter.yml --limit <new-host>
   ```
3. Re-run the monitoring playbook to regenerate and push the prometheus config:
   ```bash
   ansible-playbook playbooks/monitoring.yml
   ```

No edits to the prometheus template or monitoring role are needed.
