#!/usr/bin/env python3
"""
UniFi configuration snapshot tool.
Fetches legacy REST API endpoints and saves them as JSON files.
Run periodically and commit to git — use `git diff` to track changes.

Usage:
    python scripts/unifi/fetch_config.py

Requirements:
    pip install requests python-dotenv

.env keys:
    UNIFI_HOST           e.g. https://192.168.1.1  (no trailing slash)
    UNIFI_API_KEY        generated at Network > Settings > Control Plane > Integrations
    UNIFI_SITE           site short name, usually "default"
    UNIFI_OUTPUT_DIR     path to output directory, default: configs/unifi
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
    from dotenv import load_dotenv
except ImportError:
    print("Missing dependencies. Run: pip install requests python-dotenv")
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────

load_dotenv()

HOST        = os.getenv("UNIFI_HOST", "https://*.*.*.*").rstrip("/")
API_KEY     = os.getenv("UNIFI_API_KEY", "")
SITE        = os.getenv("UNIFI_SITE", "default")
OUTPUT_DIR  = Path(os.getenv("UNIFI_OUTPUT_DIR", "configs/unifi"))

if not API_KEY:
    print("Error: UNIFI_API_KEY not set in .env")
    sys.exit(1)

# ── Endpoints ─────────────────────────────────────────────────────────────────

LEGACY = f"/proxy/network/api/s/{SITE}"
INT_V1 = "/proxy/network/integration/v1"

LEGACY_ENDPOINTS = {
    "device":      f"{LEGACY}/stat/device",
    "networkconf": f"{LEGACY}/rest/networkconf",
    "portconf":    f"{LEGACY}/rest/portconf",
    "setting":     f"{LEGACY}/rest/setting",
    "wlanconf":    f"{LEGACY}/rest/wlanconf",
    "dhcp_reservations":  f"{LEGACY}/rest/user",
}

def zbf_endpoints(site_uuid: str) -> dict:
    """ZBF endpoints require the site UUID, discovered at runtime."""
    base = f"{INT_V1}/sites/{site_uuid}"
    return {
        "firewall_zones":    f"{base}/firewall/zones",
        "firewall_policies": f"{base}/firewall/policies",
    }


# ── Masking ───────────────────────────────────────────────────────────────────

def mask_value(field: str) -> str:
    """
    Masked value for a secret field - everything gets
    a generic redaction marker that includes the field name,
    making it easy to identify what was redacted in a diff.
    """
    return f"<REDACTED:{field}>"
 
 
def mask_secrets(obj: object) -> object:
    """
    Recursively walk the JSON structure and redact all x_-prefixed fields.
    Works on dicts, lists, and primitives at any nesting depth.
    """
    if isinstance(obj, dict):
        return {
            k: mask_value(k) if (k.startswith("x_") and isinstance(v, str) and v)
            else mask_secrets(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [mask_secrets(item) for item in obj]
    return obj

# ── Fetch ─────────────────────────────────────────────────────────────────────

def fetch(session: requests.Session, path: str) -> dict:
    url = f"{HOST}{path}"
    response = session.get(url, timeout=15)
    response.raise_for_status()
    return response.json()

def discover_site_uuid(session: requests.Session) -> str | None:
    """Fetch site UUID from Integration API for ZBF endpoints."""
    try:
        data = fetch(session, f"{INT_V1}/sites")
        sites = data.get("data", [])
        for site in sites:
            if site.get("internalReference") == SITE:
                return site["id"]
        # fallback: return first site if short name doesn't match
        if sites:
            return sites[0]["id"]
    except Exception as e:
        print(f"  !  Could not discover site UUID: {e}")
    return None


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
 
def filter_dhcp_reservations(data: dict) -> dict:
    """Keep only clients with a fixed IP reservation."""
    filtered = [
        entry for entry in data.get("data", [])
        if entry.get("use_fixedip") is True
    ]
    return {**data, "data": filtered}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def save(data: dict, name: str, out_path: Path) -> tuple[bool, str]:
    try:
        masked = mask_secrets(data)
        with open(out_path, "w") as f:
            json.dump(masked, f, indent=2, sort_keys=True)
            f.write("\n")
        count = len(data.get("data", []))
        return True, f"({count} items)"
    except Exception as e:
        return False, str(e)
 

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({
        "X-API-KEY": API_KEY,
        "Accept": "application/json",
    })
    session.verify = False  # UDR7 uses self-signed cert on LAN

    # suppress the SSL warning — expected on local gateway
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    print(f"Host:   {HOST}")
    print(f"Site:   {SITE}")
    print(f"Output: {OUTPUT_DIR}/")
    print()

    # discover site UUID for ZBF endpoints
    site_uuid = discover_site_uuid(session)
    if site_uuid:
        print(f"  Site UUID: {site_uuid}")
        all_endpoints = {**LEGACY_ENDPOINTS, **zbf_endpoints(site_uuid)}
    else:
        print("  ! Skipping ZBF endpoints (could not get site UUID)")
        all_endpoints = LEGACY_ENDPOINTS
    print()

    success = 0
    errors = []

    for name, path in all_endpoints.items():
        try:
            data = fetch(session, path)
            if name == "dhcp_reservations":
                data = filter_dhcp_reservations(data)
            out_path = OUTPUT_DIR / f"unifi.{name}.json"
            ok, note = save(data, name, out_path)
            if ok:
                print(f"  OK  {name:<20} -> {out_path}  {note}")
                success += 1
            else:
                raise Exception(note)
        except requests.HTTPError as e:
            msg = f"HTTP {e.response.status_code}"
            print(f"  !!  {name:<20} -> {msg}")
            errors.append((name, msg))
        except Exception as e:
            print(f"  !!  {name:<20} -> {e}")
            errors.append((name, str(e)))
 
    # metadata
    meta = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "host": HOST,
        "site": SITE,
        "site_uuid": site_uuid,
        "endpoints": list(all_endpoints.keys()),
        "errors": [{"endpoint": n, "error": e} for n, e in errors],
    }
    with open(OUTPUT_DIR / "unifi.meta.json", "w") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")
 
    print()
    print(f"Done: {success}/{len(all_endpoints)} endpoints saved to {OUTPUT_DIR}/")
 
    if errors:
        print(f"Errors: {[e[0] for e in errors]}")
        sys.exit(1)
 
 
if __name__ == "__main__":
    main()