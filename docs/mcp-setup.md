# ha-mcp Setup Guide

[ha-mcp](https://github.com/homeassistant-ai/ha-mcp) lets coding agents (like Claude Code) interact with your Home Assistant instance through MCP (Model Context Protocol).

## Prerequisites

- A running Home Assistant instance accessible on your network
- Node.js 18+ installed
- A long-lived access token from HA

## Step 1: Create a Long-Lived Access Token

1. Open your HA instance in a browser.
2. Click your profile icon (bottom-left).
3. Go to **Security** tab.
4. Scroll to **Long-Lived Access Tokens**.
5. Click **Create Token**.
6. Name it something descriptive (e.g., "Claude Code MCP").
7. Copy the token immediately — it won't be shown again.
8. Store it in your `secrets.yaml` as `ha_long_lived_token`.

## Step 2: Install and Configure ha-mcp

### For Claude Code

Add to your Claude Code MCP config (`~/.claude/settings.json` or project-level):

```json
{
  "mcpServers": {
    "ha-mcp": {
      "command": "npx",
      "args": ["-y", "@anthropic-ai/ha-mcp"],
      "env": {
        "HOME_ASSISTANT_URL": "http://your-ha-instance:8123",
        "HOME_ASSISTANT_TOKEN": "your-long-lived-token"
      }
    }
  }
}
```

> **Note:** Check the [ha-mcp repo](https://github.com/homeassistant-ai/ha-mcp) for the current correct package name and configuration format, as it may have changed.

### Via Docker

```bash
docker run -e HOME_ASSISTANT_URL=http://your-ha-instance:8123 \
           -e HOME_ASSISTANT_TOKEN=your-token \
           ghcr.io/homeassistant-ai/ha-mcp
```

## Step 3: Verify the Connection

Once configured, ask Claude Code to list your HA entities or check a device state. If the MCP server is running correctly, it will be able to query your HA instance.

## Security Best Practices

- **Local network only:** Only run ha-mcp on your local network or over a VPN. Do not expose your HA instance or tokens to the public internet.
- **Dedicated user:** Create a dedicated HA user for the agent with only the permissions it needs.
- **Token safety:** Never commit tokens to Git. Use `secrets.yaml` (which is gitignored) or environment variables.
- **Entity access:** Consider which entities and domains the agent should be able to control. You can restrict this through HA user permissions.
