#!/usr/bin/env python3
import argparse, subprocess, os, sys, re, shutil, datetime, json, signal, socket

VERSION = "1.0"
LOG_FILE = "/var/log/adrive.log"
XBPS_LOCK = "/var/db/xbps/.lock"

class BackupManager:
    def __init__(self, log_func):
        self.log = log_func
        self.root_dir = "/root/adrive-backups"
        self.targets = [
            "/etc/dracut.conf.d/nvidia.conf", 
            "/etc/modprobe.d/blacklist-nouveau.conf", 
            "/etc/X11/xorg.conf.d/10-nvidia.conf"
        ]

    def create(self, installed_pkgs, dry_run=False):
        if dry_run: return
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        path = os.path.join(self.root_dir, f"backup_{ts}")
        os.makedirs(path, exist_ok=True)
        manifest = {
            "files": {}, 
            "packages": installed_pkgs, 
            "version": VERSION,
            "date": str(datetime.datetime.now())
        }
        for t in self.targets:
            if os.path.exists(t):
                fname = os.path.basename(t)
                shutil.copy2(t, os.path.join(path, fname))
                manifest["files"][fname] = t
        with open(os.path.join(path, "manifest.json"), "w") as f:
            json.dump(manifest, f, indent=4)
        self.log(f"System state backed up to {path}", "+")

    def get_latest_valid(self):
        if not os.path.exists(self.root_dir): return None
        for d in sorted(os.listdir(self.root_dir), reverse=True):
            p = os.path.join(self.root_dir, d)
            if os.path.exists(os.path.join(p, "manifest.json")): return p
        return None

class ADrive:
    def __init__(self, args):
        self.args = args
        self.is_root = os.geteuid() == 0
        self.backup = BackupManager(self.log)
        # Корректная обработка сигналов
        signal.signal(signal.SIGINT, self._sig_handler)

    def _sig_handler(self, s, f):
        print("\n")
        self.log("Interrupted by user. Cleaning up...", "!")
        sys.exit(130)

    def log(self, message, status="*"):
        icons = {"*": "[*]", "!": "[!]", "+": "[+]", "DONE": "[>]"}
        msg = f"{icons.get(status, '[*]')} {message}"
        print(msg)
        if self.is_root and not self.args.dry_run:
            try:
                with open(LOG_FILE, "a") as f:
                    f.write(f"{datetime.datetime.now()} | {msg}\n")
            except: pass

    def check_env(self):
        if not self.is_root and not self.args.dry_run:
            self.log("Root privileges required!", "!")
            return False
        
        # Проверка блокировки XBPS
        if os.path.exists(XBPS_LOCK):
            self.log("XBPS database is locked. Another update might be running.", "!")
            if not self.args.force: return False

        # Проверка свободного места
        stat = shutil.disk_usage("/boot")
        free_mb = stat.free // 1048576
        if free_mb < 120:
            self.log(f"Low space in /boot: {free_mb}MB. Need 120MB+.", "!")
            if not self.args.force: return False

        # Проверка интернета
        self.log("Checking repository connection...", "*")
        try:
            socket.create_connection(("alpha.de.repo.voidlinux.org", 80), timeout=5)
        except:
            self.log("Network unreachable. XBPS will fail.", "!")
            if not self.args.force: return False

        # Проверка графической сессии
        env = os.environ
        if env.get("DISPLAY") or env.get("WAYLAND_DISPLAY") or env.get("XDG_SESSION_TYPE"):
            self.log("Graphical session active. Switch to TTY for safety.", "!")
            if not self.args.force: return False
            
        return True

    def get_gpu_info(self):
        """Продвинутое определение NVIDIA по PCI ID диапазонам"""
        try:
            out = subprocess.check_output("lspci -nn | grep -i nvidia", shell=True).decode()
            match = re.search(r'10de:([0-9a-fA-F]{4})', out)
            if not match: return "NVIDIA GPU", "nvidia"
            
            dev_id = match.group(1).lower()
            val = int(dev_id, 16)
            
            # Kepler (470xx): 0fc0-0fff, 1180-11ff, 1280-12ff
            if (0x0fc0 <= val <= 0x0fff) or (0x1180 <= val <= 0x11ff) or (0x1280 <= val <= 0x12ff):
                return f"NVIDIA (ID:{dev_id} Kepler)", "nvidia470"
            # Fermi (390xx): 0dc0-0dff, 0e20-0eff, 1080-10ff
            if (0x0dc0 <= val <= 0x0dff) or (0x0e20 <= val <= 0x0eff) or (0x1080 <= val <= 0x10ff):
                return f"NVIDIA (ID:{dev_id} Fermi)", "nvidia390"
                
            return f"NVIDIA (ID:{dev_id} Modern)", "nvidia"
        except:
            return "Generic NVIDIA", "nvidia"

    def get_nvidia_packages(self):
        """Унифицированный парсинг установленных пакетов"""
        output = subprocess.getoutput("xbps-query -l")
        return [l.split()[1] for l in output.split('\n') if 'nvidia' in l and l.startswith('ii')]

    def run_cmd(self, cmd):
        if self.args.dry_run:
            self.log(f"Simulating: {' '.join(cmd)}", "*")
            return True
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            self.log(f"Fail: {res.stderr.strip()}", "!")
            return False
        return True

    def install(self):
        if not self.check_env(): return
        
        model, ver = self.get_gpu_info()
        self.log(f"Detected {model}. Target driver: {ver}", "+")
        
        # Создаем бэкап текущего состояния
        self.backup.create(self.get_nvidia_packages(), self.args.dry_run)
        
        # Формируем список пакетов
        k_rel = os.uname().release
        h = "linux-lts-headers" if "lts" in k_rel else "linux-headers"
        pkgs = [h, f"{ver}-dkms", "nvidia-settings"]
        pkgs.append("nvidia-libs-32bit" if ver=="nvidia" else f"lib{ver}-libs-32bit")
        
        self.log("Starting installation steps...", "*")
        if self.run_cmd(["xbps-install", "-Sy", "void-repo-nonfree", "void-repo-multilib"]) and \
           self.run_cmd(["xbps-install", "-y"] + pkgs):
            
            if not self.args.dry_run:
                os.makedirs("/etc/dracut.conf.d", exist_ok=True)
                with open("/etc/dracut.conf.d/nvidia.conf", "w") as f:
                    f.write('omit_drivers+=" nouveau "\n')
                os.makedirs("/etc/modprobe.d", exist_ok=True)
                with open("/etc/modprobe.d/blacklist-nouveau.conf", "w") as f:
                    f.write("blacklist nouveau\noptions nouveau modeset=0\n")
                
                if shutil.which("Xorg"):
                    os.makedirs("/etc/X11/xorg.conf.d", exist_ok=True)
                    with open("/etc/X11/xorg.conf.d/10-nvidia.conf", "w") as f:
                        f.write('Section "Device"\n  Identifier "NvidiaCard"\n  Driver "nvidia"\nEndSection\n')

            self.run_cmd(["dracut", "--force"])
            self.log("Installation complete. Reboot to apply.", "DONE")
        else:
            self.log("Critical installation error. Attempting rollback...", "!")
            self.uninstall()

    def uninstall(self):
        self.log("Executing atomic removal...", "*")
        pkgs = self.get_nvidia_packages()
        if pkgs:
            self.run_cmd(["xbps-remove", "-Ry"] + pkgs)
        
        latest = self.backup.get_latest_valid()
        if latest:
            with open(os.path.join(latest, "manifest.json"), "r") as f:
                m = json.load(f)
                for fn, orig_path in m["files"].items():
                    src = os.path.join(latest, fn)
                    if os.path.exists(src):
                        os.makedirs(os.path.dirname(orig_path), exist_ok=True)
                        shutil.copy2(src, orig_path)
                        self.log(f"Restored: {orig_path}", "+")
        else:
            self.log("No valid backup found to restore configs.", "!")

        self.run_cmd(["dracut", "--force"])
        self.log("Uninstall process finished.", "DONE")

    def status(self):
        model, _ = self.get_gpu_info()
        self.log(f"ADrive v{VERSION} | GPU: {model}")
        
        pkgs = self.get_nvidia_packages()
        self.log(f"Installed Packages: {', '.join(pkgs) if pkgs else 'None'}")
        
        mod_status = subprocess.getoutput("lsmod")
        mod_loaded = "nvidia" in mod_status
        self.log(f"NVIDIA Module: {'LOADED' if mod_loaded else 'NOT LOADED'}", "+" if mod_loaded else "!")
        
        if shutil.which("nvidia-smi"):
            try:
                ver = subprocess.check_output(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"], text=True).strip()
                self.log(f"Driver Version: {ver}", "+")
            except: pass
        
        stat = shutil.disk_usage("/boot")
        self.log(f"Boot space: {stat.free // 1048576}MB free")

def main():
    parser = argparse.ArgumentParser(
        description=f"ADrive v{VERSION}: Professional NVIDIA Driver Manager for Void Linux",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Commands:\n  install    Detect GPU, backup configs, and install drivers\n"
               "  uninstall  Remove drivers and restore configs from latest backup\n"
               "  status     Show GPU info, driver version, and module status\n"
               "  fix        Rebuild DKMS modules and initramfs"
    )
    parser.add_argument('--dry-run', action='store_true', help='Simulate actions without making changes')
    parser.add_argument('--force', action='store_true', help='Ignore warnings (space, internet, session)')
    parser.add_argument('command', nargs='?', choices=['install', 'uninstall', 'status', 'fix'], help='Command to execute')

    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return

    app = ADrive(args)
    
    if args.command == 'install': app.install()
    elif args.command == 'uninstall': app.uninstall()
    elif args.command == 'status': app.status()
    elif args.command == 'fix':
        if shutil.which("dkms"):
            if app.run_cmd(["dkms", "autoinstall"]):
                app.run_cmd(["dracut", "--force"])
                app.log("Fix complete.", "DONE")
        else:
            app.log("DKMS not found. Install it first.", "!")

if __name__ == "__main__":
    main()
