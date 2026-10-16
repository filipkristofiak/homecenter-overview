# Monitoring LXC — pve-01

monitoring-01 runs the Ansible-managed Prometheus/Grafana Compose stack plus pve-exporter, the status-page nginx and periscope.
Prometheus collects guest and host metrics; follow the linked exporter and periscope runbooks for their prerequisites.

See [pve-exporter.md](pve-exporter.md), [pve-status.md](pve-status.md) and [periscope.md](periscope.md).

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
- Grafana → `http://*.*.*.*:3000` (`admin` / vaulted `grafana_admin_password`)
- Prometheus → `http://*.*.*.*:9090`

---

## Key decisions

| Decision | Value | Reason |
|---|---|---|
| Container type | Privileged LXC | Docker daemon requires full cgroup and netns access |
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

- [ ] Debian 12 template available on pve-01: [template prerequisites](pve-01-rebuild.md#3-templates-on-pve-01)
- [ ] lab-deck `dist/` built ([periscope.md](periscope.md))
- [ ] SSH key added to `terraform.tfvars`
- [ ] `community.docker` Ansible collection installed
