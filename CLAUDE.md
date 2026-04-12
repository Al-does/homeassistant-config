# Home Assistant Configuration Repository

This is a Home Assistant configuration repository managed via Git. Changes are synced to HA using the Git Pull add-on.

## File Structure

- `configuration.yaml` — Main config, mostly includes. Rarely needs editing.
- `packages/` — **Primary config directory.** Add new YAML files here for new features/domains.
- `automations.yaml` — UI-created automations (managed by HA's UI editor).
- `scripts.yaml`, `scenes.yaml` — Same as above, managed by HA UI.
- `secrets.yaml` — All sensitive values. NEVER committed. Uses `secrets.yaml.example` as template.
- `custom_components/` — HACS and manual custom integrations.
- `blueprints/` — Automation and script blueprints.
- `docs/` — Setup guides for MCP, Git Pull, etc.

## Key Conventions

- **New configuration goes in `packages/`** as individual YAML files (one per feature/domain).
- **Secrets** use `!secret key_name` syntax. Define values in `secrets.yaml`.
- **Never commit `secrets.yaml`** — it's gitignored.
- **Always validate YAML** before committing (CI runs yamllint automatically).
- **Entity naming**: use `domain.descriptive_name` format (e.g., `light.kitchen_ceiling`, `sensor.front_door_temperature`).
- **Automation IDs**: use `area_function` format (e.g., `kitchen_lights_on_motion`).

## Common Tasks

### Add a new automation

Create or edit a package file in `packages/`:

```yaml
# packages/kitchen.yaml
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
```

### Add a new sensor

```yaml
# packages/monitoring.yaml
sensor:
  - platform: template
    sensors:
      average_indoor_temp:
        friendly_name: "Average Indoor Temperature"
        unit_of_measurement: "°F"
        value_template: >
          {{ states.sensor | selectattr('entity_id', 'search', 'temperature')
             | map(attribute='state') | map('float', 0) | list | average }}
```

### Create a new package

1. Create a new `.yaml` file in `packages/` named for the feature (e.g., `security.yaml`).
2. Add any HA domains you need (automation, sensor, binary_sensor, input_boolean, script, etc.).
3. Commit and push. The Git Pull add-on syncs it to HA.
4. Restart HA or reload the relevant domain.

## HA-Specific YAML Notes

Valid YAML tags (these are NOT standard YAML — they're HA extensions):
- `!include filename.yaml`
- `!include_dir_named directory/`
- `!include_dir_list directory/`
- `!include_dir_merge_named directory/`
- `!include_dir_merge_list directory/`
- `!secret key_name`
- `!env_var VAR_NAME`

## Safety Rules

- **Backup first**: Always create a snapshot/backup before major changes.
- **Test config**: Use Developer Tools > Check Configuration, or `hass --script check_config`.
- **Incremental changes**: Prefer small, focused changes over large rewrites.
- **Never modify `.storage/`**: These are internal HA files managed by the system.
- **Restart vs. reload**: Many domains (automations, scripts, scenes, groups) can be reloaded without a full restart. Only restart when necessary.
