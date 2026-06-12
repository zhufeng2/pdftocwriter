"""浅色 / 深色主题：集中管理调色板、QSS 与控件矢量图标。"""
from __future__ import annotations

import atexit
import os
import shutil
import tempfile

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

_ICON_DIR = tempfile.mkdtemp(prefix="pdftoc_ui_")
# 退出时清理图标临时目录，避免每次启动残留一个 pdftoc_ui_* 目录
atexit.register(lambda: shutil.rmtree(_ICON_DIR, ignore_errors=True))


class Palette:
    def __init__(self, dark: bool) -> None:
        if dark:
            self.bg = "#1e2127"
            self.panel = "#262a31"
            self.panel_alt = "#2c313a"
            self.border = "#363b45"
            self.text = "#e6e8eb"
            self.subtle = "#9aa3af"
            self.accent = "#5b8def"
            self.accent_hover = "#6f9bf2"
            self.accent_text = "#ffffff"
            self.danger = "#e0596b"
            self.danger_bg = "#3a2329"
            self.editor_bg = "#22262d"
            self.canvas = "#191c21"
            self.scroll = "#3c424d"
        else:
            self.bg = "#f4f5f7"
            self.panel = "#ffffff"
            self.panel_alt = "#f7f8fa"
            self.border = "#e3e6ea"
            self.text = "#1f2933"
            self.subtle = "#6b7280"
            self.accent = "#4f7cff"
            self.accent_hover = "#3f6ae6"
            self.accent_text = "#ffffff"
            self.danger = "#d64550"
            self.danger_bg = "#fdecee"
            self.editor_bg = "#ffffff"
            self.canvas = "#eaecef"
            self.scroll = "#d4d8de"
        self.dark = dark


# ── 矢量图标（运行时绘制，随主题着色） ─────────────────────────────────────────

def _new_painter(pm: QPixmap, color: str, width: float) -> QPainter:
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    return p


def _chevron_pixmap(color: str, up: bool) -> QPixmap:
    pm = QPixmap(24, 24)
    p = _new_painter(pm, color, 1.8)
    if up:
        p.drawLine(8, 14, 12, 10)
        p.drawLine(12, 10, 16, 14)
    else:
        p.drawLine(8, 10, 12, 14)
        p.drawLine(12, 14, 16, 10)
    p.end()
    return pm


def chevron_pixmap(color: str, up: bool = False) -> QPixmap:
    """公开的 chevron 图标，供自定义控件（SelectBox 等）直接使用。"""
    return _chevron_pixmap(color, up)


def _save_icon(name: str, pm: QPixmap) -> str:
    path = os.path.join(_ICON_DIR, name)
    pm.save(path)
    return path.replace("\\", "/")


def theme_assets(p: Palette) -> dict[str, str]:
    """生成本主题用到的图标文件，返回 QSS 可引用的路径。"""
    suffix = "dark" if p.dark else "light"
    return {
        "chevron_up": _save_icon(f"up_{suffix}.png", _chevron_pixmap(p.subtle, True)),
        "chevron_down": _save_icon(f"down_{suffix}.png", _chevron_pixmap(p.subtle, False)),
    }


def make_eye_icon(p: Palette, off: bool) -> QIcon:
    """生成简洁的单色"眼睛"图标，用于 Token 显示/隐藏。"""
    pm = QPixmap(36, 36)
    painter = _new_painter(pm, p.subtle, 1.7)
    eye = QPainterPath()
    eye.moveTo(7, 18)
    eye.quadTo(18, 8, 29, 18)
    eye.quadTo(18, 28, 7, 18)
    painter.drawPath(eye)
    painter.drawEllipse(QRectF(14.5, 14.5, 7, 7))
    if off:
        painter.drawLine(9, 28, 27, 8)
    painter.end()
    return QIcon(pm)


def build_qss(p: Palette) -> str:
    a = theme_assets(p)
    return f"""
    QWidget {{
        background: {p.bg};
        color: {p.text};
        /* 注意：Qt 不识别 -apple-system（CSS 写法），会回退到行高偏小的字体，
           导致中文按钮文字顶部被裁；这里用真实字体名、中文字体优先 */
        font-family: "PingFang SC", "Helvetica Neue", "Microsoft YaHei", "Segoe UI", sans-serif;
        font-size: 13px;
    }}
    QLabel {{ background: transparent; }}
    QToolTip {{
        background: {p.panel}; color: {p.text};
        border: 1px solid {p.border}; border-radius: 6px; padding: 4px 6px;
    }}

    QFrame#Header {{ background: {p.panel}; border: none; border-bottom: 1px solid {p.border}; }}
    QLabel#AppTitle {{ font-size: 15px; font-weight: 600; }}
    QLabel#SectionLabel {{ font-size: 11px; font-weight: 700; color: {p.subtle}; }}
    QLabel#Hint {{ color: {p.subtle}; font-size: 12px; }}

    QFrame#Panel {{ background: {p.panel}; border: 1px solid {p.border}; border-radius: 10px; }}

    /* ── 按钮 ── */
    QPushButton {{
        background: {p.panel_alt}; border: 1px solid {p.border};
        border-radius: 7px; padding: 7px 12px; color: {p.text};
    }}
    QPushButton:hover {{ background: {p.border}; }}
    QPushButton:disabled {{ color: {p.subtle}; }}
    QPushButton#Primary {{
        background: {p.accent}; border: 1px solid {p.accent};
        color: {p.accent_text}; font-weight: 600;
    }}
    QPushButton#Primary:hover {{ background: {p.accent_hover}; border-color: {p.accent_hover}; }}
    QPushButton#Primary:disabled {{ background: {p.border}; border-color: {p.border}; color: {p.subtle}; }}
    QPushButton#Ghost {{ background: transparent; border: none; padding: 5px 9px; color: {p.subtle}; }}
    QPushButton#Ghost:hover {{ background: {p.panel_alt}; color: {p.text}; }}
    QPushButton#Ghost:checked {{ background: {p.panel_alt}; color: {p.accent}; }}
    QPushButton#Chip {{
        background: transparent; border: 1px solid {p.border};
        border-radius: 6px; padding: 4px 10px; font-size: 12px; color: {p.subtle};
    }}
    QPushButton#Chip:hover {{ background: {p.panel_alt}; color: {p.text}; }}

    /* ── 输入框 ── */
    QLineEdit {{
        background: {p.panel}; border: 1px solid {p.border};
        border-radius: 7px; padding: 6px 8px;
        selection-background-color: {p.accent}; selection-color: {p.accent_text};
    }}
    QLineEdit:focus {{ border-color: {p.accent}; }}

    /* ── 数字框：扁平 chevron 步进器 ── */
    QSpinBox {{
        background: {p.panel}; border: 1px solid {p.border};
        border-radius: 7px; padding: 5px 24px 5px 9px;
        selection-background-color: {p.accent};
    }}
    QSpinBox:focus {{ border-color: {p.accent}; }}
    QSpinBox::up-button, QSpinBox::down-button {{
        subcontrol-origin: border; width: 20px; border: none;
        background: transparent; margin: 2px 3px 2px 0;
    }}
    QSpinBox::up-button {{ subcontrol-position: top right; border-top-right-radius: 6px; }}
    QSpinBox::down-button {{ subcontrol-position: bottom right; border-bottom-right-radius: 6px; }}
    QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: {p.panel_alt}; }}
    QSpinBox::up-arrow {{ image: url({a['chevron_up']}); width: 16px; height: 16px; }}
    QSpinBox::down-arrow {{ image: url({a['chevron_down']}); width: 16px; height: 16px; }}

    /* ── 下拉框 ── */
    QComboBox {{
        background: {p.panel}; border: 1px solid {p.border};
        border-radius: 7px; padding: 6px 32px 6px 10px;
    }}
    QComboBox:hover {{ border-color: {p.subtle}; }}
    QComboBox:focus, QComboBox:on {{ border-color: {p.accent}; }}
    QComboBox::drop-down {{
        subcontrol-origin: padding; subcontrol-position: center right;
        width: 28px; border: none; background: transparent;
    }}
    QComboBox::down-arrow {{ image: url({a['chevron_down']}); width: 16px; height: 16px; }}
    QComboBox QAbstractItemView {{
        background: {p.panel}; border: 1px solid {p.border}; border-radius: 8px;
        padding: 4px; outline: none;
        selection-background-color: {p.accent}; selection-color: {p.accent_text};
    }}
    QComboBox QAbstractItemView::item {{ min-height: 28px; padding: 2px 8px; border-radius: 6px; }}

    QProgressBar {{
        background: {p.panel_alt}; border: none;
        border-radius: 3px; max-height: 6px; min-height: 6px;
    }}
    QProgressBar::chunk {{ background: {p.accent}; border-radius: 3px; }}

    /* ── PDF 预览画布：柔和中性底色 + 圆角，与卡片协调 ── */
    QPdfView {{ background: {p.canvas}; border: 1px solid {p.border}; border-radius: 8px; }}
    QLabel#PreviewPlaceholder {{ color: {p.subtle}; font-size: 13px; background: transparent; }}

    /* ── 编辑器：透明叠在圆角面板上；英文 Times New Roman、中文宋体 ── */
    QPlainTextEdit#Editor {{
        background: transparent; border: none;
        font-family: "Times New Roman", "Songti SC", "STSong", "SimSun", serif;
        font-size: 12px;
    }}

    /* ── 网页风格下拉选择（SelectBox） ── */
    QWidget#SelectPopupWrap {{ background: transparent; }}
    QFrame#SelectField {{
        background: {p.panel}; border: 1px solid {p.border}; border-radius: 7px;
    }}
    QFrame#SelectField:hover {{ border-color: {p.subtle}; }}
    QFrame#SelectField[open="true"] {{ border-color: {p.accent}; }}
    QLabel#SelectText {{ color: {p.text}; background: transparent; }}
    QLabel#SelectText[empty="true"] {{ color: {p.subtle}; }}
    QFrame#SelectPopup {{ background: {p.panel}; border: none; border-radius: 10px; }}
    QPushButton#SelectItem {{
        background: transparent; border: none; border-radius: 6px;
        padding: 7px 11px; text-align: left; color: {p.text};
    }}
    QPushButton#SelectItem:hover {{ background: {p.panel_alt}; }}
    QPushButton#SelectItem[selected="true"] {{ color: {p.accent}; font-weight: 600; }}

    QStatusBar {{ background: {p.panel}; border-top: 1px solid {p.border}; color: {p.subtle}; }}

    /* ── 圆角滚动条 ── */
    QScrollBar:vertical {{ background: transparent; width: 12px; margin: 4px 2px; }}
    QScrollBar::handle:vertical {{ background: {p.scroll}; border-radius: 4px; min-height: 32px; }}
    QScrollBar::handle:vertical:hover {{ background: {p.subtle}; }}
    QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px 4px; }}
    QScrollBar::handle:horizontal {{ background: {p.scroll}; border-radius: 4px; min-width: 32px; }}
    QScrollBar::handle:horizontal:hover {{ background: {p.subtle}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; background: transparent; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    """
