"""
Main Window for PrismaRGB.
Cross-platform RGB Control & System Monitoring Suite with a clean 2-Tab UI
and direct GitHub integration (https://github.com/FilzDevs/PrismaRGB).
"""

import threading
from typing import List

from PySide6.QtCore import QMetaObject, Qt, QTimer, QUrl, Slot
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QSlider,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from backend.hardware_manager import HardwareManager
from backend.profiles import ProfileManager
from backend.shader_engine import ShaderEngine
from backend.telemetry import TelemetryEngine
from ui.canvas_widget import CanvasStudioTab
from ui.monitoring_widget import SystemMonitoringTab
from ui.theme import DARK_STUDIO_STYLESHEET


GITHUB_REPO_URL = "https://github.com/FilzDevs/PrismaRGB"


class PrismaRGBMainWindow(QMainWindow):
    def __init__(self, project_root: str) -> None:
        super().__init__()
        self.project_root = project_root
        self.setWindowTitle("PrismaRGB — RGB Lighting & Hardware Monitoring")
        self.resize(1340, 840)
        self.setStyleSheet(DARK_STUDIO_STYLESHEET)

        self.telemetry = TelemetryEngine()
        self.hw = HardwareManager(project_root)
        self.shader = ShaderEngine()
        self.profiles = ProfileManager(project_root)

        self._nav_buttons: List[QPushButton] = []
        self._blackout_active: bool = False
        self._saved_brightness: int = self.hw.global_brightness

        self._setup_icon_and_tray()
        self._build_ui()

        self.hw.on_devices_updated = lambda: QMetaObject.invokeMethod(
            self, "_on_hardware_topology_changed", Qt.ConnectionType.QueuedConnection
        )

        QTimer.singleShot(250, self._async_init_bridge)

        self.render_timer = QTimer(self)
        self.render_timer.timeout.connect(self._on_frame_tick)
        self.render_timer.start(16)

    def _create_app_icon(self) -> QIcon:
        pix = QPixmap(64, 64)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setBrush(QColor(0, 240, 255))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(6, 6, 52, 52)
        p.setBrush(QColor(255, 0, 127))
        p.drawEllipse(16, 16, 32, 32)
        p.setBrush(QColor(10, 14, 26))
        p.drawEllipse(24, 24, 16, 16)
        p.end()
        return QIcon(pix)

    def _setup_icon_and_tray(self) -> None:
        icon = self._create_app_icon()
        self.setWindowIcon(icon)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(icon, self)
            self.tray.setToolTip("PrismaRGB")
            menu = QMenu()
            act_show = QAction("Open PrismaRGB", self)
            act_show.triggered.connect(self.showNormal)
            menu.addAction(act_show)

            act_solid = QAction("Effect: Static Color", self)
            act_solid.triggered.connect(lambda: self.canvas_tab.select_effect("static_solid"))
            menu.addAction(act_solid)

            act_aurora = QAction("Effect: Aurora Borealis", self)
            act_aurora.triggered.connect(lambda: self.canvas_tab.select_effect("aurora"))
            menu.addAction(act_aurora)

            act_therm = QAction("Effect: Thermal Indicator", self)
            act_therm.triggered.connect(lambda: self.canvas_tab.select_effect("thermal_core"))
            menu.addAction(act_therm)

            menu.addSeparator()
            act_gh = QAction("GitHub (FilzDevs/PrismaRGB)", self)
            act_gh.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(GITHUB_REPO_URL)))
            menu.addAction(act_gh)

            act_quit = QAction("Quit", self)
            act_quit.triggered.connect(self.close)
            menu.addAction(act_quit)
            self.tray.setContextMenu(menu)
            self.tray.show()

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("RootWidget")
        self.setCentralWidget(root)
        main_vbox = QVBoxLayout(root)
        main_vbox.setContentsMargins(0, 0, 0, 0)
        main_vbox.setSpacing(0)

        # 1. Top Header Bar
        topbar = QFrame()
        topbar.setObjectName("TopBar")
        topbar.setFixedHeight(62)
        tb_layout = QHBoxLayout(topbar)
        tb_layout.setContentsMargins(18, 8, 18, 8)
        tb_layout.setSpacing(12)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        lbl_title = QLabel("PRISMARGB")
        lbl_title.setObjectName("TitleLabel")
        lbl_sub = QLabel("2D RGB Lighting & System Monitoring Suite")
        lbl_sub.setObjectName("SubtitleLabel")
        title_col.addWidget(lbl_title)
        title_col.addWidget(lbl_sub)
        tb_layout.addLayout(title_col)

        tb_layout.addStretch()

        self.lbl_cpu = QLabel("CPU: --°C")
        self.lbl_cpu.setObjectName("MetricBadge")
        tb_layout.addWidget(self.lbl_cpu)

        self.lbl_gpu = QLabel("GPU: --°C")
        self.lbl_gpu.setObjectName("MetricBadge")
        tb_layout.addWidget(self.lbl_gpu)

        self.lbl_ram = QLabel("RAM: --%")
        self.lbl_ram.setObjectName("MetricBadge")
        tb_layout.addWidget(self.lbl_ram)

        tb_layout.addSpacing(8)

        tb_layout.addWidget(QLabel("Profile:"))
        self.combo_profiles = QComboBox()
        self.combo_profiles.setMinimumWidth(175)
        self._reload_profile_combo()
        self.combo_profiles.currentTextChanged.connect(self._on_profile_selected)
        tb_layout.addWidget(self.combo_profiles)

        btn_save_prof = QPushButton("Save")
        btn_save_prof.clicked.connect(self._on_save_profile)
        tb_layout.addWidget(btn_save_prof)

        tb_layout.addWidget(QLabel("Brightness:"))
        self.sld_global_br = QSlider(Qt.Orientation.Horizontal)
        self.sld_global_br.setRange(0, 255)
        self.sld_global_br.setValue(self.hw.global_brightness)
        self.sld_global_br.setFixedWidth(100)
        self.sld_global_br.valueChanged.connect(self._on_global_brightness)
        tb_layout.addWidget(self.sld_global_br)

        self.btn_blackout = QPushButton("LEDs Off")
        self.btn_blackout.setObjectName("DangerButton")
        self.btn_blackout.clicked.connect(self._toggle_blackout)
        tb_layout.addWidget(self.btn_blackout)

        main_vbox.addWidget(topbar)

        # 2. Body: Left Sidebar + 2-Tab Stacked Workspace
        body_hbox = QHBoxLayout()
        body_hbox.setContentsMargins(0, 0, 0, 0)
        body_hbox.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(235)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(12, 16, 12, 16)
        sb_layout.setSpacing(8)

        nav_items = [
            ("Lighting & Effects", 0),
            ("System Monitoring", 1),
        ]
        for label, idx in nav_items:
            nbtn = QPushButton(label)
            nbtn.setObjectName("NavButton")
            nbtn.clicked.connect(lambda checked=False, i=idx: self._switch_tab(i))
            self._nav_buttons.append(nbtn)
            sb_layout.addWidget(nbtn)

        sb_layout.addStretch()

        status_box = QFrame()
        status_box.setObjectName("Card")
        self.st_layout = QVBoxLayout(status_box)
        self.st_layout.setContentsMargins(12, 10, 12, 10)
        self.st_layout.setSpacing(5)

        lbl_hw_hdr = QLabel("Detected RGB Devices")
        lbl_hw_hdr.setStyleSheet("color: #00F0FF; font-weight: 700; font-size: 12px;")
        self.st_layout.addWidget(lbl_hw_hdr)

        self.hw_list_widget = QWidget()
        self.hw_list_layout = QVBoxLayout(self.hw_list_widget)
        self.hw_list_layout.setContentsMargins(0, 0, 0, 0)
        self.hw_list_layout.setSpacing(4)
        self.st_layout.addWidget(self.hw_list_widget)

        btn_rescan = QPushButton("Rescan Devices")
        btn_rescan.clicked.connect(self._async_init_bridge)
        self.st_layout.addWidget(btn_rescan)

        sb_layout.addWidget(status_box)

        btn_github = QPushButton("GitHub • FilzDevs/PrismaRGB")
        btn_github.setToolTip(GITHUB_REPO_URL)
        btn_github.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(GITHUB_REPO_URL)))
        sb_layout.addWidget(btn_github)

        body_hbox.addWidget(sidebar)

        self.stack = QStackedWidget()
        self.canvas_tab = CanvasStudioTab(self.hw, self.shader, self)
        self.monitoring_tab = SystemMonitoringTab(self.telemetry, self)

        self.stack.addWidget(self.canvas_tab)
        self.stack.addWidget(self.monitoring_tab)

        body_hbox.addWidget(self.stack, 1)
        main_vbox.addLayout(body_hbox, 1)

        self.refresh_sidebar_hardware_status()
        self._switch_tab(0)

    @Slot()
    def _on_hardware_topology_changed(self) -> None:
        self.refresh_sidebar_hardware_status()
        self.canvas_tab.rebuild_device_brightness_list()
        self.canvas_tab.canvas.update()

    def refresh_sidebar_hardware_status(self) -> None:
        while self.hw_list_layout.count():
            item = self.hw_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.hw.devices:
            lbl = QLabel("Scanning RGB controllers…")
            lbl.setStyleSheet("font-size: 11px; color: #8A9BB8;")
            self.hw_list_layout.addWidget(lbl)
            return

        for dev in self.hw.devices:
            short = dev.name if len(dev.name) <= 24 else dev.name[:23] + "…"
            l_item = QLabel(f"<span style='color:#00FF9D;'>●</span> {short}")
            l_item.setToolTip(f"{dev.name}\n{dev.vendor}\n{dev.bus_info}\nLEDs: {len(dev.leds)}")
            l_item.setStyleSheet("font-size: 11px; color: #C5D4EB;")
            self.hw_list_layout.addWidget(l_item)

    def _switch_tab(self, idx: int) -> None:
        self.stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._nav_buttons):
            btn.setProperty("active", "true" if i == idx else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _async_init_bridge(self) -> None:
        def _worker() -> None:
            ok = self.hw.sdk_bridge.start_headless_server_if_available()
            if ok:
                self.hw.sync_devices_from_bridge()

        threading.Thread(target=_worker, daemon=True).start()

    def _reload_profile_combo(self) -> None:
        self.combo_profiles.blockSignals(True)
        self.combo_profiles.clear()
        for name in self.profiles.list_profiles():
            self.combo_profiles.addItem(name)
        self.combo_profiles.blockSignals(False)

    def _on_profile_selected(self, name: str) -> None:
        if not name:
            return
        if self.profiles.load_profile(name, self.hw, self.shader):
            self.sld_global_br.setValue(self.hw.global_brightness)
            self.canvas_tab._update_inspector_visibility()
            self.canvas_tab._refresh_swatches()
            self.canvas_tab.sync_device_sliders()
            self.canvas_tab.canvas.update()

    def _on_save_profile(self) -> None:
        name, ok = QInputDialog.getText(
            self,
            "Save Profile",
            "Profile name:",
            text=self.combo_profiles.currentText() or "My Custom Profile",
        )
        if ok and name.strip():
            self.profiles.save_profile(name.strip(), self.hw, self.shader)
            self._reload_profile_combo()
            self.combo_profiles.setCurrentText(name.strip())

    def _on_global_brightness(self, val: int) -> None:
        self.hw.global_brightness = val
        if val > 0 and self._blackout_active:
            self._blackout_active = False
            self.btn_blackout.setText("LEDs Off")

    def _toggle_blackout(self) -> None:
        if not self._blackout_active:
            self._saved_brightness = max(50, self.hw.global_brightness)
            self._blackout_active = True
            self.sld_global_br.setValue(0)
            self.btn_blackout.setText("LEDs On")
        else:
            self._blackout_active = False
            self.sld_global_br.setValue(self._saved_brightness)
            self.btn_blackout.setText("LEDs Off")

    def _on_frame_tick(self) -> None:
        metrics = self.telemetry.get_metrics(min_interval=0.5)
        self.lbl_cpu.setText(f"CPU: {metrics.cpu_temp:.1f}°C ({int(metrics.cpu_load)}%)")
        self.lbl_gpu.setText(f"GPU: {metrics.gpu_temp:.1f}°C ({int(metrics.gpu_load)}%)")
        self.lbl_ram.setText(f"RAM: {int(metrics.ram_load)}% ({metrics.ram_used_gb:.1f} GB)")

        self.canvas_tab.canvas.metrics = metrics
        self.shader.render_devices(self.hw.devices, metrics)
        self.hw.push_frame_to_hardware()

        cur_idx = self.stack.currentIndex()
        if cur_idx == 0:
            self.canvas_tab.canvas.update()
        elif cur_idx == 1:
            self.monitoring_tab.refresh_metrics(metrics)

    def closeEvent(self, event) -> None:
        self.hw.sdk_bridge.stop()
        super().closeEvent(event)
