# Git Pull Add-on Setup

The Git Pull add-on automatically syncs your HA configuration from this GitHub repository.

## Step 1: Install the Add-on

1. In HA, go to **Settings > Add-ons**.
2. Click **Add-on Store** (bottom-right).
3. Search for **"Git pull"**.
4. Click **Install**.

## Step 2: Generate a Deploy Key (Recommended)

Deploy keys are more secure than personal access tokens because they only grant access to a single repository.

```bash
# Generate a new SSH key pair
ssh-keygen -t ed25519 -C "homeassistant-git-pull" -f ~/.ssh/ha_deploy_key -N ""

# Display the public key (add this to GitHub)
cat ~/.ssh/ha_deploy_key.pub

# Display the private key (add this to the Git Pull add-on config)
cat ~/.ssh/ha_deploy_key
```

### Add the public key to GitHub:

1. Go to your repo on GitHub: **Settings > Deploy keys**.
2. Click **Add deploy key**.
3. Paste the public key contents.
4. Do NOT enable write access (read-only is sufficient).
5. Click **Add key**.

## Step 3: Configure the Add-on

In the Git Pull add-on configuration:

```yaml
git_branch: main
git_command: pull
git_remote: origin
repository: git@github.com:YOUR_USERNAME/homeassistant-config.git
auto_restart: false
repeat:
  active: true
  interval: 300  # Check every 5 minutes
deployment_key:
  - "-----BEGIN OPENSSH PRIVATE KEY-----"
  - "your-private-key-contents-here"
  - "-----END OPENSSH PRIVATE KEY-----"
deployment_key_protocol: ssh
```

### Auto-restart trade-offs

- **`auto_restart: true`** — HA restarts automatically after each pull. Convenient but can cause brief interruptions to automations.
- **`auto_restart: false`** (recommended) — Changes are pulled but HA doesn't restart until you do it manually. Safer for a production home. You can reload individual domains (automations, scripts, scenes) without a full restart.

## Step 4: Test the Initial Pull

1. Start the Git Pull add-on.
2. Check the add-on logs for successful clone/pull messages.
3. Verify that the config files appear in your HA config directory.
4. Run **Settings > System > Restart** (or use Developer Tools > Check Configuration first).

## Alternative: Personal Access Token

If you prefer not to use deploy keys:

1. Create a [GitHub personal access token](https://github.com/settings/tokens) with `repo` scope.
2. Use HTTPS URL in the add-on config: `https://github.com/YOUR_USERNAME/homeassistant-config.git`
3. Set the token in the add-on's Git credentials.

Deploy keys are preferred because they're scoped to a single repo and can be read-only.
