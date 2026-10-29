"""
Hardware-Agnostic System Monitoring Dashboard for PrismaRGB.
Renders custom anti-aliased circular arc gauges, 60-second rolling area charts
for temperatures and utilization, and per-core CPU load bars.
"""

from typing import Deque, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from backend.telemetry import SystemMetrics, TelemetryEngine


class ArcGaugeCard(QFrame):
    def __init__(
        self,
        title: str,
        accent_color: QColor,
        max_value: float = 100.0,
        unit: str = "°C",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.title = title
        self.accent_color = accent_color
        self.max_value = max_value
        self.unit = unit

        self.value: float = 0.0
        self.hardware_label: str = ""
        self.sub_metric_left: str = ""
        self.sub_metric_right: str = ""
        self.setMinimumSize(240, 215)

    def set_data(
        self,
        value: float,
        hardware_label: str,
        sub_left: str,
        sub_right: str = "",
    ) -> None:
        self.value = value
        self.hardware_label = hardware_label
        self.sub_metric_left = sub_left
        self.sub_metric_right = sub_right
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w = float(self.width())
        h = float(self.height())

        p.setPen(QColor(0, 240, 255))
        p.setFont(QFont("Inter", 10, QFont.Weight.Bold))
        p.drawText(QRectF(14, 10, w - 28, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.title)

        p.setPen(QColor(138, 155, 184))
        p.setFont(QFont("Inter", 8))
        elided_hw = self.hardware_label if len(self.hardware_label) <= 36 else self.hardware_label[:35] + "…"
        p.drawText(QRectF(14, 28, w - 28, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided_hw)

        arc_size = min(w - 60, h - 88)
        arc_size = max(96.0, min(132.0, arc_size))
        cx = w * 0.5
        cy = 50.0 + arc_size * 0.5
        arc_rect = QRectF(cx - arc_size * 0.5, cy - arc_size * 0.5, arc_size, arc_size)

        start_angle = 225 * 16
        span_total = -270 * 16

        track_pen = QPen(QColor(26, 36, 58), 9.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(track_pen)
        p.drawArc(arc_rect, start_angle, span_total)

        ratio = max(0.0, min(1.0, self.value / max(1.0, self.max_value)))
        active_col = self.accent_color
        if self.unit == "°C" and self.value >= 82.0:
            active_col = QColor(255, 45, 85)
        elif self.unit == "°C" and self.value >= 70.0:
            active_col = QColor(255, 183, 3)

        val_pen = QPen(active_col, 9.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(val_pen)
        p.drawArc(arc_rect, start_angle, int(span_total * ratio))

        p.setPen(QColor(240, 246, 255))
        p.setFont(QFont("Inter", 19, QFont.Weight.Bold))
        val_str = f"{self.value:.1f}{self.unit}" if self.unit == "°C" else f"{int(round(self.value))}{self.unit}"
        p.drawText(arc_rect, Qt.AlignmentFlag.AlignCenter, val_str)

        footer_y = h - 30.0
        p.setPen(QColor(197, 212, 235))
        p.setFont(QFont("Inter", 9, QFont.Weight.DemiBold))
        if self.sub_metric_right:
            p.drawText(QRectF(14, footer_y, w * 0.52, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.sub_metric_left)
            p.drawText(QRectF(w * 0.48, footer_y, w * 0.52 - 14, 20), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self.sub_metric_right)
        else:
            p.drawText(QRectF(14, footer_y, w - 28, 20), Qt.AlignmentFlag.AlignCenter, self.sub_metric_left)


class DualHistoryChartCard(QFrame):
    def __init__(
        self,
        title: str,
        series_a_label: str,
        series_a_color: QColor,
        series_b_label: str,
        series_b_color: QColor,
        max_y: float = 100.0,
        unit: str = "°C",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.title = title
        self.series_a_label = series_a_label
        self.series_a_color = series_a_color
        self.series_b_label = series_b_label
        self.series_b_color = series_b_color
        self.max_y = max_y
        self.unit = unit
        self.data_a: List[float] = []
        self.data_b: List[float] = []
        self.setMinimumHeight(195)

    def update_series(self, history_a: Deque[float], history_b: Deque[float]) -> None:
        self.data_a = list(history_a)
        self.data_b = list(history_b)
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w = float(self.width())
        h = float(self.height())

        p.setPen(QColor(0, 240, 255))
        p.setFont(QFont("Inter", 10, QFont.Weight.Bold))
        p.drawText(QRectF(16, 10, w * 0.5, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.title)

        cur_a = self.data_a[-1] if self.data_a else 0.0
        cur_b = self.data_b[-1] if self.data_b else 0.0
        p.setFont(QFont("Inter", 9, QFont.Weight.DemiBold))
        p.setPen(self.series_a_color)
        p.drawText(
            QRectF(w - 280, 10, 130, 20),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"● {self.series_a_label}: {cur_a:.1f}{self.unit}",
        )
        p.setPen(self.series_b_color)
        p.drawText(
            QRectF(w - 140, 10, 124, 20),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"● {self.series_b_label}: {cur_b:.1f}{self.unit}",
        )

        left = 42.0
        top = 38.0
        right = w - 16.0
        bottom = h - 18.0
        pw = max(10.0, right - left)
        ph = max(10.0, bottom - top)

        p.setFont(QFont("Inter", 8))
        for step in range(5):
            frac = step / 4.0
            gy = bottom - frac * ph
            p.setPen(QPen(QColor(255, 255, 255, 20), 1, Qt.PenStyle.DotLine))
            p.drawLine(int(left), int(gy), int(right), int(gy))
            p.setPen(QColor(138, 155, 184))
            lbl_val = int(round(frac * self.max_y))
            p.drawText(QRectF(4, gy - 8, left - 8, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{lbl_val}{self.unit}")

        self._draw_curve(p, self.data_a, self.series_a_color, left, top, pw, ph)
        self._draw_curve(p, self.data_b, self.series_b_color, left, top, pw, ph)

    def _draw_curve(
        self,
        p: QPainter,
        values: List[float],
        color: QColor,
        left: float,
        top: float,
        pw: float,
        ph: float,
    ) -> None:
        if len(values) < 2:
            return
        n = len(values)
        pts: List[QPointF] = []
        for i, val in enumerate(values):
            x = left + (i / max(1, n - 1)) * pw
            norm = max(0.0, min(1.0, val / max(1.0, self.max_y)))
            y = top + ph * (1.0 - norm)
            pts.append(QPointF(x, y))

        line_path = QPainterPath()
        line_path.moveTo(pts[0])
        for pt in pts[1:]:
            line_path.lineTo(pt)

        area_path = QPainterPath(line_path)
        area_path.lineTo(QPointF(pts[-1].x(), top + ph))
        area_path.lineTo(QPointF(pts[0].x(), top + ph))
        area_path.closeSubpath()

        grad = QLinearGradient(0, top, 0, top + ph)
        fill_top = QColor(color.red(), color.green(), color.blue(), 68)
        fill_bot = QColor(color.red(), color.green(), color.blue(), 4)
        grad.setColorAt(0.0, fill_top)
        grad.setColorAt(1.0, fill_bot)
        p.fillPath(area_path, grad)

        p.setPen(QPen(color, 2.2))
        p.drawPath(line_path)


class SystemMonitoringTab(QWidget):
    def __init__(
        self,
        telemetry: TelemetryEngine,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.telemetry = telemetry
        self._core_bars: List[Tuple[QProgressBar, QLabel]] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(14)

        gauges_row = QHBoxLayout()
        gauges_row.setSpacing(14)

        self.gauge_cpu = ArcGaugeCard("PROCESSOR (CPU)", QColor(0, 240, 255), max_value=100.0, unit="°C")
        self.gauge_gpu = ArcGaugeCard("GRAPHICS (GPU)", QColor(255, 0, 127), max_value=100.0, unit="°C")
        self.gauge_ram = ArcGaugeCard("MEMORY (RAM)", QColor(0, 255, 157), max_value=100.0, unit="%")
        self.gauge_board = ArcGaugeCard("MOTHERBOARD & NVME", QColor(255, 183, 3), max_value=100.0, unit="°C")

        gauges_row.addWidget(self.gauge_cpu, 1)
        gauges_row.addWidget(self.gauge_gpu, 1)
        gauges_row.addWidget(self.gauge_ram, 1)
        gauges_row.addWidget(self.gauge_board, 1)
        root.addLayout(gauges_row)

        charts_row = QHBoxLayout()
        charts_row.setSpacing(14)

        self.chart_temps = DualHistoryChartCard(
            "Temperature History (Last 60 Seconds)",
            "CPU",
            QColor(0, 240, 255),
            "GPU",
            QColor(255, 0, 127),
            max_y=100.0,
            unit="°C",
        )
        self.chart_loads = DualHistoryChartCard(
            "Utilization History (Last 60 Seconds)",
            "CPU",
            QColor(0, 255, 157),
            "GPU",
            QColor(255, 183, 3),
            max_y=100.0,
            unit="%",
        )
        charts_row.addWidget(self.chart_temps, 1)
        charts_row.addWidget(self.chart_loads, 1)
        root.addLayout(charts_row, 1)

        cores_card = QFrame()
        cores_card.setObjectName("Card")
        cc_layout = QVBoxLayout(cores_card)
        cc_layout.setContentsMargins(16, 12, 16, 12)
        cc_layout.setSpacing(8)

        hdr_row = QHBoxLayout()
        lbl_cores = QLabel("Processor Threads & System Sensors")
        lbl_cores.setObjectName("SectionHeader")
        hdr_row.addWidget(lbl_cores)
        hdr_row.addStretch()
        self.lbl_fans_summary = QLabel("")
        self.lbl_fans_summary.setObjectName("SubtitleLabel")
        hdr_row.addWidget(self.lbl_fans_summary)
        cc_layout.addLayout(hdr_row)

        self.cores_grid = QGridLayout()
        self.cores_grid.setHorizontalSpacing(14)
        self.cores_grid.setVerticalSpacing(6)
        cc_layout.addLayout(self.cores_grid)

        root.addWidget(cores_card)

    def _ensure_core_bars(self, count: int) -> None:
        if len(self._core_bars) == count or count <= 0:
            return
        while self.cores_grid.count():
            item = self.cores_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._core_bars.clear()

        cols = 4 if count >= 8 else 2
        for i in range(count):
            r = i // cols
            c = (i % cols) * 3
            lbl_name = QLabel(f"Thread #{i + 1}")
            lbl_name.setStyleSheet("color: #8A9BB8; font-size: 11px;")
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setTextVisible(False)
            bar.setFixedHeight(10)
            lbl_val = QLabel("0%")
            lbl_val.setFixedWidth(36)
            lbl_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lbl_val.setStyleSheet("color: #EAF2FF; font-size: 11px; font-weight: 600;")

            self.cores_grid.addWidget(lbl_name, r, c)
            self.cores_grid.addWidget(bar, r, c + 1)
            self.cores_grid.addWidget(lbl_val, r, c + 2)
            self._core_bars.append((bar, lbl_val))

    def refresh_metrics(self, m: SystemMetrics) -> None:
        freq_txt = f"{m.cpu_freq_ghz:.2f} GHz" if m.cpu_freq_ghz > 0 else ""
        self.gauge_cpu.set_data(
            m.cpu_temp,
            m.cpu_name,
            f"Load: {m.cpu_load:.0f}%",
            freq_txt,
        )

        gpu_right = (
            f"{m.gpu_power_w:.0f} W"
            if m.gpu_power_w > 0
            else (f"VRAM: {m.gpu_vram_used_gb:.1f}/{m.gpu_vram_total_gb:.0f} GB" if m.gpu_vram_total_gb > 0 else "")
        )
        self.gauge_gpu.set_data(
            m.gpu_temp,
            m.gpu_name,
            f"Load: {m.gpu_load:.0f}%",
            gpu_right,
        )

        self.gauge_ram.set_data(
            m.ram_load,
            "System Memory",
            f"Used: {m.ram_used_gb:.1f} / {m.ram_total_gb:.1f} GB",
            "",
        )

        self.gauge_board.set_data(
            m.board_temp,
            m.board_name,
            f"NVMe SSD: {m.nvme_temp:.1f}°C",
            f"Board: {m.board_temp:.1f}°C",
        )

        self.chart_temps.update_series(self.telemetry.cpu_temp_history, self.telemetry.gpu_temp_history)
        self.chart_loads.update_series(self.telemetry.cpu_load_history, self.telemetry.gpu_load_history)

        if m.cpu_core_loads:
            self._ensure_core_bars(min(24, len(m.cpu_core_loads)))
            for i, (bar, lbl) in enumerate(self._core_bars):
                load_v = int(round(m.cpu_core_loads[i]))
                bar.setValue(load_v)
                lbl.setText(f"{load_v}%")

        if m.fan_rpms:
            fan_txt = "  •  ".join(f"{name}: {rpm} RPM" for name, rpm in m.fan_rpms[:4])
            self.lbl_fans_summary.setText(fan_txt)
        else:
            vram_txt = f"VRAM: {m.gpu_vram_used_gb:.1f} / {m.gpu_vram_total_gb:.1f} GB" if m.gpu_vram_total_gb > 0 else ""
            hot_txt = f"GPU Hotspot: {m.gpu_hotspot_temp:.1f}°C" if m.gpu_hotspot_temp > 0 else ""
            self.lbl_fans_summary.setText("   •   ".join(x for x in (hot_txt, vram_txt) if x))
