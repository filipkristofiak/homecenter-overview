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

When a homecenter diagram changes, update its contract JSON in `~/projects/tools/lab-deck/modules/contracts/`, rerun `scripts/dist.sh`, and reapply `monitoring.yml`. After editing a lab-deck teachme runbook, also rebuild `dist/` and reapply `monitoring.yml`.

## Verify

```sh
curl -s http://*.*.*.*:8090/api/modules | python3 -m json.tool
periscope --url http://*.*.*.*:8090
```

Open `http://*.*.*.*:8090/` in a browser.

Using the dashboard: lab-deck `README.md`.

## Roll back

Remove the `periscope` service from the monitoring compose template, remove its deployment tasks and their `tags: [periscope]`, and rerun `playbooks/monitoring.yml`. The existing stack handler recreates the stack. No registry image needs removal; the `periscope:local` image and copied distribution may be removed from monitoring-01 later by its operator.
