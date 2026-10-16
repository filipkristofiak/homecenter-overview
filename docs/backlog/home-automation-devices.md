# Home automation devices and automations

## Zigbee Devices (planned)

| Category | Purpose | Protocol |
|---|---|---|
| Smart plugs with power monitoring | Main PC workstation, homelab server, TV hub, Rancilio espresso machine | Zigbee |
| Radiator TRVs | Per-room radiator thermostat control | Zigbee |
| mmWave presence sensors | Motion/presence detection for night lighting | Zigbee |
| RGBW LED (red, floor level) | Night lighting triggered by presence | Zigbee |

**Smart plug notes:** Verify max current rating per plug (most are 16A/3680W — sufficient for all listed devices). The homelab server plug should be monitored-only, not switched.

**TRV notes:** Standard M30×1.5 thread fits most European radiator valves; adapters available for others.

**Presence sensor notes:** mmWave (e.g. Aqara FP2 or Tuya mmWave modules) preferred over PIR — detects stationary presence, not only movement.


## Planned Automations

| Automation | Trigger | Action |
|---|---|---|
| Night lighting | Presence detected, time between ~23:00–07:00 | Turn on floor-level red LED at low brightness |
| Night light off | No presence detected | Turn off red LED after short delay |
| Radiator schedule | Time-based / presence-based | Adjust TRV setpoints per room |
| Power alerts | Plug reports wattage above threshold | Mobile notification |
| Energy dashboard | Continuous | Track kWh and cost per device in HA Energy panel |


A SONOFF plug is already paired (see the components diagram in the [design](../home_automation/home-automation.md#components-and-message-flow)).
