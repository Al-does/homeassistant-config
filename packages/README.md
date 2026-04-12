# Packages Directory

Home Assistant's [packages](https://www.home-assistant.io/docs/configuration/packages/) pattern lets you organize configuration by feature or domain instead of by integration type. Each YAML file in this directory is automatically loaded by HA.

## How It Works

In `configuration.yaml`, we have:

```yaml
homeassistant:
  packages: !include_dir_named packages/
```

This tells HA to load every `.yaml` file in this directory as a named package. The filename (minus `.yaml`) becomes the package name.

## Adding a New Package

1. Create a new `.yaml` file in this directory (e.g., `climate.yaml`).
2. Add any HA configuration domains you need inside it.
3. Commit and push — the Git Pull add-on will sync it to HA.
4. Restart HA or reload the relevant domain.

## Naming Conventions

Name files by feature or area:

- `lights.yaml` — lighting automations, groups, scenes
- `security.yaml` — alarm, door sensors, cameras
- `climate.yaml` — thermostat, temperature sensors, HVAC automations
- `presence.yaml` — person tracking, zone-based automations
- `notifications.yaml` — notification automations and scripts

## Example Package

A package file can contain any combination of HA domains:

```yaml
# packages/kitchen.yaml

sensor:
  - platform: template
    sensors:
      kitchen_occupancy_status:
        friendly_name: "Kitchen Occupancy"
        value_template: >
          {{ "occupied" if is_state("binary_sensor.kitchen_motion", "on") else "empty" }}

automation:
  - id: kitchen_lights_on_motion
    alias: "Kitchen - Lights on with motion"
    trigger:
      - platform: state
        entity_id: binary_sensor.kitchen_motion
        to: "on"
    action:
      - service: light.turn_on
        target:
          entity_id: light.kitchen_ceiling

  - id: kitchen_lights_off_no_motion
    alias: "Kitchen - Lights off after no motion"
    trigger:
      - platform: state
        entity_id: binary_sensor.kitchen_motion
        to: "off"
        for: "00:05:00"
    action:
      - service: light.turn_off
        target:
          entity_id: light.kitchen_ceiling
```
