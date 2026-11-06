# LivingroomOS Installation Guide

**Target platform: Debian 13 (Trixie), amd64 / x86_64**

This guide describes how to install and configure LivingroomOS on a minimal Debian 13 system.

**Important:** Complete the Debian installation first by following [DEBIANINSTALL.md](DEBIANINSTALL.md). Do not skip the Debian preparation steps.

LivingroomOS is currently intended for internal testing. Perform the initial installation on a dedicated test machine.

---

## 1. Requirements

### Hardware

- x86_64 / amd64 processor
- Graphics hardware with working Linux DRM/KMS support
- Display or television connected to the system
- Keyboard or another supported input device
- Internet connection for package installation

ARM and ARM64 hardware are not supported.

### Software

The Debian base system must already be installed according to [DEBIANINSTALL.md](DEBIANINSTALL.md).

The following components will be installed or configured during this guide:

- Python 3
- Google Chrome Stable
- Wayland
- labwc
- greetd
- systemd
- Polkit
- PipeWire

---

## 2. Verify the Debian installation

Log in using the regular Debian user created during the Debian installation.

Check the architecture:

```bash
uname -m
```

Expected output:

```text
x86_64
```

Check the Debian version:

```bash
cat /etc/os-release
```

Make sure the system is running Debian 13.

Check network connectivity:

```bash
ping -c 3 deb.debian.org
```

Update the system:

```bash
sudo apt update
sudo apt full-upgrade -y
```

If the architecture is not x86_64, stop here.

---

## 3. Install system dependencies

Install the required Debian packages:

```bash
sudo apt install -y \
    python3 \
    python3-venv \
    python3-pip \
    python3-dev \
    build-essential \
    labwc \
    greetd \
    systemd \
    dbus-user-session \
    libpam-systemd \
    polkitd \
    pipewire \
    pipewire-pulse \
    wireplumber \
    mesa-utils \
    fonts-noto-core \
    fonts-noto-color-emoji \
    curl \
    ca-certificates \
    unzip \
    git \
    wget
```

Some packages may already be installed or may have different availability depending on the Debian repository configuration.

Install any additional dependencies listed in `debian-packages.txt` if they are not already covered.

---

## 4. Install Google Chrome Stable

LivingroomOS uses Google Chrome Stable as its supported browser.

Download it from the official distribution endpoint:

```bash
cd /tmp
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
```

Install it:

```bash
sudo apt install -y ./google-chrome-stable_current_amd64.deb
```

Verify the installation:

```bash
google-chrome-stable --version
```

Install the managed Chrome policy shipped with LivingroomOS:

```bash
sudo install -d -o root -g root -m 755 /etc/opt/chrome/policies/managed
sudo install -o root -g root -m 644 \
    /opt/livingroomos/system/chrome/livingroomos.json \
    /etc/opt/chrome/policies/managed/livingroomos.json
```

The policy is installed system-wide and must remain owned by root. Restart Chrome after changing it.

Do not substitute Chromium unless the project is explicitly changed and tested to support it.

## 5. Create the LivingroomOS service account

Create a dedicated system user:

```bash
sudo useradd \
    --system \
    --create-home \
    --home-dir /var/lib/livingroomos \
    --shell /usr/sbin/nologin \
    livingroomos
```

If the account already exists, do not create it again. Verify its home directory and shell instead:

```bash
getent passwd livingroomos
```

The service account should not own or be able to modify trusted application code.

---

## 6. Deploy the project

The application files are located in the repository's `livingroomos/` subdirectory.

Copy the contents of that directory to `/opt/livingroomos`.

For example, if the repository was cloned into your home directory:

```bash
sudo install -d -o root -g root -m 755 /opt/livingroomos
sudo cp -a ~/LivingroomOS/livingroomos/. /opt/livingroomos/
```

Adjust the source path if your repository is stored somewhere else.

Set ownership and permissions:

```bash
sudo chown -R root:root /opt/livingroomos
sudo find /opt/livingroomos -type d -exec chmod 755 {} \;
sudo find /opt/livingroomos -type f -exec chmod 644 {} \;
```

Make shell scripts executable:

```bash
sudo find /opt/livingroomos -type f -name '*.sh' -exec chmod 755 {} \;
```

The two extensionless helper programs are also started directly by greetd and labwc. Make them executable explicitly:

```bash
sudo chmod 755 \
    /opt/livingroomos/system/bin/livingroomos-session \
    /opt/livingroomos/system/bin/livingroomosctl
```
The application directory must remain protected against modification by the service account.

Do not make `/opt/livingroomos` writable by the `livingroomos` user.

---

## 7. Set up the Python environment

Create the virtual environment as root so that the application runtime cannot modify its installed Python packages:

```bash
sudo python3 -m venv /opt/livingroomos/.venv
```

Install the Python dependencies.

If the project contains `requirements.txt`, use:

```bash
sudo /opt/livingroomos/.venv/bin/pip install \
    -r /opt/livingroomos/requirements.txt
```

If no requirements file is available, the backend at minimum requires FastAPI and Uvicorn:

```bash
sudo /opt/livingroomos/.venv/bin/pip install fastapi uvicorn
```

Do not install Python packages globally with `sudo pip`.

The service account needs permission to execute the virtual environment, but it must not have permission to modify it.

---

## 8. Prepare the service configuration

The systemd service configuration uses the service user's home directory for the LivingroomOS settings file.

Create the configuration directory:

```bash
sudo install -d \
    -o livingroomos \
    -g livingroomos \
    -m 700 \
    /var/lib/livingroomos/.config/livingroomos
```

The expected settings path is:

```text
/var/lib/livingroomos/.config/livingroomos/settings.json
```

Create the runtime settings file from the configuration template included in the repository:

```bash
sudo install \
    -o livingroomos \
    -g livingroomos \
    -m 600 \
    /opt/livingroomos/backend/config/settings.json \
    /var/lib/livingroomos/.config/livingroomos/settings.json
```

This copies the supplied configuration into the exact path used by the backend. The source file remains part of the downloaded project; the runtime copy is owned by `livingroomos` because the application saves UI settings to it.

Before the first start, edit the runtime copy and replace the example streaming URLs with the services you actually use. In particular, `example.com` and `example.org` are placeholders, and `localhost:8096` requires a media server listening on that address.

---

## 9. Test the backend manually

Before enabling automatic startup, verify that the backend can be started with the same runtime configuration used by the systemd user service.

Run:

```bash
sudo -u livingroomos env \
    LIVINGROOMOS_CONFIG=/var/lib/livingroomos/.config/livingroomos/settings.json \
    /opt/livingroomos/run.sh
```

The `run.sh` entry point automatically uses `/opt/livingroomos/.venv` when that virtual environment exists. The explicit `LIVINGROOMOS_CONFIG` value is important: without it, this manual test would use the read-only template inside the application directory instead of the writable runtime settings file.

The backend should listen on:

```text
http://127.0.0.1:8750
```

In another terminal, check its health endpoint:

```bash
curl http://127.0.0.1:8750/api/v1/health
```

The expected response is:

```json
{"status":"ok"}
```

Stop the manually started process with `Ctrl+C` before proceeding with systemd configuration.

## 10. Run the system checker

Run the system checker:

```bash
sudo -u livingroomos \
    /opt/livingroomos/.venv/bin/python \
    -B /opt/livingroomos/tools/check_system.py
```

Review any missing dependencies or configuration warnings.

The checker is intended to identify important system requirements such as:

- x86_64 architecture
- Google Chrome
- labwc
- greetd
- required system components

Optional utilities may be reported separately.

Resolve blocking errors before enabling automatic startup.

---

## 11. Configure the graphical session

LivingroomOS uses Wayland and labwc. Install the supplied greetd configuration:

```bash
sudo install -o root -g root -m 644 \
    /opt/livingroomos/system/greetd/config.toml \
    /etc/greetd/config.toml
```

This replaces the existing greetd configuration. If the machine already has a custom greetd setup, back it up before running the command.

The session script starts labwc with the project configuration directory:

```text
/opt/livingroomos/system/labwc
```

The script passes this directory to labwc with `-C`; do not copy these files to a different location unless you also update the session script.

Verify that the session script is executable:

```bash
sudo test -x /opt/livingroomos/system/bin/livingroomos-session \
    && echo "Session script is executable"
```

The labwc autostart file starts the LivingroomOS systemd user target. The Home key bindings in `rc.xml` call `livingroomosctl` by its absolute project path. Keep the project at `/opt/livingroomos` unless you update all corresponding paths.

Do not enable automatic login until manual session startup has been tested successfully.

## 12. Configure systemd

The supplied units are **systemd user units**, not system-wide system services. Install them into the dedicated service user's configuration directory:

```bash
sudo install -d \
    -o livingroomos \
    -g livingroomos \
    -m 700 \
    /var/lib/livingroomos/.config/systemd/user

sudo install -o livingroomos -g livingroomos -m 644 \
    /opt/livingroomos/system/systemd/user/livingroomos-backend.service \
    /opt/livingroomos/system/systemd/user/livingroomos-shell.service \
    /opt/livingroomos/system/systemd/user/livingroomos.target \
    /var/lib/livingroomos/.config/systemd/user/
```

The labwc autostart file runs `systemctl --user start livingroomos.target` inside the `livingroomos` graphical session. The target starts the backend and Chrome launcher. These units are therefore started by the session; do not install them under `/etc/systemd/system/` and do not enable them as system services.

After the first greetd login, inspect the user manager from a terminal in the LivingroomOS session:

```bash
systemctl --user daemon-reload
systemctl --user status livingroomos.target
systemctl --user status livingroomos-backend.service
systemctl --user status livingroomos-shell.service
```

The backend unit uses `%h/.config/livingroomos/settings.json`. For the `livingroomos` account, `%h` must resolve to `/var/lib/livingroomos`.

The greetd configuration is installed separately in Section 11. Reloading the system-wide systemd manager does not reload user units; use `systemctl --user daemon-reload` from the corresponding user session.

## 13. Configure power management permissions

The backend requests restart and shutdown through fixed `systemctl reboot` and `systemctl poweroff` commands. Authorization is handled by Debian's systemd-logind and Polkit policy.

The repository includes a narrowly scoped JavaScript Polkit rule at `system/polkit/50-livingroomos-power.rules`. Install it system-wide:

```bash
sudo install -d -o root -g root -m 755 /etc/polkit-1/rules.d
sudo install -o root -g root -m 644 \
    /opt/livingroomos/system/polkit/50-livingroomos-power.rules \
    /etc/polkit-1/rules.d/50-livingroomos-power.rules
```

The rule grants only the dedicated `livingroomos` account permission for the four explicit systemd-logind actions covering reboot and power-off, including the multiple-session variants. It does not grant general administrator privileges or permission for suspend, hibernate, or unrelated Polkit actions. Polkit monitors its rules directories and reloads rules when files change; a daemon restart is normally unnecessary.

Because the backend and launched applications share the `livingroomos` UID, any process that gains code execution as that account can also request these power actions. Keep the account dedicated to LivingroomOS and test restart and shutdown on the target Debian 13 machine.

## 14. Enable automatic startup

Only continue after the following have been verified:

- The backend starts successfully.
- The settings file exists and has the correct ownership.
- The health endpoint responds.
- Chrome launches successfully.
- labwc starts correctly.
- The LivingroomOS session script is executable.
- The relevant systemd units are installed.
- Power management permissions have been reviewed.

Enable greetd:

```bash
sudo systemctl enable greetd
```

For the first automatic-start test, keep a separate SSH connection or another recovery method available.

Then reboot:

```bash
sudo reboot
```

The system should start the configured LivingroomOS session.

---

## 15. Initial test checklist

After the first successful startup, test the following:

- [ ] LivingroomOS starts automatically.
- [ ] The display uses the expected resolution.
- [ ] The interface is visible and usable.
- [ ] Keyboard navigation works.
- [ ] Google Chrome launches.
- [ ] Application navigation works.
- [ ] Settings can be changed.
- [ ] Settings persist after restarting the application.
- [ ] The Debug section contains the test applications.
- [ ] System status information is displayed.
- [ ] Restart works as intended.
- [ ] Shutdown works as intended.
- [ ] The interface recovers from a backend restart.
- [ ] Logs do not contain unexpected errors.

---

## 16. Troubleshooting

### The backend does not start

Check the Python environment:

```bash
ls -la /opt/livingroomos/.venv/bin/python
```

Check the settings file:

```bash
sudo -u livingroomos test -r \
    /var/lib/livingroomos/.config/livingroomos/settings.json
```

Check the backend manually:

```bash
sudo -u livingroomos /opt/livingroomos/run.sh
```

Review the terminal output for missing dependencies or configuration errors.

### The health endpoint does not respond

Check whether the backend is running:

```bash
ss -ltnp | grep 8750
```

Check the local endpoint:

```bash
curl -v http://127.0.0.1:8750/api/v1/health
```

Confirm that the backend is listening on `127.0.0.1` and the expected port.

### Chrome does not launch

Check the installed browser:

```bash
google-chrome-stable --version
```

Check the session environment and display permissions.

### The graphical session does not start

Inspect greetd:

```bash
sudo systemctl status greetd
sudo journalctl -u greetd -b
```

Inspect system logs:

```bash
sudo journalctl -b -p warning
```

Check that the session script exists and is executable.

### Restart or shutdown does not work

Check that the session is active and inspect the systemd-logind/Polkit authorization messages. LivingroomOS does not currently install a project-specific Polkit rule; see Section 13 and `docs/SICHERHEIT.md`.

Inspect system logs:

```bash
sudo journalctl -b | grep -i polkit
```

Do not work around permission errors by granting unrestricted root access to the application.

---

## 17. Uninstall and recovery

If the automatic session prevents normal access:

1. Switch to a TTY using the appropriate keyboard shortcut, commonly `Ctrl+Alt+F2`.
2. Log in with an administrator account.
3. Disable greetd:

```bash
sudo systemctl disable --now greetd
```

4. Reboot:

```bash
sudo reboot
```

To remove the application after disabling its services:

```bash
sudo rm -rf /opt/livingroomos
```

Remove only the systemd units and Polkit rules that were installed specifically for LivingroomOS. Remove the supplied rule with:\n\n```bash\nsudo rm -f /etc/polkit-1/rules.d/50-livingroomos-power.rules\n```

Reload systemd after removing system units:

```bash
sudo systemctl daemon-reload
```

Do not remove shared Debian packages unless you have confirmed that no other installed software depends on them.

---

## 18. Internal testing notes

This installation guide describes the intended deployment configuration. Hardware-specific behavior can vary, particularly for:

- GPU drivers
- HDMI audio
- display resolution and refresh rate
- remote-control input devices
- Wayland session permissions
- automatic login behavior

Test the complete startup and recovery process before deploying LivingroomOS to a device that is used regularly.

**LivingroomOS is currently intended for internal testing.**
