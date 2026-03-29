# Adrive

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Platform](https://img.shields.io/badge/Platform-Void_Linux-black?style=for-the-badge&logo=linux&logoColor=white)](https://voidlinux.org/)
[![NVIDIA](https://img.shields.io/badge/NVIDIA-Drivers-76B900?style=for-the-badge&logo=nvidia&logoColor=white)](https://www.nvidia.com/)
[![Status](https://img.shields.io/badge/Status-Production--Ready-green?style=for-the-badge)](https://github.com/)

**ADrive** is a professional-grade CLI utility designed to automate NVIDIA proprietary driver management on **Void Linux**. It eliminates the manual hassle of hardware detection, kernel header synchronization, and dracut configuration.

##  Key Features

* **Smart GPU Detection**: Identifies GPU architecture (Fermi, Kepler, or Modern) via hex-range PCI ID matching.
* **Atomic Rollback**: Uses JSON-based manifests to restore your system to its exact previous state if an installation fails.
* **Safety Guards**: Pre-flight checks for `XBPS` locks, `/boot` space availability, and active X11/Wayland sessions.
* **Kernel Sync**: Automatically resolves and installs the correct `headers` for your specific kernel (LTS or Current).
* **System Integrity**: Handles `nouveau` blacklisting and `dracut` initramfs rebuilding automatically.

---

##  Quick Start

Ensure you have root privileges before running the script:

```bash
chmod +x adrive.py
sudo ./adrive.py install
```
# Commands Overview

**Command	Description**
install	Full cycle: backup, driver installation, config setup, and initramfs rebuild.
uninstall	Complete removal of drivers and atomic restoration of original configs.
status	Dashboard: GPU info, driver version, and kernel module load status.
fix	Rebuilds DKMS modules and refreshes initramfs after kernel updates.
# Options
--dry-run: Simulate all actions without modifying the filesystem.

--force: Bypass safety warnings (disk space, network, or active sessions).

# Backup System
Backups are stored in /root/adrive-backups/. Each snapshot includes:

manifest.json: Metadata, package lists, and original file mappings.

Physical copies of /etc/dracut.conf.d/, /etc/modprobe.d/, and X11 configs.

# Logging
All operations and detailed stderr error messages are recorded for auditing:
 /var/log/adrive.log

# License
Distributed under the MIT License. See LICENSE for more information
