# Home Automation VM — pve-01

## What was done

Provisioned `homeautomation-01` as a full Debian 12 VM (ID 203) on pve-01 via Terraform,
replacing the earlier LXC design. The VM runs on VLAN 39 — an isolated zone —
rather than VLAN 27 to contain blast radius from HA's large attack surface.

Home Assistant, Mosquitto and Zigbee2MQTT run as Docker containers managed by
Ansible and Docker Compose. HA's existing `/opt/homeassistant/config` persists
across the stack expansion; no HA reset or new owner account is required.

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
    defaults/main.yml       pinned image tags, Zigbee channel and coordinator address
    tasks/main.yml          deploy broker accounts, Z2M config and Compose stack
    templates/             Compose, mosquitto.conf, Zigbee2MQTT configuration
  inventory/host_vars/homeautomation-01.yml  vaulted MQTT passwords and Zigbee key
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

### 5. Deploy the home automation stack (Ansible)

From `ansible/`:

```bash
ansible-playbook playbooks/homeassistant.yml -l homeautomation-01
```

The role deploys Mosquitto (`127.0.0.1:1883`), Zigbee2MQTT (frontend on
`127.0.0.1:8080`), and Home Assistant (`*.*.*.*:8123`). Both MQTT
accounts and the mesh key come from encrypted host variables. Z2M talks to the
SLZB-06U at `*.*.*.*:6638` with the `zstack` adapter.

### 6. Connect Home Assistant to MQTT (once, in its UI)

Open `http://*.*.*.*:8123` from an internal VLAN. Go to **Settings →
Devices & services → Add integration → MQTT**, enter broker `localhost`, port
`1883`, user `homeassistant`. Retrieve its password with
`ssh -i ~/.ssh/homelab_id ***@*.*.*.* 'cat /opt/homeassistant/mosquitto/ha-mqtt-password'`
and paste it into the UI. HA stores this integration in its persistent config
volume. Do **not** add ZHA: only Zigbee2MQTT owns the coordinator.

### 7. Pair a plug

Use an SSH tunnel from your workstation (keep it open during pairing):

```bash
ssh -i ~/.ssh/homelab_id -L 8080:127.0.0.1:8080 ***@*.*.*.*
```

Open `http://127.0.0.1:8080` and select **Permit join (All)**. Factory-reset
the plug using the manufacturer's instructions, wait for the successful
interview, give it a name, then close permit-join. The plug will appear via
MQTT discovery in HA; test switching it there. Pair mains-powered plugs
before battery-powered radiator heads so the plugs can extend the Zigbee
mesh. Neither MQTT nor the Z2M frontend needs a UniFi inbound rule: their
host ports bind to VM loopback.

### 8. Verify

```bash
ssh -i ~/.ssh/homelab_id ***@*.*.*.* \
  'cd /opt/homeassistant && docker compose ps && docker compose logs --tail=40 zigbee2mqtt'
curl -s -o /dev/null -w '%{http_code}\n' http://*.*.*.*:8123/
# Expect three running services, Z2M started and connected to the coordinator, HA HTTP 200.
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
| HA Docker privilege | none | Not needed — full VM, no USB passthrough, Zigbee is TCP-based (SLZB-06U on VLAN 39) |
| HA image | Pinned in `ansible/roles/homeassistant/defaults/main.yml` | Upgrade deliberately; do not track `stable` |
| Config persistence | `./config:/config` volume | HA config, secrets, and database survive restarts and upgrades |
| QEMU agent | disabled until Ansible runs | Agent not in cloud image; re-enable after `qemu-guest-agent` is installed |

---

## Upgrading Home Assistant

Bump `homeassistant_image_tag` in `ansible/roles/homeassistant/defaults/main.yml`,
then re-run the playbook from `ansible/`. The role pulls the pinned tag and
recreates the container when the Compose template changes:

```bash
ansible-playbook playbooks/homeassistant.yml
```

---

## Pre-flight checklist (fresh deploy)

- [ ] Debian 12 cloud-init template exists on pve-01: `qm list | grep template`
- [ ] VM ID `203` is free: `qm list`
- [ ] IP `*.*.*.*` is not in use: `ping -c1 *.*.*.*`
- [ ] VLAN 39 exists in UniFi controller
- [ ] SSH key set in `terraform.tfvars`
- [ ] `community.docker` Ansible collection installed
