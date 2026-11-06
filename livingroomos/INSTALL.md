# LivingroomOS Installation Guide

**Target platform: Debian 13 (Trixie), amd64 / x86_64**

This guide describes how to install and configure LivingroomOS on a minimal Debian 13 system.

**Important:** Complete the Debian installation first by following [DEBIANINSTALL.md](DebianInstall.md). Do not skip the Debian preparation steps.

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

The Debian base system must already be installed according to [DebianInstall.md](DebianInstall.md).

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

The service account is intended to own the application runtime and perform only the operations required by LivingroomOS.

The graphical session configuration may require additional session permissions or group membership depending on the hardware and Debian setup.

Do not grant broad administrative privileges just to make the interface start.

---

## 6. Deploy the project

Copy the LivingroomOS project directory to `/opt/livingroomos`.

For example, if the project is currently in your home directory:

```bash
sudo mkdir -p /opt/livingroomos
sudo cp -a /path/to/LivingroomOS/. /opt/livingroomos/
```

Replace `/path/to/LivingroomOS` with the actual location of your project.

Set ownership according to the intended runtime and security model.

The application should not allow an unprivileged process to modify trusted executable files or system configuration.

Review executable permissions:

```bash
sudo find /opt/livingroomos -type f -name '*.sh' -exec chmod 755 {} \;
```

Make sure that configuration files and application files are not writable by untrusted users.

---

## 7. Set up the Python environment

Switch to the project directory:

```bash
cd /opt/livingroomos
```

Create a virtual environment as the LivingroomOS account:

```bash
sudo -u livingroomos python3 -m venv .venv
```

Install the Python dependencies required by the backend.

At minimum, the application requires FastAPI and Uvicorn:

```bash
sudo -u livingroomos /opt/livingroomos/.venv/bin/pip install fastapi uvicorn
```

If the project contains a `requirements.txt`, use that file instead:

```bash
sudo -u livingroomos /opt/livingroomos/.venv/bin/pip install -r requirements.txt
```

Do not install Python packages globally with `sudo pip`.

---

## 8. Test the backend manually

Start the application:

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

## 9. Run the system checker

Run the system checker:

```bash
sudo -u livingroomos python3 -B /opt/livingroomos/tools/check_system.py
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

## 10. Configure the graphical session

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

## 11. Configure systemd

The project provides systemd integration under:

```text
/opt/livingroomos/system/systemd/
```

Review the included unit files before installing them.

Install the appropriate units into the systemd configuration directory according to their intended scope:

- System units belong in `/etc/systemd/system/`.
- User units belong in the relevant user's systemd configuration directory.

Do not install user units as system units or vice versa.

After installation, reload systemd:

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

## 12. Configure power management permissions

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

## 13. Enable automatic startup

Only continue after the following have been verified:

- The backend starts successfully.
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

## 14. Initial test checklist

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

## 15. Troubleshooting

### The backend does not start

Check the Python environment:

```bash
ls -la /opt/livingroomos/.venv/bin/python
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

## 16. Uninstall and recovery

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

## 17. Internal testing notes

This installation guide describes the intended deployment configuration. Hardware-specific behavior can vary, particularly for:

- GPU drivers
- HDMI audio
- display resolution and refresh rate
- remote-control input devices
- Wayland session permissions
- automatic login behavior

Test the complete startup and recovery process before deploying LivingroomOS to a device that is used regularly.

**LivingroomOS is currently intended for internal testing.**
