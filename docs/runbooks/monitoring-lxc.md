# Monitoring LXC — pve-01

## What was done

Added Terraform and Ansible to provision and configure a monitoring stack as a privileged
LXC container on pve-01. The container runs Grafana and Prometheus as Docker containers
managed by docker-compose. Prometheus scrapes metrics; Grafana provides dashboards.

No infrastructure was changed yet — these are ready to apply.

---

## File layout

```
terraform/pve-01/
  variables.tf              added monitoring_lxc_ip, monitoring_lxc_id
  main.tf                   LXC container resource (monitoring-01, VLAN 27)
  terraform.tfvars.example  monitoring_lxc_ip / monitoring_lxc_id example values

ansible/
  inventory/hosts.yml       monitoring-01 added to pve_lxc group
  playbooks/monitoring.yml  entry-point playbook
  roles/monitoring/
    defaults/main.yml       tunable vars: monitoring_dir, ports, retention
    tasks/main.yml          install Docker CE + Compose plugin, deploy configs, start stack
    handlers/main.yml       apt cache refresh + stack recreate on config change
    templates/
      docker-compose.yml.j2  Prometheus (9090) + Grafana (3000), named volumes
      prometheus.yml.j2      scrape config (add targets here as services grow)
```

---

## Deploy order

### 1. Provision the container (Terraform)

```bash
cd terraform/pve-01
cp terraform.tfvars.example terraform.tfvars   # fill in real values
terraform init
terraform apply
```

### 2. Install the required Ansible collection (one-time)

```bash
ansible-galaxy collection install community.docker
```

### 3. Configure the monitoring stack (Ansible)

```bash
cd ansible
ansible-playbook playbooks/monitoring.yml
```

Ansible will:
- Install Docker CE and docker-compose-plugin from Docker's official apt repo
- Deploy `/opt/monitoring/docker-compose.yml` and `/opt/monitoring/prometheus.yml`
- Start the stack with `docker compose up -d`

### 4. Verify

```bash
# from any host on VLAN 27
curl -s http://*.*.*.*:9090/-/healthy   # Prometheus
curl -s http://*.*.*.*:3000/api/health  # Grafana
```

Or open in a browser:
- Grafana → `http://*.*.*.*:3000` (default credentials: `admin` / `admin`)
- Prometheus → `http://*.*.*.*:9090`

**Change the Grafana admin password on first login.**

---

## Key decisions

| Decision | Value | Reason |
|---|---|---|
| Container type | Privileged LXC | Docker daemon requires full cgroup and netns access |
| CT ID | `201` | Before plex-01 (202); change in `terraform.tfvars` if taken |
| Hostname | `monitoring-01` | Follows `<service>-XX` naming convention |
| IP | `*.*.*.*/24` | VLAN 27, static; next free after nut-01 (.10) |
| Gateway | `*.*.*.1` | VLAN 27 gateway |
| OS template | Debian 12 standard | Consistent with rest of homelab LXC containers |
| CPU | 2 cores | Prometheus TSDB compaction and scrape ingestion can spike |
| RAM | 1024 MB | Prometheus + Grafana + OS headroom; increase for many targets |
| Disk | 20 GB | Prometheus data retention (default 30d); increase for longer retention |
| Retention | 30 days | Controlled via `prometheus_retention` in `defaults/main.yml` |
| Compose management | `community.docker.docker_compose_v2` | Native Ansible module; avoids shelling out to `docker compose` |

---

## Adding scrape targets

Node exporter is already deployed on all `pve_lxc` containers and scraped automatically.
See [node-exporter.md](node-exporter.md) for details and for how to add new containers.

For other exporters, add a new job under `scrape_configs` in
`ansible/roles/monitoring/templates/prometheus.yml.j2`, then re-run the monitoring playbook:

```bash
ansible-playbook ansible/playbooks/monitoring.yml
```

Prometheus also supports live config reload without restart:

```bash
curl -X POST http://*.*.*.*:9090/-/reload
```

---

## Pre-flight checklist

- [ ] Debian 12 template downloaded on pve-01: `pveam update && pveam download local debian-12-standard_12.7-1_amd64.tar.zst`
- [ ] CT ID `202` is free on pve-01: `pct list`
- [ ] IP `*.*.*.*` is not in use: `ping -c1 *.*.*.*`
- [ ] SSH key added to `terraform.tfvars`
- [ ] `community.docker` Ansible collection installed
