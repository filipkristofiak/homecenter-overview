# Periscope on monitoring-01

Private LAN-only dashboard at `http://*.*.*.*:8090/`. No container registry or GitHub repository: compile the x86_64 Linux daemon on the Mac, then let the monitoring role copy `dist/` and build the image on monitoring-01.

Periscope itself (daemon, modules, contracts, teachme runbooks) lives in a separate private repository, `lab-deck`; this repo only deploys its build output.

## Build and apply

```sh
cd ~/projects/tools/lab-deck
export PATH="/opt/homebrew/opt/rustup/bin:$HOME/.cargo/bin:$PATH"
scripts/dist.sh
file dist/periscoped # x86-64, statically linked ELF
cd ~/projects/homecenter/ansible
ansible-playbook playbooks/monitoring.yml
```

Changing the monitoring compose file triggers the existing `Restart monitoring stack` handler, which recreates the whole stack. Changing the copied distribution or `periscope.toml` rebuilds and recreates only the periscope service. Every `monitoring.yml` run requires a built dist on the controller; to apply unrelated monitoring changes without it, run `ansible-playbook playbooks/monitoring.yml --skip-tags periscope` (this works only after periscope has been deployed once, because compose still references `./periscope` on the host).

## Verify

```sh
curl -s http://*.*.*.*:8090/api/modules | python3 -m json.tool
periscope --url http://*.*.*.*:8090
```

Open `http://*.*.*.*:8090/` in a browser. The homeautomation contract combines collector metrics from homeautomation-01 (services, Zigbee availability; shown as stale when `periscope-services.prom` is older than 120 seconds) with direct HTTP probes from monitoring-01 to Home Assistant (`*.*.*.*:8123`) and the SLZB-06U (`*.*.*.*`). UDR7 status is inferred from the SLZB-06U.

The `network` and `architecture` modules evaluate contracts derived from the network topology diagram (not published) and `homelab-architecture.drawio`. They use TCP/HTTP probes from monitoring-01 and Prometheus `up`/`pve_up`/`nut_ups_online` series; the architecture contract also reads homeautomation-01 collector metrics for Home Assistant, Mosquitto and Zigbee2MQTT. Boxes without signals (VLAN 28/Guest/IoT VLANs, workstation tools, LAN clients, SATA HDDs) show `not monitored`. When a diagram changes, update its JSON in `~/projects/tools/lab-deck/modules/contracts/`, rerun `scripts/dist.sh`, and reapply `monitoring.yml`.

In the TUI, the sidebar shows only `pve-01 · guests`. Tab focuses the guests table; Space expands a row inline and Enter opens its module full-pane. Each guest except truenas expands to its contract (`nut`, `monitoring`, `k3s`, `jellyfin`, `homeautomation`). The `pve-01 (host)` row expands to the architecture contract and `pve-01 network` expands to the network contract.

The guests table's `Services` column counts healthy services per guest. homeautomation-01 reads its collector (`periscope-services.prom`) and appends `· stale` after 120 seconds while keeping the last reported state. nut-01, monitoring-01, k3s-01 and jellyfin get `--contract NODENAME=PATH`: the module evaluates the components listed under `services` in that contract JSON with the same probes as the expanded contract. truenas has no contract and is passed as `--unmodelled`. The `drift` line under the table warns about any guest that is neither linked nor unmodelled and about links whose guest no longer exists; the homeautomation contract adds a `drift` table comparing collector services with the contract. `CPUs` comes from `pve_cpu_usage_limit`. An older `pve_guests.py` rejects `--contract` and `--unmodelled` and the guests module fails, so rebuild `dist/` before applying.

Each module sets `teachme = "/opt/periscope/modules/teachme/<id>.md"`; `scripts/dist.sh` packages the eight runbooks from lab-deck `modules/teachme/`. periscoped reads and validates every runbook at startup and returns it as the module's `teachme` field in `/api/modules`. In the TUI, select a module (or open a linked one with Enter) and press `t`; Space cycles an exercise through hint, solution and hidden. On the web, the status page links each runbook and `/teachme/<id>` serves it. A missing or invalid runbook stops periscoped from starting, and a periscoped built before teachme support rejects the `teachme` key, so rebuild `dist/` before applying. After editing a runbook, rerun `scripts/dist.sh` and reapply `monitoring.yml`; the changed dist recreates periscope.

Expansion targets set `sidebar = false` in `periscope.toml`; the web page still lists every module. The new contracts use TCP/HTTP probes plus `node_systemd_unit_state`, `up`, `nut_ups_online` and node textfile freshness. Jellyfin's NFS mount and LAN clients, CoreDNS, metrics-server, kubectl and planned k3s workloads show `not monitored`. Rebuild `dist/` before applying: `periscope.toml` rejects unknown keys, so an older periscoped fails to start on `sidebar`.

## Roll back

Remove the `periscope` service from the monitoring compose template, remove its deployment tasks and their `tags: [periscope]`, and rerun `playbooks/monitoring.yml`. The existing stack handler recreates the stack. No registry image needs removal; the `periscope:local` image and copied distribution may be removed from monitoring-01 later by its operator.
