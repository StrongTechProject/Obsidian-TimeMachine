# Obsidian Timemachine

<p align="center">
  <strong>🕰️ A "Set and Forget" automated backup solution for your Obsidian Vault</strong>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#installation">Installation</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#usage">Usage</a> •
  <a href="#configuration">Configuration</a>
</p>

---

## Features

- **🖥️ Modern TUI**: Clean, interactive menu interface with real-time status updates
- **🔄 Background Automation**: Runs via Cron without opening Obsidian
- **☁️ iCloud Compatible**: Smart detection waits for iCloud sync to complete
- **📦 Dual Modes**: Direct Git mode or Mirror mode (rsync to separate repo)
- **🔐 Secure**: SSH key-based authentication for GitHub/GitLab
- **📝 Auto-commit**: Automatic timestamped commits with smart change detection
- **⏰ Flexible Scheduling**: Native macOS LaunchAgents (15min, hourly, etc) or standard Cron

## Requirements

- Python 3.10+
- Git
- rsync (pre-installed on macOS)
- SSH key for Git authentication

## Installation

### One-Line Install (Recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/StrongTechProject/Obsidian-TimeMachine/main/install.sh | bash
```

This will:
- Check system requirements (Python 3.10+, Git, rsync)
- Install the package
- Optionally run the setup wizard

### From Source

```bash
git clone https://github.com/StrongTechProject/Obsidian-TimeMachine.git
cd Obsidian-TimeMachine
pip install .
```

### Development Install

```bash
pip install -e ".[dev]"
```

### Updating

To update to the latest version:

```bash
ot update
```

Or check for updates without installing:

```bash
ot update --check
```

## Quick Start

### 1. Run the Setup Wizard

```bash
ot setup
```

This interactive wizard will guide you through:
- Setting your Obsidian vault path
- Configuring the Git repository
- Setting up SSH key authentication
- Configuring auto-sync schedule

### 2. Or Manual Configuration

Create `~/.config/ot/config.yaml`:

```yaml
source_dir: ~/Library/Mobile Documents/iCloud~md~obsidian/Documents/MyVault
dest_dir: ~/ObsidianBackup
ssh_key_path: ~/.ssh/id_ed25519
log_retention_days: 7
```

Initialize the destination as a Git repo:

```bash
cd ~/ObsidianBackup
git init
git remote add origin git@github.com:username/your-vault-backup.git
```

### 3. Run Your First Sync

```bash
ot sync
```

## Usage

### Interactive Menu (Recommended)

```bash
ot menu
```

This opens an interactive menu for all operations:

```
  📊 Current Status:
     Source: MyVault
     Repo: obsidian-backup (main)
     Schedule: Every hour
     Last Sync: ✅ Changes pushed to remote (15m ago)

  ──────────────────────────────────────────────────

  1. 🔄 Run Sync Now
  2. 📋 View Full Status
  3. ⏰ Manage Schedule
  4. ⚙️  Run Setup Wizard
  5. 📁 View Logs
  6. 🆕 Check for Updates
  7. ❌ Exit
```

### Command Line (Advanced)

For scripting or quick access, you can use direct commands:

| Command | Description |
|---------|-------------|
| `ot menu` | Open interactive menu |
| `ot sync` | Run backup (pull → sync → commit → push) |
| `ot status` | Check configuration and sync status |
| `ot setup` | Interactive configuration wizard |
| `ot update` | Check for updates and upgrade |
| `ot update --check` | Check for updates only |
| `ot version` | Show version information |
| `ot schedule set <freq>` | Set auto-sync: `15min`, `30min`, `hourly`, `daily` |
| `ot schedule show` | Show current schedule |
| `ot schedule remove` | Disable auto-sync |

### Quick Examples

```bash
# Open interactive menu
ot menu

# Run a manual sync directly
ot sync

# Enable auto-sync every 15 minutes
ot schedule set 15min
```

## Configuration

### Config File Location

`~/.config/ot/config.yaml`

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `source_dir` | Path to Obsidian vault | Required |
| `dest_dir` | Path to Git repository | Required |
| `ssh_key_path` | Path to SSH private key | `~/.ssh/id_ed25519` |
| `log_retention_days` | Days to keep log files | `7` |
| `icloud_wait_timeout` | Seconds to wait for iCloud sync | `120` |
| `rsync_delete` | Delete files in dest not in source | `false` |

### Logs

Logs are stored in `~/.local/share/ot/logs/` with daily rotation.

## How It Works

1. **Pull**: Fetch and merge remote changes
2. **Wait**: Check for iCloud sync completion (if applicable)
3. **Sync**: Copy files using rsync (or cp for first sync)
4. **Commit**: Stage and commit with auto-generated message
5. **Push**: Push to remote repository

## Project Structure

```
ot/
├── __init__.py
├── config.py       # Configuration management
├── logger.py       # Logging with rotation
├── sync.py         # rsync wrapper
├── git_ops.py      # Git operations
├── icloud.py       # iCloud sync detection
├── runner.py       # Main sync orchestrator
├── ssh.py          # SSH key management
├── scheduler.py    # Scheduler (Cron / LaunchAgents)
├── launchd_ops.py  # macOS LaunchAgents management
├── sync_status.py  # Sync status tracking
└── cli/
    ├── main.py     # CLI entry point
    ├── menu.py     # Interactive TUI
    └── wizard.py   # Setup wizard
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

Inspired by the need for a reliable, "set and forget" backup solution for Obsidian that works seamlessly with iCloud.
