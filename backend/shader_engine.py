"""
60 FPS 2D Spatial Canvas Shader Engine for PrismaRGB.
Hardware-agnostic effect evaluator with strict per-effect color & parameter metadata:
- "single": Effect uses exactly 1 color (e.g., Static Color, Soft Pulse)
- "dual": Effect uses exactly 2 colors (e.g., 2-Color Gradient, Dual Wave)
- "multi": Effect uses 2–4 colors or a preset palette (e.g., Static Multi-Color, Aurora, Plasma)
- "auto": Effect calculates its colors automatically (e.g., Rainbow Spectrum, Thermal Indicator)
"""

import colorsys
import math
import time
from typing import Any, Dict, List, Tuple

from backend.hardware_manager import RGBDevice
from backend.telemetry import SystemMetrics


PALETTES: Dict[str, List[Tuple[int, int, int]]] = {
    "Cyberpunk Neon": [(0, 240, 255), (255, 0, 85), (255, 230, 0), (120, 0, 255)],
    "Arctic Ice": [(230, 248, 255), (0, 212, 255), (0, 88, 255), (140, 230, 255)],
    "Neon Magenta": [(255, 0, 127), (123, 44, 191), (0, 180, 216), (255, 80, 200)],
    "Aurora Borealis": [(0, 255, 136), (0, 180, 216), (114, 9, 183), (0, 255, 200)],
    "Synthwave Sunset": [(255, 0, 127), (255, 109, 0), (114, 9, 183), (20, 0, 70)],
    "Matrix Green": [(0, 255, 65), (170, 255, 0), (0, 95, 25), (0, 35, 10)],
    "Inferno Lava": [(255, 245, 120), (255, 90, 0), (200, 0, 0), (65, 0, 0)],
    "Deep Ocean": [(0, 245, 212), (0, 119, 182), (3, 4, 94), (0, 180, 216)],
    "Royal Gold": [(255, 215, 0), (157, 78, 221), (40, 0, 80), (255, 160, 0)],
    "Pastel Dream": [(255, 120, 195), (120, 215, 255), (210, 160, 255), (255, 180, 220)],
}


EFFECT_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "static_solid",
        "name": "Static Color",
        "category": "Static",
        "desc": "Solid single-color lighting across your entire setup.",
        "color_mode": "single",
        "has_speed": False,
        "has_angle": False,
        "has_style": False,
    },
    {
        "id": "static_dual",
        "name": "2-Color Gradient",
        "category": "Static",
        "desc": "Smooth static gradient between two custom colors.",
        "color_mode": "dual",
        "has_speed": False,
        "has_angle": True,
        "has_style": False,
    },
    {
        "id": "static_multicolor",
        "name": "Static Multi-Color",
        "category": "Static",
        "desc": "Static multi-color lighting (gradient, color blocks, radial, or per-device split).",
        "color_mode": "multi",
        "has_speed": False,
        "has_angle": True,
        "has_style": True,
    },
    {
        "id": "breathing_single",
        "name": "Soft Pulse",
        "category": "Animated",
        "desc": "Gentle breathing animation using a single selected color.",
        "color_mode": "single",
        "has_speed": True,
        "has_angle": False,
        "has_style": False,
    },
    {
        "id": "dual_pulse",
        "name": "Dual Wave",
        "category": "Animated",
        "desc": "Flowing directional wave oscillating between two chosen colors.",
        "color_mode": "dual",
        "has_speed": True,
        "has_angle": True,
        "has_style": False,
    },
    {
        "id": "aurora",
        "name": "Aurora Borealis",
        "category": "Animated",
        "desc": "Organic northern-lights waves flowing across the 2D canvas.",
        "color_mode": "multi",
        "has_speed": True,
        "has_angle": False,
        "has_style": False,
    },
    {
        "id": "cyberpunk_plasma",
        "name": "Plasma Field",
        "category": "Animated",
        "desc": "Smooth multi-layered 2D interference plasma.",
        "color_mode": "multi",
        "has_speed": True,
        "has_angle": False,
        "has_style": False,
    },
    {
        "id": "spiral_vortex",
        "name": "Galaxy Vortex",
        "category": "Animated",
        "desc": "Rotating spiral vortex radiating from the center of the 2D space.",
        "color_mode": "multi",
        "has_speed": True,
        "has_angle": False,
        "has_style": False,
    },
    {
        "id": "rainbow_wave",
        "name": "Color Wave",
        "category": "Animated",
        "desc": "Angle-adjustable color wave using your selected palette stops.",
        "color_mode": "multi",
        "has_speed": True,
        "has_angle": True,
        "has_style": False,
    },
    {
        "id": "spectrum_cycle",
        "name": "Rainbow Spectrum",
        "category": "Automatic",
        "desc": "Classic full-spectrum rainbow wave across all devices.",
        "color_mode": "auto",
        "has_speed": True,
        "has_angle": True,
        "has_style": False,
    },
    {
        "id": "thermal_core",
        "name": "Thermal Indicator",
        "category": "Automatic",
        "desc": "Automatically maps live CPU & GPU temperatures to color (Blue -> Green -> Red).",
        "color_mode": "auto",
        "has_speed": False,
        "has_angle": False,
        "has_style": False,
    },
]

EFFECT_BY_ID: Dict[str, Dict[str, Any]] = {item["id"]: item for item in EFFECT_CATALOG}


class ShaderEngine:
    def __init__(self) -> None:
        self.active_effect: str = "static_solid"
        self.active_palette: str = "Cyberpunk Neon"
        self.custom_colors: List[Tuple[int, int, int]] = [
            (0, 240, 255),
            (255, 0, 128),
            (255, 215, 0),
            (120, 0, 255),
        ]
        self.num_active_stops: int = 4
        self.multicolor_style: str = "Smooth Gradient"
        self.speed: float = 1.0
        self.scale: float = 1.25
        self.angle_deg: float = 35.0
        self._start_time: float = time.time()

    def get_active_effect_meta(self) -> Dict[str, Any]:
        return EFFECT_BY_ID.get(self.active_effect, EFFECT_CATALOG[0])

    def set_palette(self, palette_name: str) -> None:
        self.active_palette = palette_name
        if palette_name in PALETTES:
            self.custom_colors = list(PALETTES[palette_name])

    def _effective_stops(self) -> List[Tuple[int, int, int]]:
        meta = self.get_active_effect_meta()
        cmode = meta.get("color_mode", "multi")
        stops = self.custom_colors if self.custom_colors else [(0, 240, 255)]
        while len(stops) < 4:
            stops.append(stops[-1])
        if cmode == "single":
            return stops[:1]
        if cmode == "dual":
            return stops[:2]
        cnt = max(2, min(4, self.num_active_stops))
        return stops[:cnt]

    def sample_palette(self, t: float, hard_steps: bool = False) -> Tuple[int, int, int]:
        stops = self._effective_stops()
        n = len(stops)
        if n == 1:
            return stops[0]
        if hard_steps:
            idx = int(math.floor((t % 1.0) * n)) % n
            return stops[idx]
        pos = (t % 1.0) * n
        idx0 = int(math.floor(pos)) % n
        idx1 = (idx0 + 1) % n
        frac = pos - math.floor(pos)
        frac = frac * frac * (3.0 - 2.0 * frac)
        c0 = stops[idx0]
        c1 = stops[idx1]
        return (
            int(c0[0] + (c1[0] - c0[0]) * frac),
            int(c0[1] + (c1[1] - c0[1]) * frac),
            int(c0[2] + (c1[2] - c0[2]) * frac),
        )

    def sample_linear_clamped(self, t: float, hard_steps: bool = False) -> Tuple[int, int, int]:
        stops = self._effective_stops()
        n = len(stops)
        if n == 1:
            return stops[0]
        t_clamped = max(0.0, min(0.9999, t))
        if hard_steps:
            idx = int(t_clamped * n)
            return stops[min(n - 1, idx)]
        pos = t_clamped * (n - 1)
        idx0 = int(math.floor(pos))
        idx1 = min(n - 1, idx0 + 1)
        frac = pos - idx0
        frac = frac * frac * (3.0 - 2.0 * frac)
        c0 = stops[idx0]
        c1 = stops[idx1]
        return (
            int(c0[0] + (c1[0] - c0[0]) * frac),
            int(c0[1] + (c1[1] - c0[1]) * frac),
            int(c0[2] + (c1[2] - c0[2]) * frac),
        )

    def evaluate_point(
        self,
        wx: float,
        wy: float,
        t: float,
        metrics: SystemMetrics,
        dev_idx: int = 0,
    ) -> Tuple[int, int, int]:
        eff = self.active_effect
        sc = self.scale

        if eff == "static_solid":
            return self.custom_colors[0] if self.custom_colors else (0, 240, 255)

        if eff == "static_dual":
            rad = math.radians(self.angle_deg)
            proj = ((wx - 0.5) * math.cos(rad) + (wy - 0.5) * math.sin(rad)) * sc + 0.5
            return self.sample_linear_clamped(proj, hard_steps=False)

        if eff == "static_multicolor":
            stops = self._effective_stops()
            style = self.multicolor_style
            if style == "Per-Device Split":
                return stops[dev_idx % len(stops)]
            if style == "Radial Center":
                dx = (wx - 0.5) * sc
                dy = (wy - 0.5) * sc
                dist = math.sqrt(dx * dx + dy * dy) * 1.45
                return self.sample_linear_clamped(dist, hard_steps=False)
            rad = math.radians(self.angle_deg)
            proj = ((wx - 0.5) * math.cos(rad) + (wy - 0.5) * math.sin(rad)) * sc + 0.5
            return self.sample_linear_clamped(proj, hard_steps=(style == "Hard Blocks"))

        if eff == "breathing_single":
            r, g, b = self.custom_colors[0] if self.custom_colors else (0, 240, 255)
            pulse = 0.18 + 0.82 * (0.5 + 0.5 * math.sin(t * 2.0))
            return int(r * pulse), int(g * pulse), int(b * pulse)

        if eff == "dual_pulse":
            rad = math.radians(self.angle_deg)
            proj = (wx * math.cos(rad) + wy * math.sin(rad)) * sc
            wave = 0.5 + 0.5 * math.sin(proj * 4.0 - t * 2.2)
            return self.sample_linear_clamped(wave, hard_steps=False)

        if eff == "aurora":
            w1 = math.sin(wx * 4.5 * sc + t * 1.3) * 0.5 + 0.5
            w2 = math.cos(wy * 3.8 * sc - t * 0.9 + math.sin(wx * 3.0 + t)) * 0.5 + 0.5
            curtain = math.sin((wx * 2.5 + wy * 1.5) * sc + t * 0.7) * 0.5 + 0.5
            v = w1 * 0.45 + w2 * 0.35 + curtain * 0.20
            return self.sample_palette(v + t * 0.08)

        if eff == "cyberpunk_plasma":
            v1 = math.sin(wx * 6.0 * sc + t * 1.5)
            v2 = math.sin((wx * math.cos(t * 0.4) + wy * math.sin(t * 0.3)) * 6.5 * sc + t)
            cx = wx - 0.5 + 0.25 * math.sin(t * 0.5)
            cy = wy - 0.5 + 0.25 * math.cos(t * 0.7)
            v3 = math.sin(math.sqrt(cx * cx + cy * cy + 0.01) * 9.0 * sc - t * 1.8)
            norm_v = (v1 + v2 + v3) / 6.0 + 0.5
            return self.sample_palette(norm_v)

        if eff == "spiral_vortex":
            dx = wx - 0.5
            dy = wy - 0.5
            dist = math.sqrt(dx * dx + dy * dy)
            ang = math.atan2(dy, dx) / (2.0 * math.pi)
            spiral = (ang * 2.0 + dist * 2.2 * sc - t * 0.45) % 1.0
            return self.sample_palette(spiral)

        if eff == "rainbow_wave":
            rad = math.radians(self.angle_deg)
            proj = (wx * math.cos(rad) + wy * math.sin(rad)) * sc
            val = (proj * 0.85 - t * 0.35) % 1.0
            return self.sample_palette(val)

        if eff == "spectrum_cycle":
            rad = math.radians(self.angle_deg)
            proj = (wx * math.cos(rad) + wy * math.sin(rad)) * sc
            hue = (proj * 0.65 - t * 0.25) % 1.0
            fr, fg, fb = colorsys.hsv_to_rgb(hue, 0.95, 1.0)
            return int(fr * 255), int(fg * 255), int(fb * 255)

        if eff == "thermal_core":
            temp = metrics.cpu_temp * (1.0 - wx) + metrics.gpu_temp * wx
            norm_temp = max(0.0, min(1.0, (temp - 35.0) / 50.0))
            hue = (1.0 - norm_temp) * 0.60
            fr, fg, fb = colorsys.hsv_to_rgb(hue, 0.95, 1.0)
            return int(fr * 255), int(fg * 255), int(fb * 255)

        return self.sample_palette((wx + wy + t * 0.2) % 1.0)

    def render_devices(self, devices: List[RGBDevice], metrics: SystemMetrics) -> None:
        t = (time.time() - self._start_time) * self.speed
        for d_idx, dev in enumerate(devices):
            if not dev.enabled:
                continue
            for led in dev.leds:
                wx = max(0.0, min(1.0, dev.x + led.rel_x * dev.width))
                wy = max(0.0, min(1.0, dev.y + led.rel_y * dev.height))
                r, g, b = self.evaluate_point(wx, wy, t, metrics, dev_idx=d_idx)
                led.r = r
                led.g = g
                led.b = b
