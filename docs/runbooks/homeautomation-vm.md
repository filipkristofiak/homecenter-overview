# Home Automation VM — pve-01

Home Assistant, Mosquitto and Zigbee2MQTT run as an Ansible-managed Compose stack in a Debian VM.
Persistent state lives under `/opt/homeassistant`; deploy, connect MQTT, pair devices and upgrade with the procedures below.

---

## Deploy order

Prerequisite: [Debian 12 cloud-init template on pve-01](pve-01-rebuild.md#3-templates-on-pve-01).

### 1. Provision the VM (Terraform)

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

### 2. Accept SSH host key (one-time)

```bash
ssh -i ~/.ssh/homelab_id ***@*.*.*.*
# type yes, then exit
```

### 3. Install the required Ansible collection (one-time)

```bash
ansible-galaxy collection install community.docker
```

### 4. Deploy the home automation stack (Ansible)

From `ansible/`:

```bash
ansible-playbook playbooks/homeassistant.yml -l homeautomation-01
```

The role deploys Mosquitto (`127.0.0.1:1883`), Zigbee2MQTT (frontend on
`127.0.0.1:8080`), and Home Assistant (`*.*.*.*:8123`). Both MQTT
accounts and the mesh key come from encrypted host variables. Z2M talks to the
SLZB-06U at `*.*.*.*:6638` with the `zstack` adapter.

### 5. Connect Home Assistant to MQTT (once, in its UI)

Open `http://*.*.*.*:8123` from an internal VLAN. Go to **Settings →
Devices & services → Add integration → MQTT**, enter broker `localhost`, port
`1883`, user `homeassistant`. Retrieve its password with
`ssh -i ~/.ssh/homelab_id ***@*.*.*.* 'cat /opt/homeassistant/mosquitto/ha-mqtt-password'`
and paste it into the UI. HA stores this integration in its persistent config
volume. Do **not** add ZHA: only Zigbee2MQTT owns the coordinator.

### 6. Pair a plug

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

### 7. Verify

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
- [ ] VLAN 39 exists in UniFi controller
- [ ] SSH key set in `terraform.tfvars`
- [ ] `community.docker` Ansible collection installed
