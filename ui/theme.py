"""
Cyberpunk / Obsidian Dark Glassmorphism Theme for PrismaRGB Studio.
"""

DARK_STUDIO_STYLESHEET = """
QMainWindow, QWidget#RootWidget {
    background-color: #090C15;
    color: #E6EDF8;
    font-family: "Inter", "Noto Sans", "Segoe UI", sans-serif;
    font-size: 13px;
}

QFrame#TopBar {
    background-color: #0E1322;
    border-bottom: 1px solid #1E2942;
}

QFrame#Sidebar {
    background-color: #0C101D;
    border-right: 1px solid #1C253B;
}

QFrame#Card {
    background-color: #111728;
    border: 1px solid #1F2A44;
    border-radius: 12px;
}

QFrame#AccentCard {
    background-color: #131B30;
    border: 1px solid #00D4FF;
    border-radius: 12px;
}

QFrame#WarningCard {
    background-color: #1E1420;
    border: 1px solid #FF006E;
    border-radius: 12px;
}

QLabel {
    color: #E2E8F5;
    background: transparent;
}

QLabel#TitleLabel {
    font-size: 18px;
    font-weight: 700;
    color: #FFFFFF;
}

QLabel#SubtitleLabel {
    font-size: 12px;
    color: #8A9BB8;
}

QLabel#SectionHeader {
    font-size: 14px;
    font-weight: 700;
    color: #00F0FF;
}

QLabel#MetricBadge {
    background-color: #161F36;
    border: 1px solid #263558;
    border-radius: 8px;
    padding: 5px 10px;
    font-weight: 600;
    color: #D4E4FF;
}

QPushButton {
    background-color: #182138;
    color: #E2EBF8;
    border: 1px solid #2A395C;
    border-radius: 8px;
    padding: 7px 14px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #212E4D;
    border-color: #00D4FF;
}

QPushButton:pressed {
    background-color: #00A8CC;
    color: #060911;
}

QPushButton#NavButton {
    text-align: left;
    padding: 11px 16px;
    border-radius: 9px;
    border: 1px solid transparent;
    background-color: transparent;
    color: #9AB0D0;
    font-size: 13px;
    font-weight: 600;
}

QPushButton#NavButton:hover {
    background-color: #141D33;
    color: #FFFFFF;
}

QPushButton#NavButton[active="true"] {
    background-color: #152340;
    border: 1px solid #00E5FF;
    color: #00F0FF;
}

QPushButton#PrimaryButton {
    background-color: #00C8FF;
    color: #060911;
    border: 1px solid #40E0FF;
    font-weight: 700;
}

QPushButton#PrimaryButton:hover {
    background-color: #33D6FF;
}

QPushButton#DangerButton {
    background-color: #FF006E;
    color: #FFFFFF;
    border: 1px solid #FF4D94;
    font-weight: 700;
}

QPushButton#DangerButton:hover {
    background-color: #FF2A85;
}

QComboBox, QLineEdit {
    background-color: #151D31;
    color: #ECF2FC;
    border: 1px solid #273657;
    border-radius: 7px;
    padding: 6px 10px;
}

QComboBox:hover, QLineEdit:hover {
    border-color: #00D4FF;
}

QComboBox QAbstractItemView {
    background-color: #111728;
    color: #ECF2FC;
    selection-background-color: #00B4D8;
    selection-color: #060911;
    border: 1px solid #273657;
}

QSlider::groove:horizontal {
    height: 6px;
    background: #1A243D;
    border-radius: 3px;
}

QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00F0FF, stop:1 #FF007F);
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background: #FFFFFF;
    border: 2px solid #00F0FF;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}

QScrollArea {
    background: transparent;
    border: none;
}

QCheckBox {
    color: #D8E4F8;
    spacing: 8px;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 1px solid #2C3D63;
    background: #141C30;
}

QCheckBox::indicator:checked {
    background: #00E5FF;
    border-color: #00E5FF;
}
"""
