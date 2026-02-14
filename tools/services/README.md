# Service Installation Guide

## RK3588 Edge (systemd)

```bash
# Copy service file
sudo cp neuro-pipeline-edge.service /etc/systemd/system/

# Reload and enable
sudo systemctl daemon-reload
sudo systemctl enable neuro-pipeline-edge
sudo systemctl start neuro-pipeline-edge

# Check status
sudo systemctl status neuro-pipeline-edge
journalctl -u neuro-pipeline-edge -f
```

## Mac Central (launchd)

```bash
# Copy plist (user agent — runs at login)
cp com.neuro-pipeline.central.plist ~/Library/LaunchAgents/

# Load and start
launchctl load ~/Library/LaunchAgents/com.neuro-pipeline.central.plist

# Check status
launchctl list | grep neuro-pipeline

# Stop and unload
launchctl unload ~/Library/LaunchAgents/com.neuro-pipeline.central.plist
```

## Log Locations

- Edge: `journalctl -u neuro-pipeline-edge` or `/opt/neuro-pipeline/logs/`
- Central: `/opt/neuro-pipeline/logs/central.log` (rotating, 10MB x 5)
