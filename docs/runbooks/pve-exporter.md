# PVE Exporter — Proxmox metrics in Prometheus

## What was done

Added `prometheus-pve-exporter` to the monitoring stack on `monitoring-01`. It talks to the
Proxmox REST API (`pve-01:8006`) using an API token and exposes per-guest and host metrics
that Prometheus can scrape. This replaces SSH-based polling for resource data and feeds the
custom PVE Overview Grafana dashboard.

No SSH automation to the hypervisor — the exporter uses the same HTTP API as the Proxmox
web UI, authenticated with a read-only API token.

Source: [github.com/prometheus-pve/prometheus-pve-exporter](https://github.com/prometheus-pve/prometheus-pve-exporter) (Apache 2.0)

---

## File layout

```
ansible/
  group_vars/pve_lxc/
    defaults/main.yml           pve_host, pve_api_user, pve_api_token_name
    vault.yml                   pve_api_token_value (ansible-vault encrypted)
  roles/monitoring/
    defaults/main.yml           pve_exporter_port: 9221
    tasks/main.yml              deploys pve-exporter.yml config
    templates/
      docker-compose.yml.j2     pve-exporter service (prompve/prometheus-pve-exporter)
      pve-exporter.yml.j2       exporter config — token credentials
      prometheus.yml.j2         pve scrape job (metrics_path /pve, target pve-01)

dashboards/
  pve-overview.json             importable Grafana dashboard (6 panels)
```

---

## First-time setup

### 1. Create a PVE API token (Proxmox web UI)

The exporter needs a read-only API token. Do this once in the Proxmox web UI:

1. **Create a user** — Datacenter → Permissions → Users → Add
   - User: `prometheus`, Realm: `Proxmox VE authentication server` (the `pve` realm — not Linux PAM)
   - PAM ties to real OS users that can SSH; PVE realm is Proxmox-internal only
2. **Grant read-only access** — Datacenter → Permissions → Add → User Permission
   - Path: `/`, User: `prometheus@pve`, Role: `PVEAuditor`
3. **Create token** — Datacenter → API Tokens → Add
   - User: `prometheus@pve`, Token ID: `***`
   - Uncheck "Privilege Separation" (token inherits user role)
4. **Copy the UUID** — shown only once at creation

### 2. Add the token to vault

```bash
cd ansible
ansible-vault edit group_vars/pve_lxc/vault.yml
```

Add:

```yaml
pve_api_token_value: "paste-uuid-here"
```

### 3. Deploy

```bash
ansible-playbook playbooks/monitoring.yml
```

Ansible will deploy `pve-exporter.yml` to `/opt/monitoring/` and recreate the stack with the
new `pve-exporter` container.

### 4. Import the Grafana dashboard

1. Grafana → Dashboards → Import → Upload `dashboards/pve-overview.json`
2. Select the Prometheus datasource when prompted

---

## Verify

```bash
# exporter is reachable and returns metrics for pve-01
curl -s 'http://*.*.*.*:9221/pve?target=*.*.*.*' | grep pve_up

# Prometheus sees the pve job as UP
curl -s 'http://*.*.*.*:9090/api/v1/targets' \
  | python3 -m json.tool \
  | grep -A2 '"job": "pve"'
```

Expected: `pve_up{id="node/pve-01"} 1` and health `"up"`.

---

## Key metrics

| Metric | Labels | What it is |
|--------|--------|------------|
| `pve_memory_usage_bytes` | `id` | Memory currently used in bytes |
| `pve_memory_size_bytes` | `id` | Memory allocated (maxmem) in bytes |
| `pve_cpu_usage_ratio` | `id` | CPU usage 0–1. Multiply by 100 for percent |
| `pve_up` | `id` | 1 if guest/node is running, 0 if stopped |
| `pve_guest_info` | `id`, `name`, `status`, `type` | Always 1; carries name and status labels for joins |
| `pve_disk_size_bytes` | `id` | Allocated disk size |

The `id` label format: `lxc/200`, `qemu/100`, `node/pve-01`.

Note: there is no `node` label on metrics and no separate cache metric in this exporter version.

---

## PromQL patterns

Getting guest names onto any metric (join via `pve_guest_info`):

```promql
pve_memory_usage_bytes{id=~"lxc/.*|qemu/.*"}
* on(id) group_left(name) pve_guest_info
```

Memory used as a percentage of allocated per guest:

```promql
pve_memory_usage_bytes{id=~"lxc/.*|qemu/.*"}
/ on(id) pve_memory_size_bytes{id=~"lxc/.*|qemu/.*"}
* 100
```

Host memory used %:

```promql
pve_memory_usage_bytes{id="node/pve-01"}
/ pve_memory_size_bytes{id="node/pve-01"} * 100
```

CPU % per guest with name:

```promql
pve_cpu_usage_ratio{id=~"lxc/.*|qemu/.*"} * 100
* on(id) group_left(name) pve_guest_info
```

---

## Dashboard panels

`dashboards/pve-overview.json` contains six panels:

| Panel | Type | Shows |
|-------|------|-------|
| Guest Memory — RSS % of allocated | bargauge (horizontal) | RSS / alloc per guest, color-coded at 60/85% |
| Host Memory | gauge | Host node used %, same thresholds |
| Guest CPU % | bargauge (horizontal) | `pve_cpu_usage_ratio * 100` per guest |
| Host CPU | gauge | Host node CPU % |
| Memory RSS distribution | pie chart | Share of total RSS per guest |
| Memory absolute — RSS and cache | bargauge | Bytes: RSS + cache bars per guest |

All panels auto-select the Prometheus datasource via the `$datasource` template variable.

---

## Key decisions

| Decision | Value | Reason |
|----------|-------|--------|
| Auth method | API token (not password) | Tokens are revocable and scoped; no user password in vault |
| Token role | `PVEAuditor` | Read-only; exporter needs no write access |
| Privilege Separation | off | Simpler — token inherits the user's PVEAuditor role |
| Exporter placement | `monitoring-01` (alongside Prometheus) | Avoids any inbound scrape connection to pve-01; exporter initiates outbound HTTP to port 8006 |
| Port | `9221` | Default for this exporter |
| Scrape path | `/pve?target=*.*.*.*` | Meta-exporter pattern — one exporter instance can serve multiple PVE nodes |

---

## Rotating the API token

1. Datacenter → API Tokens → Delete the `prometheus@pve!monitoring` token → Add a new one
2. Update vault: `ansible-vault edit group_vars/pve_lxc/vault.yml`
3. Redeploy: `ansible-playbook playbooks/monitoring.yml`
