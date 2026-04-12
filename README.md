# Home Assistant Configuration

Git-managed Home Assistant configuration with MCP integration for coding agent access.

## Quick Start

1. **Clone this repo** and set up the Git Pull add-on to sync it to your HA instance (see [Git Pull Setup](docs/git-pull-setup.md)).
2. **Copy secrets**: `cp secrets.yaml.example secrets.yaml` and fill in your real values.
3. **Set up MCP** for coding agent integration (see [MCP Setup](docs/mcp-setup.md)).

## How This Works

Configuration is organized using HA's [packages pattern](https://www.home-assistant.io/docs/configuration/packages/). Instead of one monolithic `configuration.yaml`, each feature or domain gets its own file in `packages/`.

```
homeassistant-config/
├── configuration.yaml          # Main config — mostly includes
├── secrets.yaml.example        # Template for secrets (committed)
├── secrets.yaml                # Real secrets (gitignored, NEVER committed)
├── automations.yaml            # UI-created automations
├── scripts.yaml                # UI-created scripts
├── scenes.yaml                 # UI-created scenes
├── packages/                   # Modular config by domain/feature
├── custom_components/          # HACS integrations
├── blueprints/automation/      # Automation blueprints
├── www/                        # Custom frontend resources
├── docs/                       # Setup guides
├── CLAUDE.md                   # Project context for Claude Code
└── .github/workflows/          # CI validation
```

## Adding New Configuration

1. Create a YAML file in `packages/` (e.g., `packages/lights.yaml`).
2. Add any HA domains you need (automations, sensors, scripts, etc.).
3. Commit and push to `main`.
4. The Git Pull add-on syncs the changes to HA.
5. Restart HA or reload the relevant domain.

See [packages/README.md](packages/README.md) for details and examples.

## Secrets

All sensitive values (tokens, passwords, coordinates) go in `secrets.yaml`, referenced in config with `!secret key_name`. This file is gitignored — never commit it.

## Validation

A GitHub Actions workflow runs `yamllint` on every push and PR to catch YAML syntax errors before they reach your HA instance.

## Setup Guides

- [Git Pull Add-on Setup](docs/git-pull-setup.md) — Sync this repo to your HA instance
- [MCP Setup](docs/mcp-setup.md) — Connect Claude Code to HA via ha-mcp

## Safety

- Always create a backup/snapshot before major changes.
- Test config via **Developer Tools > Check Configuration** before restarting.
- Prefer incremental changes over large rewrites.
- Never modify `.storage/` files directly.
