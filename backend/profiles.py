"""
Cross-Platform Profile Manager for PrismaRGB.
Saves and loads 2D spatial device positions, effect settings, and color palettes.
"""

import json
import os
import platform
from typing import Dict, List

from backend.hardware_manager import HardwareManager
from backend.shader_engine import ShaderEngine


class ProfileManager:
    def __init__(self, project_root: str) -> None:
        self.project_root = project_root
        if platform.system().lower() == "windows":
            base = os.environ.get("APPDATA", os.path.expanduser("~"))
            self.config_dir = os.path.join(base, "PrismaRGB")
        else:
            self.config_dir = os.path.expanduser("~/.config/PrismaRGB")
        self.profiles_dir = os.path.join(self.config_dir, "profiles")
        os.makedirs(self.profiles_dir, exist_ok=True)
        self._ensure_default_profiles()

    def _ensure_default_profiles(self) -> None:
        defaults = {
            "Static Ice White": {
                "effect": "static_solid",
                "palette": "Arctic Ice",
                "custom_colors": [[235, 248, 255], [0, 240, 255], [140, 225, 255], [0, 120, 255]],
                "speed": 1.0,
                "scale": 1.0,
                "angle_deg": 0.0,
                "global_brightness": 240,
            },
            "2-Color Cyan & Magenta": {
                "effect": "static_dual",
                "palette": "Cyberpunk Neon",
                "custom_colors": [[0, 240, 255], [255, 0, 128], [255, 215, 0], [120, 0, 255]],
                "speed": 1.0,
                "scale": 1.2,
                "angle_deg": 35.0,
                "global_brightness": 245,
            },
            "Aurora Borealis": {
                "effect": "aurora",
                "palette": "Aurora Borealis",
                "speed": 1.15,
                "scale": 1.35,
                "angle_deg": 35.0,
                "global_brightness": 240,
            },
            "Cyberpunk Plasma": {
                "effect": "cyberpunk_plasma",
                "palette": "Cyberpunk Neon",
                "speed": 1.35,
                "scale": 1.50,
                "angle_deg": 45.0,
                "global_brightness": 255,
            },
            "Thermal Indicator": {
                "effect": "thermal_core",
                "palette": "Inferno Lava",
                "speed": 1.0,
                "scale": 1.0,
                "angle_deg": 0.0,
                "global_brightness": 235,
            },
        }
        for name, data in defaults.items():
            path = self._profile_path(name)
            if not os.path.exists(path):
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)

    def _profile_path(self, name: str) -> str:
        safe = "".join(c if c.isalnum() or c in " _-+()" else "_" for c in name).strip()
        return os.path.join(self.profiles_dir, f"{safe}.json")

    def list_profiles(self) -> List[str]:
        names: List[str] = []
        for fn in sorted(os.listdir(self.profiles_dir)):
            if fn.endswith(".json"):
                names.append(fn[:-5])
        return names

    def save_profile(
        self,
        name: str,
        hw: HardwareManager,
        shader: ShaderEngine,
    ) -> str:
        payload: Dict[str, object] = {
            "effect": shader.active_effect,
            "palette": shader.active_palette,
            "custom_colors": shader.custom_colors,
            "multicolor_style": shader.multicolor_style,
            "num_active_stops": shader.num_active_stops,
            "speed": shader.speed,
            "scale": shader.scale,
            "angle_deg": shader.angle_deg,
            "global_brightness": hw.global_brightness,
            "devices": {
                dev.device_id: {
                    "x": dev.x,
                    "y": dev.y,
                    "width": dev.width,
                    "height": dev.height,
                    "enabled": dev.enabled,
                    "brightness": dev.brightness,
                }
                for dev in hw.devices
            },
        }
        path = self._profile_path(name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return path

    def load_profile(
        self,
        name: str,
        hw: HardwareManager,
        shader: ShaderEngine,
    ) -> bool:
        path = self._profile_path(name)
        if not os.path.exists(path):
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            shader.active_effect = str(data.get("effect", shader.active_effect))
            pal = str(data.get("palette", shader.active_palette))
            shader.set_palette(pal)
            if "custom_colors" in data and isinstance(data["custom_colors"], list):
                shader.custom_colors = [
                    (int(c[0]), int(c[1]), int(c[2])) for c in data["custom_colors"] if len(c) == 3
                ]
            shader.speed = float(data.get("speed", shader.speed))
            shader.scale = float(data.get("scale", shader.scale))
            shader.angle_deg = float(data.get("angle_deg", shader.angle_deg))
            shader.multicolor_style = str(data.get("multicolor_style", shader.multicolor_style))
            shader.num_active_stops = int(data.get("num_active_stops", shader.num_active_stops))
            hw.global_brightness = int(data.get("global_brightness", hw.global_brightness))

            dev_map = data.get("devices", {})
            if isinstance(dev_map, dict):
                for dev in hw.devices:
                    if dev.device_id in dev_map:
                        dcfg = dev_map[dev.device_id]
                        dev.x = float(dcfg.get("x", dev.x))
                        dev.y = float(dcfg.get("y", dev.y))
                        dev.width = float(dcfg.get("width", dev.width))
                        dev.height = float(dcfg.get("height", dev.height))
                        dev.enabled = bool(dcfg.get("enabled", dev.enabled))
                        dev.brightness = int(dcfg.get("brightness", dev.brightness))
            return True
        except Exception:
            return False
