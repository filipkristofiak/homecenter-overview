# UniFi Config Snapshots

Fetches UniFi configuration via the REST API and saves as JSON files.
Commit the output to git and use `git diff` to track changes over time.

## Setup

```bash
cd network/
/opt/homebrew/bin/python3 -m venv .venv
source .venv/bin/activate
python --version   # should show 3.14.*
pip install requests python-dotenv
deactivate
cd ..
```

Add to your `.env`:

```env
UNIFI_HOST=https://192.168.1.1
UNIFI_API_KEY=your-key-here
UNIFI_SITE=default
UNIFI_OUTPUT_DIR=configs/unifi   # optional, this is the default
```

### Generating the API key

Navigate to:
**Network App → Settings → Control Plane → Integrations → Create New API Key**

> On some UniFi OS 5.x builds the Integrations nav link is missing from the sidebar.
> Navigate manually: `https://<router-ip>/network/settings/control-plane/integrations`

## Usage

```bash
cd network/
source .venv/bin/activate
cd ..
python network/unifi/fetch_config.py
```

## Output files

| File | Contents |
|---|---|
| `unifi.device.json` | Adopted devices (APs, switches) |
| `unifi.networkconf.json` | Networks / VLANs |
| `unifi.portconf.json` | Switch port profiles |
| `unifi.setting.json` | Site-wide settings |
| `unifi.wlanconf.json` | SSIDs and WiFi config |
| `unifi.firewall_zones.json` | Zone-based firewall zones |
| `unifi.firewall_policies.json` | Zone-based firewall policies |
| `unifi.meta.json` | Fetch timestamp, site UUID, error summary |

## Secret masking

All `x_`-prefixed fields are redacted before writing to disk -- this covers
passphrases, PSKs, WEP keys, RADIUS secrets, SNMP community strings,
IPsec PSKs, WireGuard private keys, and SSH credentials.
```json
"x_passphrase": "REDACTED:x_passphrase",
"x_ipsec_secret": "<REDACTED:x_ipsec_secret>",
"x_wireguard_private_key": "<REDACTED:x_wireguard_private_key>"
```

Masking is recursive -- works at any nesting depth across all endpoints.

## Git workflow

```bash
python scripts/unifi/fetch_config.py
git diff configs/unifi/
git add configs/unifi/
git commit -m "chore: unifi config snapshot $(date +%Y-%m-%d)"
```

## Notes

- SSL verification is disabled -- expected on LAN with a self-signed cert.
- The script auto-discovers the site UUID at runtime for ZBF endpoints.
  If discovery fails it falls back to legacy endpoints only.
- ZBF endpoints use the Integration API (`/proxy/network/integration/v1/`)
  and require the locally generated API key, not a Site Manager key from unifi.ui.com.