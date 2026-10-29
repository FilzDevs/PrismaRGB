#!/usr/bin/env python3
"""
PrismaRGB — Universal RGB Lighting Control & Hardware Monitoring Suite.
Repository: https://github.com/FilzDevs/PrismaRGB
"""

import argparse
import json
import os
import signal
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.hardware_manager import HardwareManager
from backend.telemetry import TelemetryEngine


def run_cli_diagnostics() -> int:
    telemetry = TelemetryEngine()
    hw = HardwareManager(PROJECT_ROOT)
    hw.sdk_bridge.start_headless_server_if_available()
    hw.sync_devices_from_bridge()
    metrics = telemetry.get_metrics(min_interval=0.0)
    summary = {
        "cpu": metrics.cpu_name,
        "gpu": metrics.gpu_name,
        "board": metrics.board_name,
        "cpu_temp_c": metrics.cpu_temp,
        "gpu_temp_c": metrics.gpu_temp,
        "ram_gb": f"{metrics.ram_used_gb:.1f} / {metrics.ram_total_gb:.1f} GB",
        "rgb_devices_detected": [
            {
                "id": d.device_id,
                "name": d.name,
                "category": d.category,
                "bus": d.bus_info,
                "leds": len(d.leds),
            }
            for d in hw.devices
        ],
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    hw.sdk_bridge.stop()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="PrismaRGB — RGB Lighting & Hardware Monitoring Suite")
    parser.add_argument("--diagnose", action="store_true", help="Output detected RGB devices and system sensors as JSON")
    parser.add_argument("--minimized", action="store_true", help="Start minimized in the system tray")
    parser.add_argument("--profile", type=str, default="", help="Load a specific lighting profile on startup")
    args = parser.parse_args()

    if args.diagnose:
        return run_cli_diagnostics()

    from PySide6.QtWidgets import QApplication
    from ui.main_window import PrismaRGBMainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("PrismaRGB")
    app.setOrganizationName("FilzDevs")

    win = PrismaRGBMainWindow(PROJECT_ROOT)
    signal.signal(signal.SIGINT, lambda *_: (win.close(), app.quit()))
    if args.profile:
        win._on_profile_selected(args.profile)

    if args.minimized:
        win.hide()
    else:
        win.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
