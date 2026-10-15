# Homeautomation service health for periscope

Applying changes the HA compose file and recreates `homeassistant`, `mosquitto`, and `zigbee2mqtt`. The MQTT broker password file is regenerated with a third, collector-only account and Mosquitto restarts; expect a brief MQTT reconnect for HA and Z2M. The collector writes `periscope-services.prom` atomically to the existing node_exporter textfile directory every 30 seconds, using container health/inspect, HTTP to the SLZB-06U coordinator, and authenticated MQTT retained messages. Its password is stored root-only on the VM.

## Apply

```sh
cd ansible
ansible-playbook playbooks/homeassistant.yml
```

## Zigbee2MQTT availability

If Zigbee2MQTT's own `configuration.yaml` has availability disabled, the playbook enables it by publishing `{"options":{"availability":{"enabled":true}}}` to `zigbee2mqtt/bridge/request/options` (via `mosquitto_rr` in the mosquitto container) and restarts Zigbee2MQTT once. While availability is off, every collector run waits the full 12 seconds and the plug displays "availability off".

## Verify

```sh
docker ps --format '{{.Names}} {{.Status}}' # the three HA containers show (healthy)
curl -s http://*.*.*.*:9100/metrics | grep '^periscope_'
curl -s http://*.*.*.*:9100/metrics | grep ^periscope_zigbee_
curl -s http://*.*.*.*:8090/api/modules | python3 -m json.tool
```

The `homeautomation` contract shows container status and Zigbee availability when collector data is fresh; until the textfile appears (or when it is older than 120 seconds), these signals show `stale`. Direct HTTP probes still report Home Assistant and SLZB-06U independently. Inspect `systemctl status periscope-collector.timer` and `journalctl -u periscope-collector.service` on the VM if collection fails.
