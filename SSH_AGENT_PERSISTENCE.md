# SSH Agent Persistence

## Overview

SSH keys loaded during devcontainer creation are now **persistent across all terminal sessions**. The SSH agent is started once and shared across all shells.

## How It Works

### 1. Post-Create Setup

When the devcontainer is created (`.devcontainer/post-create.sh`):

1. **Checks environment**: Only runs in `devcontainer` (not GitHub Actions)
2. **Starts persistent SSH agent**: Creates `~/.ssh-agent-info` with agent socket and PID
3. **Loads SSH keys**: Adds keys from `/home/vscode/.ssh-host/` to the agent
4. **Configures .bashrc**: Adds code to source `~/.ssh-agent-info` in all future shells

### 2. Future Shells

Every new terminal automatically:

1. Sources `~/.bashrc`
2. Loads `~/.ssh-agent-info` (SSH_AUTH_SOCK and SSH_AGENT_PID)
3. Connects to the same SSH agent process
4. Has access to all loaded SSH keys

## Implementation Details

### SSH Agent Info File

Location: `~/.ssh-agent-info`

Contains:
```bash
SSH_AUTH_SOCK=/tmp/ssh-mVbC0GA1D1Fc/agent.4554; export SSH_AUTH_SOCK;
SSH_AGENT_PID=4555; export SSH_AGENT_PID;
echo Agent pid 4555;
```

### .bashrc Addition

```bash
# Load SSH agent info for persistent agent across all shells
if [[ -f "$HOME/.ssh-agent-info" ]]; then
    source "$HOME/.ssh-agent-info" >/dev/null 2>&1
fi
```

### Environment Check

```bash
# SSH setup only in devcontainer (not GitHub Actions)
if [[ "$ENV_TYPE" != "devcontainer" ]]; then
    log_debug "Skipping SSH key setup (not devcontainer environment)"
    return
fi
```

## Verification

### Check SSH Keys Are Loaded

```bash
ssh-add -l
```

**Expected output:**
```
256 SHA256:VKTWKoqpe8q/yuUrmy3HMU+3UubQY/LrAtiwy55CK8E vb@example.com (ED25519)
```

### Check Agent Process

```bash
ps aux | grep ssh-agent
echo "SSH_AGENT_PID: $SSH_AGENT_PID"
```

### Test in New Terminal

1. Open new terminal in VS Code
2. Run `ssh-add -l`
3. Should see loaded keys (no passphrase prompt)

## Troubleshooting

### "The agent has no identities"

**Cause**: SSH agent file exists but keys not loaded

**Fix**:
```bash
# Re-run post-create to load keys
.devcontainer/post-create.sh
```

### "Could not open a connection to your authentication agent"

**Cause**: SSH_AUTH_SOCK not set or stale

**Fix**:
```bash
# Restart SSH agent
rm ~/.ssh-agent-info
ssh-agent -s > ~/.ssh-agent-info
source ~/.ssh-agent-info
ssh-add ~/.ssh-host/your-key
```

### Keys Not Persisting After Devcontainer Rebuild

**Expected behavior**: SSH agent state is lost on rebuild

**Fix**: Rebuild triggers post-create.sh which loads keys again (passphrase required once)

## Environment-Specific Behavior

### Devcontainer
- ✅ SSH agent started and persisted
- ✅ Keys loaded from `/home/vscode/.ssh-host/`
- ✅ Available in all terminal sessions

### GitHub Actions
- ❌ SSH agent setup skipped
- ℹ️ GitHub provides its own SSH key handling
- ℹ️ Use `webfactory/ssh-agent` action if needed

### Local Development (non-container)
- ❌ SSH agent setup skipped
- ℹ️ Use your system's SSH agent
- ℹ️ Run `eval $(ssh-agent)` and `ssh-add` manually

## Files Modified

- `.devcontainer/post-create.sh` - SSH agent persistence logic
- `~/.bashrc` - Auto-loading of SSH agent info
- `~/.ssh-agent-info` - Agent socket and PID (auto-generated)

## Security Considerations

### SSH Agent Socket

The SSH agent socket (`SSH_AUTH_SOCK`) is stored in `/tmp/` with restricted permissions:

```bash
$ ls -l /tmp/ssh-*/agent.*
srwxr-xr-x 1 vscode vscode 0 Nov 22 10:30 /tmp/ssh-mVbC0GA1D1Fc/agent.4554
```

### Key Storage

SSH keys are mounted read-only from host `~/.ssh/`:

```yaml
# .devcontainer/devcontainer.json
"mounts": [
  "source=${localEnv:HOME}/.ssh,target=/home/vscode/.ssh-host,type=bind,readonly"
]
```

**Benefits:**
- Keys never written to container
- Keys never committed to image
- Same keys across all devcontainers
- Passphrase required on devcontainer rebuild

## Comparison: Before vs After

### Before (No Persistence)

```bash
# Terminal 1
$ ssh-add -l
The agent has no identities.  # ❌

# Terminal 2 (new)
$ ssh-add -l
Could not open a connection to your authentication agent  # ❌
```

### After (With Persistence)

```bash
# Terminal 1
$ ssh-add -l
256 SHA256:VKT... vb@example.com (ED25519)  # ✅

# Terminal 2 (new)
$ ssh-add -l
256 SHA256:VKT... vb@example.com (ED25519)  # ✅ Same keys!
```

## Integration with Git

SSH keys are automatically available for Git operations:

```bash
# No SSH setup needed - works immediately
git pull
git push origin main

# Git uses SSH_AUTH_SOCK automatically
git remote -v
# origin  git@github.com:user/repo.git (fetch)
```

## See Also

- `.devcontainer/post-create.sh` - Implementation
- `FAIL_FAST_POLICY.md` - Configuration philosophy
- `AGENTS.md` - Agent workflow documentation
