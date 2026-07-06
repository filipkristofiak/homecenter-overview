# Home Automation VM — pve-01

## What was done

Provisioned `homeautomation-01` as a full Debian 12 VM (ID 203) on pve-01 via Terraform,
replacing the earlier LXC design. The VM runs on VLAN 39 — an isolated zone —
rather than VLAN 27 to contain blast radius from HA's large attack surface.

Home Assistant runs as a Docker container managed by docker-compose. Fresh install —
no configuration or integrations to carry over.

---

## File layout

```
terraform/pve-01/
  variables.tf              homeautomation_vm_ip, homeautomation_vm_id, debian12_template_id
  main.tf                   proxmox_virtual_environment_vm resource (homeautomation-01, VLAN 39)
  terraform.tfvars          homeautomation_vm_ip / homeautomation_vm_id / debian12_template_id

ansible/
  inventory/hosts.yml       homeautomation-01 in pve_lxc group — *.*.*.*
  playbooks/homeassistant.yml  entry-point playbook
  roles/homeassistant/
    defaults/main.yml       homeassistant_dir (/opt/homeassistant)
    tasks/main.yml          install Docker CE + Compose plugin, deploy compose file, start HA
    handlers/main.yml       apt cache refresh + container recreate on compose change
    files/
      docker-compose.yml    HA stable image, host networking, config volume
```

---

## Deploy order

### 1. Create the Debian 12 cloud-init template on pve-01 (one-time)

```bash
wget -P /var/lib/vz/template/iso/ \
  https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-genericcloud-amd64.qcow2

qm create 9000 --name debian-12-cloudinit --memory 1024 \
  --cores 1 --net0 virtio,bridge=vmbr0 --ostype l26

qm importdisk 9000 \
  /var/lib/vz/template/iso/debian-12-genericcloud-amd64.qcow2 local-lvm

qm set 9000 --scsihw virtio-scsi-pci --scsi0 local-lvm:vm-9000-disk-0 \
  --ide2 local-lvm:cloudinit --boot c --bootdisk scsi0 \
  --agent enabled=1 --serial0 socket --vga serial0

qm template 9000
```

### 2. Provision the VM (Terraform)

```bash
cd terraform/pve-01
terraform init
terraform apply
```

Terraform clones the template into VM 203, injects the SSH key and static IP via cloud-init,
and places the NIC on VLAN 39.

**Post-apply:** pin to E-cores on pve-01:
```bash
qm set 203 --affinity 12-19
```

### 3. Accept SSH host key (one-time)

```bash
ssh -i ~/.ssh/homelab_id ***@*.*.*.*
# type yes, then exit
```

### 4. Install the required Ansible collection (one-time)

```bash
ansible-galaxy collection install community.docker
```

### 5. Configure Home Assistant (Ansible)

```bash
ansible-playbook playbooks/homeassistant.yml
```

Ansible will:
- Install Docker CE and docker-compose-plugin from Docker's official apt repo
- Deploy `/opt/homeassistant/docker-compose.yml`
- Pull `ghcr.io/home-assistant/home-assistant:stable` and start the container

### 6. First-run onboarding

```
http://*.*.*.*:8123
```

Create admin account, set home location, add integrations.

### 7. Verify

```bash
curl -s -o /dev/null -w "%{http_code}" http://*.*.*.*:8123
# expect 200 or 302
```

---

## Key decisions

| Decision | Value | Reason |
|---|---|---|
| VM type | Full VM (not LXC) | Docker in a VM has direct kernel access; no privileged container hacks needed |
| VLAN | 39 — isolated | HA runs third-party code + cloud integrations; keeps Proxmox/TrueNAS out of blast radius |
| VM ID | `203` | Sequential after monitoring-01 (202) |
| Hostname | `homeautomation-01` | Reflects full stack (HA + Mosquitto + Z2M), not just HA |
| IP | `*.*.*.*/24` | VLAN 39 static; gateway `*.*.*.1` |
| OS | Debian 12 cloud image | Cloud-init for SSH key + network injection; consistent with IaC approach |
| CPU | 2 cores | HA automations and integrations can spike on startup |
| RAM | 2048 MB | Full stack: HA + Mosquitto + Zigbee2MQTT + recorder DB |
| Disk | 32 GB virtio | OS + Docker images + HA config + SQLite recorder database |
| Network mode | `host` | HA requires host networking for mDNS, SSDP, and local device discovery |
| HA Docker privilege | none | Not needed — full VM, no USB passthrough, Zigbee is TCP-based (SLZB-06M) |
| HA image | `ghcr.io/home-assistant/home-assistant:stable` | Official HA container image |
| Config persistence | `./config:/config` volume | HA config, secrets, and database survive restarts and upgrades |
| QEMU agent | disabled until Ansible runs | Agent not in cloud image; re-enable after `qemu-guest-agent` is installed |

---

## Upgrading Home Assistant

Re-run the playbook — `pull: always` pulls the latest `stable` image and recreates the container:

```bash
ansible-playbook ansible/playbooks/homeassistant.yml
```

Or manually on the VM:

```bash
docker compose -f /opt/homeassistant/docker-compose.yml pull
docker compose -f /opt/homeassistant/docker-compose.yml up -d
```

---

## Pre-flight checklist (fresh deploy)

- [ ] Debian 12 cloud-init template exists on pve-01: `qm list | grep template`
- [ ] VM ID `203` is free: `qm list`
- [ ] IP `*.*.*.*` is not in use: `ping -c1 *.*.*.*`
- [ ] VLAN 39 exists in UniFi controller
- [ ] SSH key set in `terraform.tfvars`
- [ ] `community.docker` Ansible collection installed
