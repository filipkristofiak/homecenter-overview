# Node Exporter — pve_lxc containers

## What was done

Added a `node_exporter` Ansible role that installs `prometheus-node-exporter` on all
LXC containers in the `pve_lxc` group. Prometheus on `monitoring-01` is updated to
scrape all four containers on port 9100. Targets are generated dynamically from the
Ansible inventory so adding a new container requires no changes to the prometheus config.

---

## File layout

```
ansible/
  playbooks/node-exporter.yml      entry-point playbook (targets pve_lxc)
  roles/node_exporter/
    defaults/main.yml              node_exporter_port: 9100
    tasks/main.yml                 install prometheus-node-exporter, enable service
  roles/monitoring/
    defaults/main.yml              node_exporter_port: 9100 (used in template)
    templates/prometheus.yml.j2    node scrape job — targets built from groups['pve_lxc']
```

---

## Deploy order

### 1. Install node exporter on all containers

```bash
cd ansible
ansible-playbook playbooks/node-exporter.yml
```

Ansible will install `prometheus-node-exporter` from the Debian apt repository and
enable it as a systemd service on each container. The exporter listens on `0.0.0.0:9100`.

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
- All four targets should show **State: UP**

Or query directly:

```bash
# from any host on VLAN 27 — spot-check one target
curl -s http://*.*.*.*:9100/metrics | head -5

# check Prometheus sees all targets as UP
curl -s 'http://*.*.*.*:9090/api/v1/targets' \
  | python3 -m json.tool \
  | grep -E '"job"|"health"'
```

Expected targets:

| Host         | Port | Label         |
|--------------|------|---------------|
| `*.*.*.*`    | 9100 | nut-01        |
| `*.*.*.*`    | 9100 | monitoring-01 |
| `*.*.*.*`    | 9100 | plex-01       |
| `*.*.*.*`    | 9100 | homeautomation-01 |

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
CPU usage across all containers.

### Not yet configured — needs follow-up

**Grafana dashboards** — data is stored but not visualised. The standard community
dashboard covers everything node exporter exposes and takes ~1 minute to import:

1. Open Grafana → Dashboards → Import
2. Enter ID `1860` (Node Exporter Full) → Load → select the Prometheus datasource

**Alerting rules** — no alerts fire yet. Useful starting points to add to a
`prometheus.yml` `rule_files` block:

| Alert | Condition | Why it matters |
|---|---|---|
| High disk usage | filesystem > 85% full | LXC disks are fixed-size; no autogrow |
| High memory | memory used > 90% | containers have hard RAM limits set in Terraform |
| Node down | target unreachable for > 2m | catches container crashes or network issues |

**Alertmanager** — even with rules defined, Prometheus needs Alertmanager running to
route alerts somewhere (email, Slack, etc.). Not yet deployed.

---

## Key decisions

| Decision | Value | Reason |
|---|---|---|
| Package | `prometheus-node-exporter` (apt) | Ships in Debian repos, no manual binary download needed |
| Port | `9100` | Default for node exporter; no config change required |
| Firewall | No new rules needed | All containers are on VLAN 27 (trusted zone) — inter-container traffic is unrestricted |
| Target generation | Jinja2 loop over `groups['pve_lxc']` | Stays in sync with inventory; adding a new container to `hosts.yml` is enough |

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
