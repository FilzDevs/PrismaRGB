"""
Cross-Platform Hardware-Agnostic RGB Hardware Manager for PrismaRGB.
Automatically discovers and controls RGB hardware on Linux and Windows via:
1. OpenRGB SDK Binary Protocol (127.0.0.1:6742) — auto-discovers Motherboards,
   RAM modules, GPUs, Keyboards, Mice, Coolers, Fans, and ARGB Strips.
2. Direct Linux I2C SMBus Driver for AMDGPU OEM 0x28 RGB controllers.
"""

import ctypes
from dataclasses import dataclass, field
import glob
import math
import os
import platform
import shutil
import socket
import struct
import subprocess
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore


I2C_SLAVE = 0x0703
I2C_SMBUS = 0x0720
I2C_SMBUS_WRITE = 0
I2C_SMBUS_READ = 1
I2C_SMBUS_BYTE_DATA = 2


class _I2CSmbusData(ctypes.Union):
    _fields_ = [
        ("byte", ctypes.c_uint8),
        ("word", ctypes.c_uint16),
        ("block", ctypes.c_uint8 * 34),
    ]


class _I2CSmbusIoctlData(ctypes.Structure):
    _fields_ = [
        ("read_write", ctypes.c_uint8),
        ("command", ctypes.c_uint8),
        ("size", ctypes.c_uint32),
        ("data", ctypes.POINTER(_I2CSmbusData)),
    ]


@dataclass
class LEDPoint:
    index: int
    label: str
    rel_x: float
    rel_y: float
    zone: str = "Main"
    r: int = 0
    g: int = 220
    b: int = 255


@dataclass
class RGBDevice:
    device_id: str
    name: str
    vendor: str
    category: str
    bus_info: str
    driver_type: str
    x: float
    y: float
    width: float
    height: float
    rotation: float = 0.0
    enabled: bool = True
    connected: bool = True
    status_note: str = "Active"
    channel_order: str = "RGB"
    brightness: int = 255
    sdk_indices: List[int] = field(default_factory=list)
    leds: List[LEDPoint] = field(default_factory=list)


class DirectAMDGPU0x28Driver:
    """
    Native Linux I2C SMBus driver for AMDGPU OEM 0x28 RGB controllers.
    No-op on Windows where OpenRGB SDK handles GPU control.
    """

    REG_EXTERNAL_CONTROL = 0x0F
    REG_MODE = 0x10
    REG_BRIGHTNESS = 0x16
    REG_RED = 0x1A
    REG_GREEN = 0x1B
    REG_BLUE = 0x1C
    MODE_CUSTOM_RGB = 0x06

    def __init__(self, address: int = 0x28) -> None:
        self.address = address
        self.bus_path: Optional[str] = self._find_bus(address) if fcntl is not None else None
        self._fd: Optional[int] = None
        self._last_rgb: Tuple[int, int, int, int] = (-1, -1, -1, -1)
        self._last_write_time: float = 0.0
        self._lock = threading.Lock()
        self.open_device()

    def _find_bus(self, addr: int) -> Optional[str]:
        if fcntl is None:
            return None
        for name_file in sorted(glob.glob("/sys/bus/i2c/devices/i2c-*/name")):
            try:
                with open(name_file, "r", encoding="utf-8") as f:
                    bname = f.read().strip()
                if "AMDGPU" in bname:
                    bdev = "/dev/" + os.path.basename(os.path.dirname(name_file))
                    if self._probe_addr(bdev, addr):
                        return bdev
            except OSError:
                continue
        return None

    @staticmethod
    def _probe_addr(dev_path: str, addr: int) -> bool:
        if fcntl is None or not os.path.exists(dev_path):
            return False
        try:
            fd = os.open(dev_path, os.O_RDWR)
            fcntl.ioctl(fd, I2C_SLAVE, addr)
            data = _I2CSmbusData()
            args = _I2CSmbusIoctlData(I2C_SMBUS_READ, 0x10, I2C_SMBUS_BYTE_DATA, ctypes.pointer(data))
            fcntl.ioctl(fd, I2C_SMBUS, args)
            os.close(fd)
            return True
        except Exception:
            return False

    def open_device(self) -> bool:
        if fcntl is None:
            return False
        with self._lock:
            if self._fd is not None:
                return True
            if not self.bus_path or not os.path.exists(self.bus_path):
                return False
            try:
                self._fd = os.open(self.bus_path, os.O_RDWR)
                fcntl.ioctl(self._fd, I2C_SLAVE, self.address)
                return True
            except OSError:
                self._fd = None
                return False

    def _write_reg_unlocked(self, reg: int, val: int) -> bool:
        if fcntl is None or self._fd is None:
            return False
        data = _I2CSmbusData()
        data.byte = val & 0xFF
        args = _I2CSmbusIoctlData(I2C_SMBUS_WRITE, reg & 0xFF, I2C_SMBUS_BYTE_DATA, ctypes.pointer(data))
        try:
            fcntl.ioctl(self._fd, I2C_SMBUS, args)
            return True
        except OSError:
            return False

    def update_color(self, r: int, g: int, b: int, brightness: int = 255) -> bool:
        if not self.bus_path:
            return False
        now = time.time()
        if now - self._last_write_time < 0.032:
            return True
        target = (r & 0xFF, g & 0xFF, b & 0xFF, brightness & 0xFF)
        if target == self._last_rgb:
            return True

        with self._lock:
            if self._fd is None and not self.open_device():
                return False
            if self._last_rgb == (-1, -1, -1, -1):
                self._write_reg_unlocked(self.REG_EXTERNAL_CONTROL, 0x00)
                self._write_reg_unlocked(self.REG_MODE, self.MODE_CUSTOM_RGB)
            if target[3] != self._last_rgb[3]:
                self._write_reg_unlocked(self.REG_BRIGHTNESS, target[3])
            self._write_reg_unlocked(self.REG_RED, target[0])
            self._write_reg_unlocked(self.REG_GREEN, target[1])
            self._write_reg_unlocked(self.REG_BLUE, target[2])
            self._last_rgb = target
            self._last_write_time = now
            return True


class OpenRGBSDKBridge:
    """
    Binary TCP client for the OpenRGB SDK Protocol (port 6742).
    Works identically on Linux and Windows.
    """

    MAGIC = b"ORGB"
    NET_PACKET_ID_REQUEST_CONTROLLER_COUNT = 0
    NET_PACKET_ID_REQUEST_CONTROLLER_DATA = 1
    NET_PACKET_ID_SET_CLIENT_NAME = 50
    NET_PACKET_ID_DEVICE_LIST_UPDATED = 100
    NET_PACKET_ID_RGBCONTROLLER_UPDATELEDS = 1050
    NET_PACKET_ID_RGBCONTROLLER_SetCustomMode = 1100
    NET_PACKET_ID_RGBCONTROLLER_UPDATEMODE = 1101

    DEV_TYPE_MAP = {
        0: "motherboard",
        1: "ram",
        2: "gpu",
        3: "cooler",
        4: "lightstrip",
        5: "keyboard",
        6: "mouse",
        7: "mousemat",
        8: "headset",
        9: "headset_stand",
        10: "gamepad",
        11: "light",
        12: "speaker",
    }

    def __init__(self, project_root: str, host: str = "127.0.0.1", port: int = 6742) -> None:
        self.project_root = project_root
        self.host = host
        self.port = port
        self.sock: Optional[socket.socket] = None
        self.connected = False
        self.controller_count = 0
        self.controller_meta: List[Dict[str, object]] = []
        self._lock = threading.Lock()
        self._server_proc: Optional[subprocess.Popen] = None
        self._last_sdk_push: float = 0.0

    def connect(self) -> bool:
        with self._lock:
            if self.connected and self.sock is not None and self.controller_count > 0:
                return True
            try:
                if self.sock is not None:
                    try:
                        self.sock.close()
                    except Exception:
                        pass
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1.5)
                s.connect((self.host, self.port))
                self.sock = s
                self.connected = True
                self.controller_meta.clear()

                self._send_packet_unlocked(0, self.NET_PACKET_ID_SET_CLIENT_NAME, b"PrismaRGB\x00")
                self._send_packet_unlocked(0, self.NET_PACKET_ID_REQUEST_CONTROLLER_COUNT, b"")
                _, _, payload = self._recv_packet_unlocked()
                if len(payload) >= 4:
                    self.controller_count = struct.unpack("<I", payload[:4])[0]

                for idx in range(self.controller_count):
                    self._send_packet_unlocked(idx, self.NET_PACKET_ID_REQUEST_CONTROLLER_DATA, b"")
                    _, _, cdata = self._recv_packet_unlocked()
                    meta, direct_pkt = self._parse_controller_data_v0(idx, cdata)
                    self.controller_meta.append(meta)
                    self._send_packet_unlocked(idx, self.NET_PACKET_ID_RGBCONTROLLER_SetCustomMode, b"")
                    if direct_pkt is not None:
                        self._send_packet_unlocked(idx, self.NET_PACKET_ID_RGBCONTROLLER_UPDATEMODE, direct_pkt)
                return self.controller_count > 0
            except Exception:
                self.sock = None
                self.connected = False
                return False

    @classmethod
    def _parse_controller_data_v0(cls, idx: int, cdata: bytes) -> Tuple[Dict[str, object], Optional[bytes]]:
        fallback = {
            "index": idx,
            "name": f"RGB Controller #{idx + 1}",
            "description": "",
            "location": "",
            "category": "other",
            "num_leds": 1,
        }
        if len(cdata) < 16:
            return fallback, None
        try:
            _data_size, dev_type_id = struct.unpack_from("<Ii", cdata, 0)
            offset = 8

            def read_str(o: int) -> Tuple[str, int]:
                slen = struct.unpack_from("<H", cdata, o)[0]
                text = cdata[o + 2 : o + 2 + max(0, slen - 1)].decode("utf-8", errors="replace")
                return text, o + 2 + slen

            name, offset = read_str(offset)
            desc, offset = read_str(offset)
            _ver, offset = read_str(offset)
            _serial, offset = read_str(offset)
            loc, offset = read_str(offset)

            num_modes, _active_mode = struct.unpack_from("<Hi", cdata, offset)
            offset += 6

            direct_mode_pkt: Optional[bytes] = None
            for m_idx in range(num_modes):
                m_start = offset
                mname, offset = read_str(offset)
                (
                    _mval,
                    _mflags,
                    _mspd_min,
                    _mspd_max,
                    _mcol_min,
                    _mcol_max,
                    _mspd,
                    _mdir,
                    _mcmode,
                    num_mcols,
                ) = struct.unpack_from("<iIIIIIIIIH", cdata, offset)
                offset += 9 * 4 + 2 + num_mcols * 4
                m_end = offset
                if mname == "Direct" or (mname == "Static" and direct_mode_pkt is None):
                    raw_m = cdata[m_start:m_end]
                    direct_mode_pkt = struct.pack("<Ii", 8 + len(raw_m), m_idx) + raw_m

            num_zones = struct.unpack_from("<H", cdata, offset)[0]
            offset += 2
            for _ in range(num_zones):
                _zname, offset = read_str(offset)
                _ztype, _zmin, _zmax, _zcnt, zmat_len = struct.unpack_from("<iIIIH", cdata, offset)
                offset += 16 + 2 + zmat_len

            num_leds = struct.unpack_from("<H", cdata, offset)[0]
            category = cls.DEV_TYPE_MAP.get(dev_type_id, "other")
            return (
                {
                    "index": idx,
                    "name": name.strip() or f"RGB Device #{idx + 1}",
                    "description": desc.strip(),
                    "location": loc.strip(),
                    "category": category,
                    "num_leds": max(1, num_leds),
                },
                direct_mode_pkt,
            )
        except Exception:
            return fallback, None

    def _find_openrgb_binary(self) -> Optional[str]:
        if platform.system().lower() == "windows":
            win_candidates = [
                os.path.join(self.project_root, "native", "OpenRGB.exe"),
                shutil.which("OpenRGB.exe") or "",
                shutil.which("openrgb") or "",
                r"C:\Program Files\OpenRGB\OpenRGB.exe",
                r"C:\Program Files (x86)\OpenRGB\OpenRGB.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\OpenRGB\OpenRGB.exe"),
            ]
            for c in win_candidates:
                if c and os.path.exists(c):
                    return c
            return None

        bundled = os.path.join(self.project_root, "native", "openrgb-bridge.AppImage")
        if os.path.exists(bundled):
            return bundled
        sys_bin = shutil.which("openrgb")
        if sys_bin:
            return sys_bin
        for pattern in (
            "~/Downloads/OpenRGB*.AppImage",
            "~/.local/bin/OpenRGB*.AppImage",
            "~/.cache/ujust/appimages/OpenRGB*.AppImage",
        ):
            matches = sorted(glob.glob(os.path.expanduser(pattern)))
            if matches:
                return matches[-1]
        return None

    def start_headless_server_if_available(self) -> bool:
        if self.connect() and self.controller_count > 0:
            return True

        binary = self._find_openrgb_binary()
        if not binary:
            return False
        try:
            if self._server_proc is None or self._server_proc.poll() is not None:
                kwargs: Dict[str, object] = {
                    "stdout": subprocess.DEVNULL,
                    "stderr": subprocess.DEVNULL,
                }
                if platform.system().lower() != "windows":
                    kwargs["close_fds"] = True
                self._server_proc = subprocess.Popen(
                    [binary, "--server", "--server-port", str(self.port), "--noautoconnect"],
                    **kwargs,  # type: ignore
                )
                time.sleep(2.6)
            for _ in range(8):
                if self.connect() and self.controller_count > 0:
                    return True
                time.sleep(0.45)
            return self.connected
        except Exception:
            return False

    def stop(self) -> None:
        with self._lock:
            if self.sock is not None:
                try:
                    self.sock.close()
                except Exception:
                    pass
                self.sock = None
            self.connected = False
            if self._server_proc is not None:
                try:
                    self._server_proc.terminate()
                except Exception:
                    pass
                self._server_proc = None

    def update_controller_leds(self, dev_idx: int, rgb_list: List[Tuple[int, int, int]]) -> bool:
        if not self.connected or self.sock is None:
            return False
        with self._lock:
            try:
                num_leds = len(rgb_list)
                data_len = 4 + 2 + (num_leds * 4)
                buf = bytearray(data_len)
                struct.pack_into("<IH", buf, 0, data_len, num_leds)
                offset = 6
                for r, g, b in rgb_list:
                    buf[offset] = r & 0xFF
                    buf[offset + 1] = g & 0xFF
                    buf[offset + 2] = b & 0xFF
                    buf[offset + 3] = 0x00
                    offset += 4
                self._send_packet_unlocked(dev_idx, self.NET_PACKET_ID_RGBCONTROLLER_UPDATELEDS, bytes(buf))
                return True
            except Exception:
                self.connected = False
                self.sock = None
                return False

    def _send_packet_unlocked(self, dev_idx: int, pkt_id: int, payload: bytes) -> None:
        if self.sock is None:
            return
        header = struct.pack("<4sIII", self.MAGIC, dev_idx, pkt_id, len(payload))
        self.sock.sendall(header + payload)

    def _recv_packet_unlocked(self) -> Tuple[int, int, bytes]:
        if self.sock is None:
            return 0, 0, b""
        while True:
            hdr = self._recv_exact(16)
            if len(hdr) < 16:
                return 0, 0, b""
            _, dev_idx, pkt_id, pkt_size = struct.unpack("<4sIII", hdr)
            payload = self._recv_exact(pkt_size) if pkt_size > 0 else b""
            if pkt_id == self.NET_PACKET_ID_DEVICE_LIST_UPDATED:
                continue
            return dev_idx, pkt_id, payload

    def _recv_exact(self, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n and self.sock is not None:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                break
            buf.extend(chunk)
        return bytes(buf)


class HardwareManager:
    """
    Cross-platform hardware-agnostic RGB device manager.
    Automatically builds its device topology from whatever RGB controllers
    are connected to the system, and streams 60 FPS color frames to them.
    """

    def __init__(self, project_root: str) -> None:
        self.project_root = project_root
        self.devices: List[RGBDevice] = []
        self.amdgpu_i2c_driver = DirectAMDGPU0x28Driver(0x28)
        self.sdk_bridge = OpenRGBSDKBridge(project_root)
        self.live_output_enabled: bool = True
        self.global_brightness: int = 230
        self.on_devices_updated: Optional[Callable[[], None]] = None
        self._lock = threading.Lock()

        if self.amdgpu_i2c_driver.bus_path:
            self.devices.append(
                self._create_device_entry(
                    device_id="gpu_i2c_0x28",
                    name="AMD Radeon GPU",
                    vendor="Direct I2C (0x28)",
                    category="gpu",
                    bus_info=f"{self.amdgpu_i2c_driver.bus_path} @ 0x28",
                    driver_type="Direct I2C",
                    num_leds=16,
                    sdk_indices=[],
                    slot_idx=0,
                )
            )

    @staticmethod
    def _generate_led_points(category: str, num_leds: int) -> List[LEDPoint]:
        leds: List[LEDPoint] = []
        if category == "keyboard" and num_leds >= 40:
            rows = 6
            cols = max(10, int(math.ceil(num_leds / rows)))
            for i in range(num_leds):
                r = i // cols
                c = i % cols
                rx = 0.05 + (c / max(1, cols - 1)) * 0.90
                ry = 0.12 + (r / max(1, rows - 1)) * 0.76
                leds.append(LEDPoint(index=i, label=f"LED {i + 1}", rel_x=rx, rel_y=ry))
            return leds

        if category == "motherboard" and num_leds >= 12:
            for i in range(num_leds):
                t = i / max(1, num_leds)
                if t < 0.35:
                    rx = 0.08 + (t / 0.35) * 0.84
                    ry = 0.10
                elif t < 0.65:
                    rx = 0.92
                    ry = 0.12 + ((t - 0.35) / 0.30) * 0.76
                else:
                    rx = 0.92 - ((t - 0.65) / 0.35) * 0.84
                    ry = 0.90
                leds.append(LEDPoint(index=i, label=f"LED {i + 1}", rel_x=rx, rel_y=ry))
            return leds

        if category in ("ram", "mouse"):
            count = max(2, num_leds)
            for i in range(count):
                ry = 0.12 + (i / max(1, count - 1)) * 0.76
                leds.append(LEDPoint(index=i, label=f"LED {i + 1}", rel_x=0.5, rel_y=ry))
            return leds

        count = max(8 if category == "gpu" else 1, num_leds)
        for i in range(count):
            rx = 0.08 + (i / max(1, count - 1)) * 0.84 if count > 1 else 0.5
            leds.append(LEDPoint(index=i, label=f"LED {i + 1}", rel_x=rx, rel_y=0.5))
        return leds

    def _default_box_for_category(self, category: str, slot_idx: int) -> Tuple[float, float, float, float]:
        if category == "motherboard":
            return (0.05, 0.08, 0.38, 0.50)
        if category == "ram":
            col = slot_idx % 4
            return (0.47 + col * 0.08, 0.08, 0.065, 0.34)
        if category == "gpu":
            return (0.47, 0.46, 0.36, 0.13)
        if category == "keyboard":
            return (0.08, 0.64, 0.56, 0.28)
        if category == "mouse":
            return (0.68, 0.66, 0.11, 0.24)
        col = slot_idx % 3
        row = slot_idx // 3
        return (0.10 + col * 0.28, 0.12 + row * 0.25, 0.24, 0.18)

    def _create_device_entry(
        self,
        device_id: str,
        name: str,
        vendor: str,
        category: str,
        bus_info: str,
        driver_type: str,
        num_leds: int,
        sdk_indices: List[int],
        slot_idx: int,
    ) -> RGBDevice:
        x, y, w, h = self._default_box_for_category(category, slot_idx)
        leds = self._generate_led_points(category, num_leds)
        return RGBDevice(
            device_id=device_id,
            name=name,
            vendor=vendor,
            category=category,
            bus_info=bus_info,
            driver_type=driver_type,
            x=x,
            y=y,
            width=w,
            height=h,
            sdk_indices=sdk_indices,
            leds=leds,
        )

    def sync_devices_from_bridge(self) -> None:
        if not self.sdk_bridge.connected or not self.sdk_bridge.controller_meta:
            return

        with self._lock:
            old_state = {
                d.device_id: (d.enabled, d.brightness, d.x, d.y, d.width, d.height)
                for d in self.devices
            }
            new_devices: List[RGBDevice] = []
            category_counts: Dict[str, int] = {}
            name_counts: Dict[str, int] = {}

            grouped_meta: List[Dict[str, object]] = []
            for meta in self.sdk_bridge.controller_meta:
                cname = str(meta["name"])
                cat = str(meta["category"])
                if cat == "mouse":
                    existing = next((g for g in grouped_meta if g["name"] == cname and g["category"] == "mouse"), None)
                    if existing is not None:
                        indices = list(existing["sdk_indices"])  # type: ignore
                        indices.append(int(meta["index"]))
                        existing["sdk_indices"] = indices
                        existing["num_leds"] = max(int(existing["num_leds"]), int(meta["num_leds"]))
                        continue
                grouped_meta.append(
                    {
                        "name": cname,
                        "description": str(meta.get("description", "")),
                        "location": str(meta.get("location", "")),
                        "category": cat,
                        "num_leds": int(meta.get("num_leds", 1)),
                        "sdk_indices": [int(meta["index"])],
                    }
                )

            total_by_name: Dict[str, int] = {}
            for g in grouped_meta:
                nm = str(g["name"])
                total_by_name[nm] = total_by_name.get(nm, 0) + 1

            for g in grouped_meta:
                raw_name = str(g["name"])
                cat = str(g["category"])
                slot = category_counts.get(cat, 0)
                category_counts[cat] = slot + 1

                occ = name_counts.get(raw_name, 0) + 1
                name_counts[raw_name] = occ
                display_name = f"{raw_name} #{occ}" if total_by_name.get(raw_name, 1) > 1 else raw_name
                dev_id = f"{cat}_{raw_name.lower().replace(' ', '_')}_{occ}"

                dev = self._create_device_entry(
                    device_id=dev_id,
                    name=display_name,
                    vendor=str(g["description"]) or cat.upper(),
                    category=cat,
                    bus_info=str(g["location"]),
                    driver_type="OpenRGB SDK",
                    num_leds=int(g["num_leds"]),
                    sdk_indices=list(g["sdk_indices"]),  # type: ignore
                    slot_idx=slot,
                )
                if dev_id in old_state:
                    en, br, ox, oy, ow, oh = old_state[dev_id]
                    dev.enabled = en
                    dev.brightness = br
                    dev.x, dev.y, dev.width, dev.height = ox, oy, ow, oh
                new_devices.append(dev)

            self.devices = new_devices

        if self.on_devices_updated is not None:
            self.on_devices_updated()

    def push_frame_to_hardware(self) -> None:
        if not self.live_output_enabled:
            return

        scale = self.global_brightness / 255.0

        for dev in self.devices:
            if not dev.leds:
                continue
            dev_scale = (scale * (dev.brightness / 255.0)) if dev.enabled else 0.0

            if dev.category == "gpu" and self.amdgpu_i2c_driver.bus_path:
                mid = dev.leds[len(dev.leds) // 2]
                r = int(mid.r * dev_scale)
                g = int(mid.g * dev_scale)
                b = int(mid.b * dev_scale)
                self.amdgpu_i2c_driver.update_color(r, g, b, brightness=int(255 * dev_scale))

        now = time.time()
        if self.sdk_bridge.connected and (now - self.sdk_bridge._last_sdk_push) >= 0.032:
            self.sdk_bridge._last_sdk_push = now
            meta_by_idx = {int(m["index"]): m for m in self.sdk_bridge.controller_meta}
            for dev in self.devices:
                if not dev.sdk_indices or not dev.leds:
                    continue
                dev_scale = (scale * (dev.brightness / 255.0)) if dev.enabled else 0.0
                base_rgb = [
                    (int(led.r * dev_scale), int(led.g * dev_scale), int(led.b * dev_scale))
                    for led in dev.leds
                ]
                for c_idx in dev.sdk_indices:
                    meta = meta_by_idx.get(c_idx)
                    if not meta:
                        continue
                    expected_leds = int(meta.get("num_leds", 1))
                    if expected_leds == 1:
                        mid = base_rgb[len(base_rgb) // 2]
                        rgb_list = [mid]
                    elif len(base_rgb) < expected_leds:
                        rgb_list = base_rgb + [base_rgb[-1]] * (expected_leds - len(base_rgb))
                    else:
                        rgb_list = base_rgb[:expected_leds]
                    self.sdk_bridge.update_controller_leds(c_idx, rgb_list)
