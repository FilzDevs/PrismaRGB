# PrismaRGB

Modern 2D RGB lighting control and hardware monitoring suite built with Python and PySide6 (Qt6).

**Repository:** [https://github.com/FilzDevs/PrismaRGB](https://github.com/FilzDevs/PrismaRGB)

I built PrismaRGB because existing RGB tools on Linux like OpenRGB have a dated, cluttered interface and lack a clean 2D spatial layout or quick per-device brightness controls. PrismaRGB uses the OpenRGB SDK protocol (plus direct Linux I2C/SMBus access where needed) under the hood, wrapped in a streamlined, modern interface.

---

## Platform Support

- **Linux (Primary Platform):** Developed and tested on Linux — stable with no known bugs.
- **Windows (Experimental):** A portable Windows `.exe` build is also generated and supported via the OpenRGB SDK bridge, though it has not yet been extensively tested on Windows systems.

---

## Features

### Lighting & Effects
- **2D Spatial Canvas:** Drag, drop, and resize all detected RGB devices (motherboard, RAM modules, GPU, keyboard, mouse, ARGB strips) on a live 2D field so gradients and waves flow naturally across your physical setup.
- **Context-Aware Inspector:** The right-hand panel only displays the color pickers and sliders that the active effect actually uses:
  - **1-Color Effects** (*Static Color*, *Soft Pulse*): Shows a single color picker and quick-preset swatches without unnecessary extra controls.
  - **2-Color Effects** (*2-Color Gradient*, *Dual Wave*): Shows two color slots and direction/speed controls.
  - **Multi-Color Effects** (*Static Multi-Color*, *Aurora Borealis*, *Plasma Field*, *Galaxy Vortex*, *Color Wave*): Choose between 2, 3, or 4 active colors. Static Multi-Color supports smooth gradients, hard color blocks, radial gradients, or assigning a dedicated static color to each device.
  - **Automatic Effects** (*Rainbow Spectrum*, *Thermal Indicator*): Automatically computes full-spectrum rainbow waves or live CPU/GPU temperature gradients (Blue → Green → Red).
- **Per-Device Brightness:** Every detected RGB device has its own enable toggle and independent `0%–100%` brightness slider right below the 2D canvas, alongside the master brightness slider.
- **Profiles & System Tray:** Save custom profiles as JSON and launch minimized to the system tray using `--minimized`.

### System Monitoring
- **Dedicated Monitoring Tab:** Automatically detects your hardware and sensors without hardcoded device names:
  - **Circular Arc Gauges** for CPU temperature & clock speed, GPU temperature & power/VRAM usage, RAM utilization, and motherboard / NVMe SSD temperatures.
  - **Live 60-Second Rolling Area Charts** for CPU & GPU temperatures (`°C`) and utilization (`%`).
  - **Per-Thread CPU Bars** and system fan RPM readouts.

---

## Installation & Usage

### Option 1: Prebuilt Releases (Recommended)
Download the latest build from the **[Releases](https://github.com/FilzDevs/PrismaRGB/releases)** page:

- **Linux (`PrismaRGB-Linux-x86_64.AppImage`):**
  ```bash
  chmod +x PrismaRGB-Linux-x86_64.AppImage
  ./PrismaRGB-Linux-x86_64.AppImage
  ```
- **Windows (`PrismaRGB-Windows-x64.exe`):**
  Download and run `PrismaRGB-Windows-x64.exe`.

*(Note: Make sure `OpenRGB` is installed on your system so PrismaRGB can automatically start and connect to the background SDK bridge for USB HID and SMBus controllers.)*

### Option 2: Run from Source
Requirements: Python 3.10+, `PySide6`, `psutil`.

```bash
git clone https://github.com/FilzDevs/PrismaRGB.git
cd PrismaRGB
pip install -r requirements.txt
python3 main.py
```

Command-line flags:
```bash
# Print detected RGB controllers and hardware sensors as JSON
python3 main.py --diagnose

# Start minimized in the system tray
python3 main.py --minimized

# Load a specific profile on startup
python3 main.py --profile "Aurora Borealis"
```

---

## Troubleshooting: DDR5 RAM Not Detected on Linux (AM5 / B650 / X670)?

On many modern AMD motherboards (such as Gigabyte B650/X670), the BIOS reserves the SMBus port range `0x0B00–0x0B0F` via ACPI (`ACPI Warning: SystemIO range 0x0B00-0x0B08 conflicts with OpRegion`). By default, the Linux kernel blocks the `i2c-piix4` SMBus driver from binding, which prevents DDR5 RAM RGB controllers (e.g. Corsair Vengeance RGB DDR5) from appearing.

**Fix:** Add the kernel parameter `acpi_enforce_resources=lax` (on Fedora Atomic / Bazzite: `rpm-ostree kargs --append=acpi_enforce_resources=lax`; on standard distributions: add it to `GRUB_CMDLINE_LINUX_DEFAULT` in `/etc/default/grub`) and reboot. Once the `/dev/i2c-*` SMBus adapters are available, both RAM sticks will be detected automatically.

---

## License & Notes

Released under the [MIT License](LICENSE). This is an independent open-source project and is not affiliated with OpenRGB, Fractal Design, or any hardware manufacturer.

*Development note: The development of this project was assisted by AI tools.*
