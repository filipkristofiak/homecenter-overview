# pve-01 — First deployment guide

Full walkthrough for deploying the core LXC containers from scratch. TrueNAS is already
running at `*.*.*.*` and is assumed reachable from VLAN 27.

**Containers being deployed:**

[REDACTED]

---

## Step 1 — One-time prerequisites

### SSH key

Ensure you have a keypair at `~/.ssh/homelab_id`. This key is injected into all containers
by Terraform and used by Ansible for all subsequent playbook runs.

[REDACTED]

### Ansible collection

```bash
ansible-galaxy collection install community.docker
```

### Proxmox API token

Generate an API token in the Proxmox UI before filling in tfvars.

[REDACTED]

### Terraform variables

```bash
cd terraform/pve-01
cp terraform.tfvars.example terraform.tfvars
```

Fill in `terraform.tfvars`:

[REDACTED]

---

## Step 2 — Download Debian 12 template on pve-01

SSH into pve-01 and run:

```bash
pveam update
pveam download local debian-12-standard_12.12-1_amd64.tar.zst
```

Verify:

```bash
pveam list local | grep debian-12
```

---

## Step 3 — Provision all containers (Terraform)

```bash
cd terraform/pve-01
terraform init
terraform apply
```

Terraform creates all four containers in one apply. Verify they appear in the Proxmox UI
or via `pct list` on pve-01 — all four should be running.

---

## Step 4 — NUT USB passthrough (manual, one-time)

The Terraform provider cannot write raw LXC config entries. SSH into pve-01 and append
the following to `/etc/pve/lxc/200.conf`:

[REDACTED]

Then restart the container:

```bash
pct shutdown 200
pct start 200
# pct reboot 200    # single-command alternative (not available on all setups)
# pct restart 200   # not a pct subcommand
```

Verify the APC UPS is visible inside the container:

[REDACTED]

---

## Step 5 — Configure services (Ansible)

Run from the `ansible/` directory:

```bash
cd ansible
```

### 5a. Node exporter — all containers

Run this first so Prometheus has targets from day one:

```bash
ansible-playbook playbooks/node-exporter.yml
```

### 5b. NUT server

Set real passwords before running — the defaults (`changeme`) are insecure:

```bash
ansible-playbook playbooks/nut-server.yml \
  -e nut_admin_password=<secret> \
  -e nut_monitor_password=<secret>
```

### 5c. Monitoring stack

```bash
ansible-playbook playbooks/monitoring.yml
```

### 5d. Jellyfin Media Server

Requires TrueNAS NFS share to be configured first (see below). Then:

```bash
ansible-playbook playbooks/jellyfin.yml
```

**TrueNAS NFS pre-requisite** — in TrueNAS SCALE (Sharing → NFS → Add):

[REDACTED]

### 5e. Home Assistant

```bash
ansible-playbook playbooks/homeassistant.yml
```

---

## Step 6 — First-run per service

### NUT — verify UPS is detected

[REDACTED]

Expect a list of UPS metrics. If you get `Error: Driver not connected`, check USB
passthrough from Step 4 and run `pct enter 200 && upsdrvctl start`.

### Monitoring — change Grafana password and import dashboard

1. Open `http://*.*.*.*:3000` — log in as [REDACTED]
2. **Change the password when prompted** — do not skip this
3. Import the Node Exporter dashboard:
   - Dashboards → Import → enter ID `1860` → Load
   - Select the Prometheus datasource → Import
4. Verify Prometheus targets are all UP: `http://*.*.*.*:9090/targets`

### Jellyfin — first-run setup wizard

No claim token needed — open `http://*.*.*.*:8096` and:

1. Create the admin account
2. Add Library → Movies / TV Shows
3. Set folder to `/mnt/media` (or subdirectories within it)

### Home Assistant — onboarding wizard

Open `http://*.*.*.*:8123` and complete the onboarding wizard:

- Create admin account
- Set home location
- Add integrations as needed (NUT is reachable at `*.*.*.*:3493`)

---

## Step 7 — Smoke-test everything

```bash
# NUT
upsc [REDACTED] | grep -E "battery|status"

# Prometheus
curl -s http://*.*.*.*:9090/-/healthy

# Grafana
curl -s http://*.*.*.*:3000/api/health

# Prometheus targets (all should be UP)
curl -s 'http://*.*.*.*:9090/api/v1/targets' \
  | python3 -m json.tool | grep '"health"'

# Jellyfin
curl -s -o /dev/null -w "%{http_code}" http://*.*.*.*:8096/health

# Home Assistant
curl -s -o /dev/null -w "%{http_code}" http://*.*.*.*:8123
```

---

## What is NOT automated (follow-up tasks)

| Item | Where to go |
|---|---|
| Grafana alerting rules | Add to `prometheus.yml.j2` under `rule_files`, redeploy monitoring |
| Alertmanager (email/Slack alerts) | Not yet deployed — needs new LXC or addition to monitoring stack |
| HA integrations (Xiaomi, TPlink) | HA onboarding wizard → Settings → Integrations |
| HA NUT integration | Settings → Integrations → search "NUT", point to `*.*.*.*:3493` |
| Jellyfin hardware transcoding | See [jellyfin-lxc.md](jellyfin-lxc.md) — GPU passthrough config on CT 205 |
| Other guest backups | VM 203 is backed up weekly to TrueNAS; other guest disks are not. See [pve-01-backups.md](pve-01-backups.md). |
