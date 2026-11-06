# Debian 13 Installation Guide

**Target platform: Debian 13 (Trixie), amd64 / x86_64**

This document describes how to install a clean, minimal Debian 13 system that will later be configured to run LivingroomOS.

Complete this guide before following [INSTALL.md](INSTALL.md).

---

## 1. Download Debian

Download the official Debian 13 amd64 installation image:

[https://www.debian.org/distrib/](https://www.debian.org/distrib/)

For this installation, the **64-bit PC netinst ISO** is recommended.

Create a bootable USB drive using a suitable tool, such as Rufus or balenaEtcher.

**Important:** Creating the installation medium will erase the selected USB drive. Back up any existing data on it before continuing.

Boot the target PC from the USB drive.

## 2. Start the installer

At the Debian boot menu, select:

**Graphical install**

## 3. Language, location and keyboard

Choose the preferred installation language.

Recommended settings:

| Setting | Recommended value |
|---|---|
| Language | English or German |
| Location | Your actual country |
| Keyboard layout | Matching your physical keyboard |

These settings determine the system language, locale, time zone defaults, and keyboard configuration.

## 4. Configure the network

Connect the PC to the network.

If a DHCP server is available, the installer should automatically configure the network.

For a wired Ethernet connection, this normally requires no manual configuration.

If the installer asks for a hostname:

- Choose any name you like.
- The hostname is not important for LivingroomOS.
- Examples: `livingroom`, `media-pc`, or `livingroomos`.

If the installer asks for a domain name:

- You can leave this field empty.
- Alternatively, you can enter `local`.
- A public domain name is not required.

## 5. Configure user accounts

When the installer asks for the root password:

**Leave both root password fields empty and continue.**

Debian will disable direct root account login and configure administrative access through the regular user account.

Next, create a normal user account.

The following values can be chosen freely:

- Full name
- Username
- User password

The username does not need to be `livingroomos`. The dedicated LivingroomOS service account will be created later during the application installation.

**Password recommendation:** Use a strong, unique password, especially because the SSH server will be installed. A strong password is important to protect remote access to the machine.

Do not use an empty password for the regular user.

## 6. Configure the clock and time zone

Select the correct time zone for the machine.

For example, for Germany:

**Europe/Berlin**

The installer should configure the system clock automatically.

## 7. Partition the disk

For a standard LivingroomOS installation, use the entire target disk.

Select:

1. **Guided - use entire disk**
2. Select the intended SSD or HDD.
3. Select **All files in one partition (recommended for new users)**.
4. Review the proposed partition layout.
5. Select **Finish partitioning and write changes to disk**.
6. Confirm the changes.

This keeps the main Linux filesystem together instead of creating separate partitions for `/home`, `/var`, and other directories.

Depending on the system firmware and partitioning choices, Debian may also create:

- An EFI System Partition (required for UEFI boot).
- A swap partition or swap area.

These additional partitions are normal and do not conflict with the intended single-main-partition setup.

**Warning:** Make absolutely sure that the correct disk is selected. Confirming the partition layout will erase the existing contents of that disk.

## 8. Configure the Debian package mirror

When asked whether another installation medium should be scanned, select **No**, unless you have a specific reason to use additional installation media.

When asked to configure a network mirror:

- Select your country.
- Select or enter the Debian mirror hostname:

  `deb.debian.org`

The `deb.debian.org` service automatically directs requests to a suitable Debian mirror.

If the installer asks for an HTTP proxy:

- Leave the field empty.
- Only enter a proxy address if your network explicitly requires one.

The installer should now retrieve the required packages from the Debian repositories.

## 9. Participate in the package usage survey

If Debian asks whether you want to participate in the package popularity contest:

- Select **No** if you do not want to send anonymous package usage statistics.
- This choice does not affect LivingroomOS.

## 10. Select the software to install

This is an important step.

The Debian installer displays a software selection screen, usually called **Software selection** or **tasksel**.

For LivingroomOS, select exactly these two options:

- [x] SSH server
- [x] standard system utilities

Make sure that all other options are disabled, especially:

- Debian desktop environment
- GNOME
- KDE Plasma
- Xfce
- Cinnamon
- MATE
- LXDE
- LXQt
- Web server
- Print server

LivingroomOS provides its own graphical interface, so a traditional desktop environment is not required.

Use the space bar to toggle selections. Before continuing, verify that only the two required options are selected.

Then select **Continue**.

## 11. Install the bootloader

When asked to install the GRUB bootloader:

- Select **Yes**.
- Install GRUB to the main boot drive.
- On a typical UEFI installation, allow the installer to configure the EFI bootloader automatically.

For example, the target disk might be `/dev/sda` or `/dev/nvme0n1`. The actual device name depends on the hardware.

Do not select an individual Linux partition as the bootloader target when the installer expects the whole disk.

## 12. Finish the installation

Once the installer reports that the installation is complete:

1. Remove the installation USB drive when requested.
2. Select **Continue** to reboot.
3. Allow the PC to boot from its internal drive.

You should now see a minimal Debian installation without a graphical desktop environment.

Log in using the regular user account created during installation.

## 13. Verify the base installation

After logging in, verify the architecture:

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

Check that SSH is installed and running:

```bash
sudo systemctl status ssh
```

Check that the system has network connectivity:

```bash
ping -c 3 deb.debian.org
```

Update the installed packages:

```bash
sudo apt update
sudo apt full-upgrade -y
```

Reboot if required:

```bash
sudo reboot
```

At this point, the Debian base installation is ready for the LivingroomOS installation steps in [INSTALL.md](INSTALL.md).

---

## Important security note

The SSH server allows remote access to the machine. Make sure the regular user has a strong password and that SSH is not exposed to the public internet without appropriate security measures.

For additional security, SSH key authentication is recommended. Once key-based access has been tested successfully, password-based SSH authentication can be disabled if appropriate.

Do not disable all administrative access before verifying that another working administration method is available.
