# LivingroomOS Installation

**Supported system:** Debian 13 (Trixie), x86_64 / amd64  
**Install source:** GitHub `main` branch

> LivingroomOS is a pre-release. Install it on a test machine first. ARM/ARM64 is not supported.
>
> First install a minimal Debian 13 system using [DEBIANINSTALL.md](DEBIANINSTALL.md). Keep SSH access available so you can recover the machine if the graphical session does not start.

## 1. Download the project

Log in with your normal Debian user. Copy and paste this complete block:

```bash
set -e

# Check the supported platform
test "$(dpkg --print-architecture)" = "amd64" || {
    echo "ERROR: LivingroomOS requires Debian amd64 (x86_64)."
    exit 1
}
grep -q 'VERSION_ID="13"' /etc/os-release || {
    echo "ERROR: LivingroomOS requires Debian 13."
    exit 1
}

sudo apt update
sudo apt install -y git wget curl ca-certificates

# Do not overwrite an existing checkout
test ! -e "$HOME/LivingroomOS" || {
    echo "ERROR: ~/LivingroomOS already exists. Move or remove it before continuing."
    exit 1
}

git clone --branch main --single-branch https://github.com/Printronics/LivingroomOS.git
```

## 2. Install LivingroomOS

Copy and paste this complete block. It installs the required Debian packages, Google Chrome, the application and its system configuration.

```bash
set -e

PROJECT="$HOME/LivingroomOS/livingroomos"

# Install the required packages listed by the project
sudo apt install --no-install-recommends -y \
    $(awk '!/^[[:space:]]*#/ && NF {print $1}' "$PROJECT/debian-packages.txt")

# Install Google Chrome Stable
cd /tmp
wget -O google-chrome-stable.deb \
    https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install -y ./google-chrome-stable.deb
rm -f google-chrome-stable.deb

# Create the dedicated service account
if ! id livingroomos >/dev/null 2>&1; then
    sudo useradd --system --create-home \
        --home-dir /var/lib/livingroomos \
        --shell /usr/sbin/nologin livingroomos
fi

# Install application files (program code stays root-owned)
sudo install -d -o root -g root -m 755 /opt/livingroomos
sudo cp -a "$PROJECT/." /opt/livingroomos/
sudo chown -R root:root /opt/livingroomos
sudo find /opt/livingroomos -type d -exec chmod 755 {} \\;
sudo find /opt/livingroomos -type f -exec chmod 644 {} \\;
sudo find /opt/livingroomos -type f -name '*.sh' -exec chmod 755 {} \\;
sudo chmod 755 \
    /opt/livingroomos/system/bin/livingroomos-session \
    /opt/livingroomos/system/bin/livingroomosctl

# Install the managed Google Chrome policy
sudo install -d -o root -g root -m 755 /etc/opt/chrome/policies/managed
sudo install -o root -g root -m 644 \
    /opt/livingroomos/system/chrome/livingroomos.json \
    /etc/opt/chrome/policies/managed/livingroomos.json

# Create the writable runtime settings file
sudo install -d -o livingroomos -g livingroomos -m 700 \
    /var/lib/livingroomos/.config/livingroomos
sudo install -o livingroomos -g livingroomos -m 600 \
    /opt/livingroomos/backend/config/settings.json \
    /var/lib/livingroomos/.config/livingroomos/settings.json

# Install systemd user units
sudo install -d -o livingroomos -g livingroomos -m 700 \
    /var/lib/livingroomos/.config/systemd/user
sudo install -o livingroomos -g livingroomos -m 644 \
    /opt/livingroomos/system/systemd/user/livingroomos-backend.service \
    /opt/livingroomos/system/systemd/user/livingroomos-shell.service \
    /opt/livingroomos/system/systemd/user/livingroomos.target \
    /var/lib/livingroomos/.config/systemd/user/

# Install the restricted power-management policy
sudo install -d -o root -g root -m 755 /etc/polkit-1/rules.d
sudo install -o root -g root -m 644 \
    /opt/livingroomos/system/polkit/50-livingroomos-power.rules \
    /etc/polkit-1/rules.d/50-livingroomos-power.rules

# Back up an existing greetd configuration, then install ours
if [ -f /etc/greetd/config.toml ] && [ ! -f /etc/greetd/config.toml.before-livingroomos ]; then
    sudo cp /etc/greetd/config.toml /etc/greetd/config.toml.before-livingroomos
fi
sudo install -o root -g root -m 644 \
    /opt/livingroomos/system/greetd/config.toml \
    /etc/greetd/config.toml

# Reserve tty1 for greetd
sudo install -d -o root -g root -m 755 \
    /etc/systemd/system/greetd.service.d
sudo tee /etc/systemd/system/greetd.service.d/tty1.conf >/dev/null <<'EOF'
[Unit]
After=getty@tty1.service
Conflicts=getty@tty1.service
EOF

sudo systemctl daemon-reload
sudo systemctl disable --now getty@tty1.service

# Check the installation before enabling automatic startup
sudo -u livingroomos python3 -B \
    /opt/livingroomos/tools/check_system.py \
    --config /var/lib/livingroomos/.config/livingroomos/settings.json

echo
echo "Installation files and configuration are in place."
echo "Review the system-check output before continuing."
```

If the system checker reports a blocking error, fix it before continuing.

## 3. Start LivingroomOS

Make sure you have working SSH access or another recovery method. Enabling greetd replaces the normal graphical/login startup with the LivingroomOS session.

```bash
sudo systemctl enable greetd
sudo reboot
```

After reboot, LivingroomOS should start automatically. The labwc session starts the systemd user target, which launches the backend and Google Chrome.

## 4. Useful checks

Run these commands over SSH if you need to inspect the installation:

**greetd and the reserved terminal**
```bash
sudo systemctl status greetd --no-pager
sudo systemctl is-active getty@tty1.service
```

**Backend and launcher (from a terminal inside the LivingroomOS graphical session)**
```bash
systemctl --user status livingroomos-backend.service --no-pager
systemctl --user status livingroomos-shell.service --no-pager
```

**Backend logs (from the graphical session)**
```bash
journalctl --user -u livingroomos-backend.service -b --no-pager -n 80
```

**greetd logs (over SSH)**
```bash
sudo journalctl -u greetd -b --no-pager -n 80
```

Do not start `livingroomos.target` from a plain SSH shell. The Chrome launcher needs the Wayland environment provided by the graphical session.

## 5. Add or change web applications

Web applications are configured with one `.cfg` file per app:

```text
/opt/livingroomos/backend/config/apps/
```

Edit or add these files as an administrator. The filename must match the `id` inside the file. See [App Configuration](docs/APP_KONFIGURATION.md) for the format and examples.

After changing an app configuration, restart the backend from a terminal inside the LivingroomOS graphical session:

```bash
systemctl --user restart livingroomos-backend.service
```

## 6. Recovery and uninstall

Keep SSH access available. The kiosk configuration does not provide the usual labwc virtual-terminal shortcuts.

To stop the LivingroomOS graphical session:

```bash
sudo systemctl disable --now greetd
```

To remove the application and its dedicated system configuration:

```bash
sudo rm -rf /opt/livingroomos
sudo rm -f \
    /etc/opt/chrome/policies/managed/livingroomos.json \
    /etc/polkit-1/rules.d/50-livingroomos-power.rules \
    /etc/systemd/system/greetd.service.d/tty1.conf \
    /var/lib/livingroomos/.config/systemd/user/livingroomos-backend.service \
    /var/lib/livingroomos/.config/systemd/user/livingroomos-shell.service \
    /var/lib/livingroomos/.config/systemd/user/livingroomos.target
```

Restore the previous greetd configuration if one was backed up:

```bash
if [ -f /etc/greetd/config.toml.before-livingroomos ]; then
    sudo cp /etc/greetd/config.toml.before-livingroomos /etc/greetd/config.toml
fi
sudo systemctl daemon-reload
sudo systemctl enable --now getty@tty1.service
```

The runtime settings, browser profiles and logs are stored in `/var/lib/livingroomos`. Remove that directory and the `livingroomos` account only if you no longer need their data:

```bash
sudo rm -rf /var/lib/livingroomos
sudo userdel livingroomos
```

Do not remove shared Debian packages unless you have checked that no other software needs them.

---

**Development status:** LivingroomOS is a pre-release. Hardware-specific behavior, automatic startup, browser playback, audio, input devices and recovery must be tested on the target machine.
