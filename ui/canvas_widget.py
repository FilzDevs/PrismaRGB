"""
Clean, Intuitive 2D Spatial RGB Studio Widget for PrismaRGB.
Dynamically adapts the color picker and parameter controls to the exact
requirements of the selected effect (1 color, 2 colors, multi-color, or automatic).
"""

import time
from typing import List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from backend.hardware_manager import HardwareManager, RGBDevice
from backend.shader_engine import EFFECT_CATALOG, PALETTES, ShaderEngine
from backend.telemetry import SystemMetrics


class SpatialFieldCanvas(QWidget):
    deviceSelected = Signal(object)

    def __init__(
        self,
        hw: HardwareManager,
        shader: ShaderEngine,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.hw = hw
        self.shader = shader
        self.metrics = SystemMetrics()
        self.setMinimumSize(580, 420)
        self.setMouseTracking(True)

        self.show_shader_backdrop: bool = True
        self.show_grid: bool = True
        self.show_led_glow: bool = True
        self.selected_device: Optional[RGBDevice] = self.hw.devices[0] if self.hw.devices else None

        self._dragging_device: Optional[RGBDevice] = None
        self._resizing_device: Optional[RGBDevice] = None
        self._drag_offset = QPointF(0.0, 0.0)
        self._bg_image = QImage(64, 40, QImage.Format.Format_RGB32)

    def update_shader_backdrop(self) -> None:
        if not self.show_shader_backdrop:
            return
        w = self._bg_image.width()
        h = self._bg_image.height()
        t = (time.time() - self.shader._start_time) * self.shader.speed
        for py in range(h):
            wy = py / max(1, h - 1)
            for px in range(w):
                wx = px / max(1, w - 1)
                r, g, b = self.shader.evaluate_point(wx, wy, t, self.metrics)
                dr = int(r * 0.34)
                dg = int(g * 0.34)
                db = int(b * 0.34)
                self._bg_image.setPixel(px, py, (0xFF << 24) | (dr << 16) | (dg << 8) | db)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        rect = self.rect()
        cw = float(rect.width())
        ch = float(rect.height())

        if self.show_shader_backdrop:
            self.update_shader_backdrop()
            painter.drawImage(rect, self._bg_image)
        else:
            painter.fillRect(rect, QColor(10, 14, 24))

        if self.show_grid:
            grid_pen = QPen(QColor(255, 255, 255, 18), 1, Qt.PenStyle.DotLine)
            painter.setPen(grid_pen)
            step_x = cw / 10.0
            step_y = ch / 10.0
            for i in range(1, 10):
                painter.drawLine(int(i * step_x), 0, int(i * step_x), int(ch))
                painter.drawLine(0, int(i * step_y), int(cw), int(i * step_y))

        for dev in self.hw.devices:
            dx = dev.x * cw
            dy = dev.y * ch
            dw = dev.width * cw
            dh = dev.height * ch
            drect = QRectF(dx, dy, dw, dh)

            is_sel = dev is self.selected_device

            path = QPainterPath()
            path.addRoundedRect(drect, 10.0, 10.0)
            bg_alpha = 185 if dev.enabled else 90
            painter.fillPath(path, QColor(12, 17, 30, bg_alpha))

            border_col = QColor(0, 240, 255, 235) if is_sel else QColor(80, 110, 160, 150)
            if not dev.enabled:
                border_col = QColor(90, 90, 100, 100)
            painter.setPen(QPen(border_col, 2.0 if is_sel else 1.2))
            painter.drawPath(path)

            painter.setPen(QColor(235, 245, 255) if dev.enabled else QColor(130, 140, 160))
            font = QFont("Inter", 9, QFont.Weight.Bold)
            painter.setFont(font)
            br_pct = int(round((dev.brightness / 255.0) * 100)) if dev.enabled else 0
            title_rect = QRectF(dx + 8, dy + 4, dw - 16, 18)
            painter.drawText(
                title_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                f"{dev.name} ({br_pct}%)",
            )

            dev_scale = (self.hw.global_brightness / 255.0) * (dev.brightness / 255.0)
            led_radius = 4.2 if len(dev.leds) > 45 else (6.0 if len(dev.leds) > 12 else 8.0)
            for led in dev.leds:
                lx = dx + led.rel_x * dw
                ly = dy + led.rel_y * dh
                sr = int(led.r * dev_scale)
                sg = int(led.g * dev_scale)
                sb = int(led.b * dev_scale)
                col = QColor(sr, sg, sb) if dev.enabled else QColor(45, 50, 65)

                if self.show_led_glow and dev.enabled and dev_scale > 0.02:
                    glow = QColor(sr, sg, sb, int(85 * min(1.0, dev_scale + 0.25)))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QBrush(glow))
                    painter.drawEllipse(QPointF(lx, ly), led_radius * 2.1, led_radius * 2.1)

                painter.setPen(QPen(QColor(255, 255, 255, 110), 0.7))
                painter.setBrush(QBrush(col))
                painter.drawEllipse(QPointF(lx, ly), led_radius, led_radius)

            if is_sel:
                handle_rect = QRectF(dx + dw - 12, dy + dh - 12, 10, 10)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0, 240, 255))
                painter.drawRoundedRect(handle_rect, 2.5, 2.5)

        meta = self.shader.get_active_effect_meta()
        painter.setPen(QColor(180, 205, 240, 185))
        painter.setFont(QFont("Inter", 9))
        hud_text = f"Active Mode: {meta['name']}  •  Drag & drop devices to position or resize from bottom-right"
        painter.drawText(QRectF(12, ch - 24, cw - 24, 20), Qt.AlignmentFlag.AlignLeft, hud_text)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        cw = float(self.width())
        ch = float(self.height())

        for dev in reversed(self.hw.devices):
            dx = dev.x * cw
            dy = dev.y * ch
            dw = dev.width * cw
            dh = dev.height * ch
            drect = QRectF(dx, dy, dw, dh)
            resize_rect = QRectF(dx + dw - 16, dy + dh - 16, 16, 16)

            if resize_rect.contains(pos):
                self.selected_device = dev
                self._resizing_device = dev
                self.deviceSelected.emit(dev)
                self.update()
                return
            if drect.contains(pos):
                self.selected_device = dev
                self._dragging_device = dev
                self._drag_offset = QPointF(pos.x() - dx, pos.y() - dy)
                self.deviceSelected.emit(dev)
                self.update()
                return

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        cw = max(1.0, float(self.width()))
        ch = max(1.0, float(self.height()))

        if self._resizing_device is not None:
            dev = self._resizing_device
            new_w = (pos.x() / cw) - dev.x
            new_h = (pos.y() / ch) - dev.y
            dev.width = max(0.05, min(0.95 - dev.x, new_w))
            dev.height = max(0.06, min(0.95 - dev.y, new_h))
            self.update()
        elif self._dragging_device is not None:
            dev = self._dragging_device
            nx = (pos.x() - self._drag_offset.x()) / cw
            ny = (pos.y() - self._drag_offset.y()) / ch
            dev.x = max(0.01, min(0.99 - dev.width, nx))
            dev.y = max(0.01, min(0.99 - dev.height, ny))
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._dragging_device = None
        self._resizing_device = None


class CanvasStudioTab(QWidget):
    def __init__(
        self,
        hw: HardwareManager,
        shader: ShaderEngine,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.hw = hw
        self.shader = shader
        self.canvas = SpatialFieldCanvas(hw, shader, self)
        self._effect_buttons: List[Tuple[str, QPushButton]] = []
        self._swatch_buttons: List[QPushButton] = []
        self._dev_br_sliders: List[Tuple[RGBDevice, QSlider, QLabel, QCheckBox]] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setSpacing(14)

        left_col = QVBoxLayout()
        left_col.setSpacing(10)

        toolbar_card = QFrame()
        toolbar_card.setObjectName("Card")
        tb_layout = QHBoxLayout(toolbar_card)
        tb_layout.setContentsMargins(12, 7, 12, 7)

        chk_backdrop = QCheckBox("Backdrop Preview")
        chk_backdrop.setChecked(True)
        chk_backdrop.toggled.connect(lambda v: setattr(self.canvas, "show_shader_backdrop", v))
        tb_layout.addWidget(chk_backdrop)

        chk_glow = QCheckBox("LED Glow")
        chk_glow.setChecked(True)
        chk_glow.toggled.connect(lambda v: setattr(self.canvas, "show_led_glow", v))
        tb_layout.addWidget(chk_glow)

        tb_layout.addStretch()

        btn_reset_layout = QPushButton("Reset Device Positions")
        btn_reset_layout.clicked.connect(self._reset_positions)
        tb_layout.addWidget(btn_reset_layout)
        left_col.addWidget(toolbar_card)

        canvas_frame = QFrame()
        canvas_frame.setObjectName("Card")
        cf_layout = QVBoxLayout(canvas_frame)
        cf_layout.setContentsMargins(6, 6, 6, 6)
        cf_layout.addWidget(self.canvas, 1)
        left_col.addWidget(canvas_frame, 3)

        dev_card = QFrame()
        dev_card.setObjectName("Card")
        dc_layout = QVBoxLayout(dev_card)
        dc_layout.setContentsMargins(14, 10, 14, 10)
        dc_layout.setSpacing(6)

        lbl_dev_hdr = QLabel("Per-Device Brightness")
        lbl_dev_hdr.setObjectName("SectionHeader")
        dc_layout.addWidget(lbl_dev_hdr)

        self.dev_br_container = QWidget()
        self.dev_br_grid = QGridLayout(self.dev_br_container)
        self.dev_br_grid.setContentsMargins(0, 0, 0, 0)
        self.dev_br_grid.setHorizontalSpacing(14)
        self.dev_br_grid.setVerticalSpacing(6)
        dc_layout.addWidget(self.dev_br_container)

        left_col.addWidget(dev_card)
        root_layout.addLayout(left_col, 3)

        # Right Column: Context-Aware Effect & Color Inspector
        right_panel = QFrame()
        right_panel.setObjectName("Card")
        right_panel.setFixedWidth(390)
        rp_outer = QVBoxLayout(right_panel)
        rp_outer.setContentsMargins(6, 6, 6, 6)

        inspector_scroll = QScrollArea()
        inspector_scroll.setWidgetResizable(True)
        inspector_body = QWidget()
        rp_layout = QVBoxLayout(inspector_body)
        rp_layout.setContentsMargins(10, 10, 10, 10)
        rp_layout.setSpacing(12)

        lbl_eff = QLabel("1. Select Effect")
        lbl_eff.setObjectName("SectionHeader")
        rp_layout.addWidget(lbl_eff)

        eff_grid = QGridLayout()
        eff_grid.setContentsMargins(0, 0, 0, 0)
        eff_grid.setSpacing(6)

        for i, item in enumerate(EFFECT_CATALOG):
            btn = QPushButton(item["name"])
            btn.setToolTip(item["desc"])
            btn.setMinimumHeight(38)
            eff_id = item["id"]
            btn.clicked.connect(lambda checked=False, eid=eff_id: self.select_effect(eid))
            self._effect_buttons.append((eff_id, btn))
            eff_grid.addWidget(btn, i // 2, i % 2)

        rp_layout.addLayout(eff_grid)

        self.lbl_effect_desc = QLabel("")
        self.lbl_effect_desc.setObjectName("SubtitleLabel")
        self.lbl_effect_desc.setWordWrap(True)
        rp_layout.addWidget(self.lbl_effect_desc)

        # 2. Dynamic Color Section
        self.color_section = QFrame()
        self.color_section.setObjectName("AccentCard")
        cs_layout = QVBoxLayout(self.color_section)
        cs_layout.setContentsMargins(12, 10, 12, 10)
        cs_layout.setSpacing(8)

        self.lbl_color_header = QLabel("2. Choose Color")
        self.lbl_color_header.setObjectName("SectionHeader")
        cs_layout.addWidget(self.lbl_color_header)

        self.lbl_auto_color_hint = QLabel("Colors are calculated automatically for this effect.")
        self.lbl_auto_color_hint.setObjectName("SubtitleLabel")
        self.lbl_auto_color_hint.setWordWrap(True)
        cs_layout.addWidget(self.lbl_auto_color_hint)

        self.quick_presets_widget = QWidget()
        preset_grid = QGridLayout(self.quick_presets_widget)
        preset_grid.setContentsMargins(0, 0, 0, 0)
        preset_grid.setSpacing(5)
        quick_presets = [
            ("White", (235, 248, 255)),
            ("Cyan", (0, 240, 255)),
            ("Magenta", (255, 0, 128)),
            ("Green", (0, 255, 135)),
            ("Gold", (255, 185, 0)),
            ("Red", (255, 25, 45)),
            ("Blue", (20, 90, 255)),
            ("Purple", (165, 35, 255)),
        ]
        for p_idx, (p_name, (pr, pg, pb)) in enumerate(quick_presets):
            pbtn = QPushButton(p_name)
            pbtn.setFixedHeight(26)
            tcol = "#050811" if (pr * 0.299 + pg * 0.587 + pb * 0.114) > 145 else "#FFFFFF"
            pbtn.setStyleSheet(
                f"background-color: rgb({pr},{pg},{pb}); color: {tcol}; font-size: 11px; font-weight: 700; border-radius: 5px;"
            )
            pbtn.clicked.connect(lambda checked=False, rgb=(pr, pg, pb): self._apply_quick_color(rgb))
            preset_grid.addWidget(pbtn, p_idx // 4, p_idx % 4)
        cs_layout.addWidget(self.quick_presets_widget)

        self.multi_palette_widget = QWidget()
        mp_layout = QVBoxLayout(self.multi_palette_widget)
        mp_layout.setContentsMargins(0, 0, 0, 0)
        mp_layout.setSpacing(6)

        pal_row = QHBoxLayout()
        pal_row.addWidget(QLabel("Preset:"))
        self.combo_palette = QComboBox()
        for pal_name in PALETTES:
            self.combo_palette.addItem(pal_name)
        self.combo_palette.currentTextChanged.connect(self._on_palette_changed)
        pal_row.addWidget(self.combo_palette, 1)

        self.combo_mc_count = QComboBox()
        for n in (2, 3, 4):
            self.combo_mc_count.addItem(f"{n} Colors", n)
        self.combo_mc_count.setCurrentIndex(2)
        self.combo_mc_count.currentIndexChanged.connect(self._on_mc_count_changed)
        pal_row.addWidget(self.combo_mc_count)
        mp_layout.addLayout(pal_row)
        cs_layout.addWidget(self.multi_palette_widget)

        self.swatches_widget = QWidget()
        swatch_row = QHBoxLayout(self.swatches_widget)
        swatch_row.setContentsMargins(0, 0, 0, 0)
        swatch_row.setSpacing(6)
        for idx in range(4):
            sbtn = QPushButton(f"Color {idx + 1}")
            sbtn.setMinimumHeight(34)
            sbtn.clicked.connect(lambda checked=False, i=idx: self._pick_stop_color(i))
            self._swatch_buttons.append(sbtn)
            swatch_row.addWidget(sbtn)
        cs_layout.addWidget(self.swatches_widget)

        self.mc_style_widget = QWidget()
        mc_row = QHBoxLayout(self.mc_style_widget)
        mc_row.setContentsMargins(0, 0, 0, 0)
        mc_row.addWidget(QLabel("Layout:"))
        self.combo_mc_style = QComboBox()
        self._mc_style_map = {
            "Smooth Gradient": "Smooth Gradient",
            "Hard Color Blocks": "Hard Blocks",
            "Per-Device Color": "Per-Device Split",
            "Radial Center": "Radial Center",
        }
        for label in self._mc_style_map:
            self.combo_mc_style.addItem(label)
        self.combo_mc_style.currentTextChanged.connect(self._on_mc_style_changed)
        mc_row.addWidget(self.combo_mc_style, 1)
        cs_layout.addWidget(self.mc_style_widget)

        rp_layout.addWidget(self.color_section)

        # 3. Dynamic Effect Parameters
        self.params_section = QFrame()
        self.params_section.setObjectName("Card")
        ps_layout = QVBoxLayout(self.params_section)
        ps_layout.setContentsMargins(12, 10, 12, 10)
        ps_layout.setSpacing(8)

        lbl_params = QLabel("3. Effect Settings")
        lbl_params.setObjectName("SectionHeader")
        ps_layout.addWidget(lbl_params)

        self.speed_widget = QWidget()
        sp_l = QVBoxLayout(self.speed_widget)
        sp_l.setContentsMargins(0, 0, 0, 0)
        sp_l.setSpacing(3)
        self.lbl_speed = QLabel(f"Speed: {self.shader.speed:.1f}x")
        sp_l.addWidget(self.lbl_speed)
        sld_speed = QSlider(Qt.Orientation.Horizontal)
        sld_speed.setRange(15, 350)
        sld_speed.setValue(int(self.shader.speed * 100))
        sld_speed.valueChanged.connect(self._on_speed_changed)
        sp_l.addWidget(sld_speed)
        ps_layout.addWidget(self.speed_widget)

        self.angle_widget = QWidget()
        an_l = QVBoxLayout(self.angle_widget)
        an_l.setContentsMargins(0, 0, 0, 0)
        an_l.setSpacing(3)
        self.lbl_angle = QLabel(f"Direction / Angle: {int(self.shader.angle_deg)}°")
        an_l.addWidget(self.lbl_angle)
        sld_angle = QSlider(Qt.Orientation.Horizontal)
        sld_angle.setRange(0, 360)
        sld_angle.setValue(int(self.shader.angle_deg))
        sld_angle.valueChanged.connect(self._on_angle_changed)
        an_l.addWidget(sld_angle)
        ps_layout.addWidget(self.angle_widget)

        rp_layout.addWidget(self.params_section)
        rp_layout.addStretch()

        inspector_scroll.setWidget(inspector_body)
        rp_outer.addWidget(inspector_scroll)
        root_layout.addWidget(right_panel)

        self.rebuild_device_brightness_list()
        self._update_inspector_visibility()
        self._refresh_swatches()

    def rebuild_device_brightness_list(self) -> None:
        while self.dev_br_grid.count():
            item = self.dev_br_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._dev_br_sliders.clear()

        for idx, dev in enumerate(self.hw.devices):
            col_offset = (idx % 2) * 3
            row_idx = idx // 2

            chk_en = QCheckBox(dev.name)
            chk_en.setChecked(dev.enabled)
            sld_d = QSlider(Qt.Orientation.Horizontal)
            sld_d.setRange(0, 255)
            sld_d.setValue(dev.brightness)
            pct = int(round((dev.brightness / 255.0) * 100))
            lbl_pct = QLabel(f"{pct}%")
            lbl_pct.setFixedWidth(38)
            lbl_pct.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            chk_en.toggled.connect(lambda v, d=dev: self._on_dev_enabled_toggled(d, v))
            sld_d.valueChanged.connect(lambda val, d=dev, lp=lbl_pct: self._on_dev_brightness_changed(d, val, lp))

            self.dev_br_grid.addWidget(chk_en, row_idx, col_offset)
            self.dev_br_grid.addWidget(sld_d, row_idx, col_offset + 1)
            self.dev_br_grid.addWidget(lbl_pct, row_idx, col_offset + 2)
            self._dev_br_sliders.append((dev, sld_d, lbl_pct, chk_en))

    def select_effect(self, eff_id: str) -> None:
        self.shader.active_effect = eff_id
        self._update_inspector_visibility()
        self._refresh_swatches()
        self.canvas.update()

    def _update_inspector_visibility(self) -> None:
        for eid, btn in self._effect_buttons:
            if eid == self.shader.active_effect:
                btn.setStyleSheet(
                    "background-color: #162B4D; border: 1.5px solid #00F0FF; color: #00F0FF; font-weight: 700;"
                )
            else:
                btn.setStyleSheet("")

        meta = self.shader.get_active_effect_meta()
        self.lbl_effect_desc.setText(str(meta.get("desc", "")))
        cmode = str(meta.get("color_mode", "multi"))
        has_speed = bool(meta.get("has_speed", False))
        has_angle = bool(meta.get("has_angle", False))
        has_style = bool(meta.get("has_style", False))

        if cmode == "auto":
            self.lbl_color_header.setText("2. Color Control (Automatic)")
            self.lbl_auto_color_hint.setVisible(True)
            self.quick_presets_widget.setVisible(False)
            self.multi_palette_widget.setVisible(False)
            self.swatches_widget.setVisible(False)
            self.mc_style_widget.setVisible(False)
        elif cmode == "single":
            self.lbl_color_header.setText("2. Choose Color (1 Color)")
            self.lbl_auto_color_hint.setVisible(False)
            self.quick_presets_widget.setVisible(True)
            self.multi_palette_widget.setVisible(False)
            self.swatches_widget.setVisible(True)
            self.mc_style_widget.setVisible(False)
            for i, btn in enumerate(self._swatch_buttons):
                btn.setVisible(i == 0)
                if i == 0:
                    btn.setText("Pick Custom Color…")
        elif cmode == "dual":
            self.lbl_color_header.setText("2. Choose Colors (2 Colors)")
            self.lbl_auto_color_hint.setVisible(False)
            self.quick_presets_widget.setVisible(False)
            self.multi_palette_widget.setVisible(False)
            self.swatches_widget.setVisible(True)
            self.mc_style_widget.setVisible(False)
            for i, btn in enumerate(self._swatch_buttons):
                btn.setVisible(i < 2)
                if i < 2:
                    btn.setText(f"Color {i + 1}")
        else:
            cnt = max(2, min(4, self.shader.num_active_stops))
            self.lbl_color_header.setText(f"2. Color Palette ({cnt} Colors)")
            self.lbl_auto_color_hint.setVisible(False)
            self.quick_presets_widget.setVisible(False)
            self.multi_palette_widget.setVisible(True)
            self.swatches_widget.setVisible(True)
            self.mc_style_widget.setVisible(has_style)
            for i, btn in enumerate(self._swatch_buttons):
                btn.setVisible(i < cnt)
                btn.setText(f"Color {i + 1}")

        if has_style and self.shader.multicolor_style in ("Per-Device Split", "Radial Center"):
            has_angle = False
        self.speed_widget.setVisible(has_speed)
        self.angle_widget.setVisible(has_angle)
        self.params_section.setVisible(has_speed or has_angle)

    def _on_palette_changed(self, name: str) -> None:
        self.shader.set_palette(name)
        self._refresh_swatches()
        self.canvas.update()

    def _refresh_swatches(self) -> None:
        stops = self.shader.custom_colors
        for i, btn in enumerate(self._swatch_buttons):
            if i < len(stops):
                r, g, b = stops[i]
                text_col = "#050811" if (r * 0.299 + g * 0.587 + b * 0.114) > 140 else "#FFFFFF"
                btn.setStyleSheet(
                    f"background-color: rgb({r},{g},{b}); color: {text_col}; border: 1px solid #FFFFFF; font-weight: 700;"
                )

    def _pick_stop_color(self, idx: int) -> None:
        while len(self.shader.custom_colors) <= idx:
            self.shader.custom_colors.append((0, 200, 255))
        r, g, b = self.shader.custom_colors[idx]
        col = QColorDialog.getColor(QColor(r, g, b), self, f"Select Color {idx + 1}")
        if col.isValid():
            self.shader.custom_colors[idx] = (col.red(), col.green(), col.blue())
            self._refresh_swatches()
            self.canvas.update()

    def _apply_quick_color(self, rgb: Tuple[int, int, int]) -> None:
        self.shader.custom_colors[0] = rgb
        self._refresh_swatches()
        self.canvas.update()

    def _on_mc_style_changed(self, label: str) -> None:
        self.shader.multicolor_style = self._mc_style_map.get(label, "Smooth Gradient")
        self._update_inspector_visibility()
        self.canvas.update()

    def _on_mc_count_changed(self, _idx: int) -> None:
        self.shader.num_active_stops = int(self.combo_mc_count.currentData() or 4)
        self._update_inspector_visibility()
        self._refresh_swatches()
        self.canvas.update()

    def _on_dev_enabled_toggled(self, dev: RGBDevice, enabled: bool) -> None:
        dev.enabled = enabled
        self.canvas.update()

    def _on_dev_brightness_changed(self, dev: RGBDevice, val: int, lbl: QLabel) -> None:
        dev.brightness = val
        lbl.setText(f"{int(round((val / 255.0) * 100))}%")
        self.canvas.update()

    def sync_device_sliders(self) -> None:
        if len(self._dev_br_sliders) != len(self.hw.devices):
            self.rebuild_device_brightness_list()
            return
        for dev, sld, lbl, chk in self._dev_br_sliders:
            chk.blockSignals(True)
            sld.blockSignals(True)
            chk.setChecked(dev.enabled)
            sld.setValue(dev.brightness)
            lbl.setText(f"{int(round((dev.brightness / 255.0) * 100))}%")
            chk.blockSignals(False)
            sld.blockSignals(False)

    def _on_speed_changed(self, val: int) -> None:
        self.shader.speed = val / 100.0
        self.lbl_speed.setText(f"Speed: {self.shader.speed:.1f}x")

    def _on_angle_changed(self, val: int) -> None:
        self.shader.angle_deg = float(val)
        self.lbl_angle.setText(f"Direction / Angle: {val}°")

    def _reset_positions(self) -> None:
        self.hw.sync_devices_from_bridge()
        self.sync_device_sliders()
        self.canvas.update()
