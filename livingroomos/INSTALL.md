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

The command should return the installed Chrome version.

Do not substitute Chromium unless the project is explicitly changed and tested to support it.

---

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

Before starting the backend, identify the settings template or initial configuration supplied by the project. Use that file to create `settings.json` at the expected location.

Do not create an empty JSON file as a substitute for the application's required configuration.

Set ownership and permissions after installing the initial settings:

```bash
sudo chown livingroomos:livingroomos \
    /var/lib/livingroomos/.config/livingroomos/settings.json

sudo chmod 600 \
    /var/lib/livingroomos/.config/livingroomos/settings.json
```

If the project version does not provide a settings template, check the configuration requirements in the backend before starting the service.

---

## 9. Test the backend manually

Before enabling automatic startup, verify that the backend can be started.

Run:

```bash
sudo -u livingroomos \
    /opt/livingroomos/.venv/bin/python \
    /opt/livingroomos/backend/main.py
```

If the project uses `run.sh` as its supported entry point, use that script instead:

```bash
sudo -u livingroomos /opt/livingroomos/run.sh
```

The backend should listen on:

```text
http://127.0.0.1:8750
```

In another terminal, check its health endpoint:

```bash
curl http://127.0.0.1:8750/api/v1/health
```

The expected response is a successful health response from the backend.

Stop the manually started process before proceeding with systemd configuration.

---

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

LivingroomOS uses Wayland and labwc.

The project includes session configuration under:

```text
/opt/livingroomos/system/
```

Review the supplied configuration before installing it.

The greetd configuration is expected to start the LivingroomOS session using:

```text
/opt/livingroomos/system/bin/livingroomos-session
```

Make sure the script exists and is executable:

```bash
sudo test -x /opt/livingroomos/system/bin/livingroomos-session \
    && echo "Session script is executable"
```

Check the labwc configuration and confirm that the application startup command points to the correct project location.

Do not enable automatic login until manual session startup has been tested successfully.

---

## 12. Configure systemd

The project provides systemd integration under:

```text
/opt/livingroomos/system/systemd/
```

Review the included unit files before installing them.

Install the appropriate units into the systemd configuration directory according to their intended scope:

- System units belong in `/etc/systemd/system/`.
- User units belong in the relevant user's systemd configuration directory.

Do not install user units as system units or vice versa.

Check the service configuration for the expected settings path:

```text
%h/.config/livingroomos/settings.json
```

For the `livingroomos` service account, `%h` should resolve to its configured home directory, `/var/lib/livingroomos`.

After installing the units, reload systemd:

```bash
sudo systemctl daemon-reload
```

Enable only the services required by the supplied configuration.

Check service status with:

```bash
systemctl status greetd
```

For a user service, inspect it from the corresponding user session:

```bash
systemctl --user status
```

---

## 13. Configure power management permissions

LivingroomOS provides restart and shutdown controls.

These operations must remain restricted to the intended service account.

The project includes a Polkit rule under:

```text
/opt/livingroomos/system/polkit/
```

Review the rule before installing it.

The intended permissions are limited to the required system power operations:

- Reboot
- Power off

Do not add unrestricted administrator permissions or broad Polkit rules.

After installing the rule, reload or restart the relevant system services if required by the configuration.

Test power operations only on a dedicated test machine.

---

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

Review the Polkit rule and the service account configuration.

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

Remove only the systemd units and Polkit rules that were installed specifically for LivingroomOS.

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
