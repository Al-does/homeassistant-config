# ha-mcp Setup Guide

[ha-mcp](https://github.com/homeassistant-ai/ha-mcp) lets coding agents interact with your Home Assistant instance through MCP (Model Context Protocol).

## Prerequisites

- A running Home Assistant instance accessible on your network
- [uv](https://docs.astral.sh/uv/) installed (`uvx` runs the MCP server)
- A long-lived access token from HA

## Step 1: Create a Long-Lived Access Token

1. Open your HA instance in a browser.
2. Click your profile icon (bottom-left).
3. Go to **Security** tab.
4. Scroll to **Long-Lived Access Tokens**.
5. Click **Create Token**.
6. Name it something descriptive (e.g., "Cursor MCP").
7. Copy the token immediately — it won't be shown again.
8. Store it in `homeassistant-config/.env.mcp` as `HOMEASSISTANT_TOKEN`.

## Step 2: Configure Credentials

Copy the example and fill in your token:

```bash
cp homeassistant-config/.env.mcp.example homeassistant-config/.env.mcp
```

Example `.env.mcp` (gitignored):

```bash
HOMEASSISTANT_URL=http://homeassistant.local:8123
HOMEASSISTANT_TOKEN=your-long-lived-access-token-here
HAMCP_ENABLE_FILESYSTEM_TOOLS=true
ENABLE_YAML_CONFIG_EDITING=true
```

## Step 3: Enable MCP in Cursor

This workspace includes `.cursor/mcp.json` at the repo root. It runs the official Python `ha-mcp` package via `uvx`.

> **Important:** Define `ha-mcp` in **either** the project `.cursor/mcp.json` **or** `~/.cursor/mcp.json`, not both. Cursor will show duplicate servers if the same name appears in both places.

After creating or updating credentials:

1. Open **Cursor Settings → MCP** (or restart Cursor).
2. Confirm **ha-mcp** shows a green/connected status.
3. Ask the agent to list entities or check a device state.

### Manual Cursor config

```json
{
  "mcpServers": {
    "ha-mcp": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "ha-mcp", "ha-mcp"],
      "env": {
        "HOMEASSISTANT_URL": "http://homeassistant.local:8123",
        "HOMEASSISTANT_TOKEN": "your-long-lived-access-token-here",
        "HAMCP_ENABLE_FILESYSTEM_TOOLS": "true",
        "ENABLE_YAML_CONFIG_EDITING": "true"
      }
    }
  }
}
```

## Step 4: Install ha_mcp_tools (custom component)

The MCP server can query and control entities out of the box. File and YAML editing tools require the `ha_mcp_tools` custom component on your HA instance.

This repo includes the component at `custom_components/ha_mcp_tools/`.

### Deploy to Home Assistant

1. Commit and push the changes to `main`.
2. Let the Git Pull add-on sync (or pull manually).
3. **Restart Home Assistant**.
4. Go to **Settings → Devices & Services → Add Integration**.
5. Search for **HA MCP Tools** and complete the setup (no config required).

### Tools unlocked by the component

| Tool | Description |
|------|-------------|
| `ha_config_set_yaml` | Add/replace/remove top-level YAML keys with backup and validation |
| `ha_list_files` | List files in allowed directories |
| `ha_read_file` | Read config YAML, logs, www/, themes/, etc. |
| `ha_write_file` | Write files to allowed directories |
| `ha_delete_file` | Delete files from allowed directories |

These require `HAMCP_ENABLE_FILESYSTEM_TOOLS=true` and `ENABLE_YAML_CONFIG_EDITING=true` in the MCP server env (already set in `.cursor/mcp.json`).

## Step 5: Verify the Connection

Ask the agent to list HA entities or check a device state. If MCP is connected, it can query your instance directly.

You can also verify the REST API manually:

```bash
source homeassistant-config/.env.mcp
curl -H "Authorization: Bearer $HOMEASSISTANT_TOKEN" "$HOMEASSISTANT_URL/api/"
```

Expected response: `{"message":"API running."}`

## Security Best Practices

- **Local network only:** Only run ha-mcp on your local network or over a VPN.
- **Dedicated user:** Create a dedicated HA user for the agent with only the permissions it needs.
- **Token safety:** Never commit tokens to Git. Use `.env.mcp` or `secrets.yaml` (both gitignored).
- **Entity access:** Restrict domains through HA user permissions where possible.

## Troubleshooting

- **Use the Python package:** Run `uvx --from ha-mcp ha-mcp`, not the old npm `ha-mcp` package (1 tool vs ~86 tools).
- **Env var names:** The official server expects `HOMEASSISTANT_URL` and `HOMEASSISTANT_TOKEN`.
- **File tools return errors:** Confirm `ha_mcp_tools` is installed, HA was restarted, and the integration was added under Devices & Services.
- **Connection refused on localhost:** Use `http://homeassistant.local:8123` if HA runs on another device.
- **MCP not showing in Cursor:** Restart Cursor after editing `.cursor/mcp.json`.
