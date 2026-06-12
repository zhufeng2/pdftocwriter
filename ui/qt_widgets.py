"""自定义 Qt 控件：实时校验的目录编辑器、PDF 预览、网页风格下拉选择。"""
from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPointF,
    QPropertyAnimation,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPalette,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.bookmarks import validate_toc_text
from ui.qt_theme import chevron_pixmap


# ─────────────────────────────────────────────────────────────────────────────
#  单行省略标签：长文本中部省略 + tooltip，避免换行后左对齐难看
# ─────────────────────────────────────────────────────────────────────────────

class ElideLabel(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full = text
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._refresh()

    def set_full_text(self, text: str) -> None:
        self._full = text
        self.setToolTip(text)
        self._refresh()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        width = max(40, self.width() - 4)
        self.setText(self.fontMetrics().elidedText(
            self._full, Qt.TextElideMode.ElideMiddle, width))


# ─────────────────────────────────────────────────────────────────────────────
#  目录编辑器（不换行 + 实时校验；统一字色，仅顶级标题加粗）
# ─────────────────────────────────────────────────────────────────────────────

class _TocHighlighter(QSyntaxHighlighter):
    """统一字色，仅无缩进的顶级标题加粗。"""

    def __init__(self, doc) -> None:
        super().__init__(doc)
        self._bold = QTextCharFormat()
        self._bold.setFontWeight(QFont.Weight.Bold)

    def highlightBlock(self, text: str) -> None:
        if text.strip() and not text.startswith(" "):
            self.setFormat(0, len(text), self._bold)


class TocEditor(QPlainTextEdit):
    """衬线字体（英文 Times New Roman / 中文宋体）、不换行、顶级加粗。

    页码越界 / 无法解析的行用红色波浪下划线标注（IDE 风格，比整行红底克制）。
    """

    errorsChanged = Signal(int)  # 错误行数

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Editor")
        font = _editor_font()
        self.setFont(font)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)  # 不换行更整齐
        self.setTabStopDistance(QFontMetrics(font).horizontalAdvance(" ") * 4)

        self._total_pages = 0
        self._offset = 0
        self._errors: dict[int, str] = {}
        self._err_color = QColor(214, 69, 80)
        self._highlighter = _TocHighlighter(self.document())

        self.textChanged.connect(self.revalidate)

    def set_theme(self, palette) -> None:  # noqa: ARG002 - 字色由 QSS 统一控制
        self._highlighter.rehighlight()

    # 主窗口在打开 PDF / 改偏移时调用，提供校验上下文
    def set_context(self, total_pages: int, offset: int) -> None:
        self._total_pages = total_pages
        self._offset = offset
        self.revalidate()

    def set_offset(self, offset: int) -> None:
        self._offset = offset
        self.revalidate()

    def revalidate(self) -> None:
        if self._total_pages <= 0:
            new_errors: dict[int, str] = {}
        else:
            new_errors = validate_toc_text(self.toPlainText(), self._offset, self._total_pages)
        self._errors = new_errors
        self._apply_highlights()
        self.errorsChanged.emit(len(new_errors))

    def error_count(self) -> int:
        return len(self._errors)

    def _apply_highlights(self) -> None:
        selections: list[QTextEdit.ExtraSelection] = []
        doc = self.document()
        for line_idx, msg in self._errors.items():
            block = doc.findBlockByNumber(line_idx)
            if not block.isValid():
                continue
            sel = QTextEdit.ExtraSelection()
            sel.format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
            sel.format.setUnderlineColor(self._err_color)
            sel.format.setToolTip(msg)
            cursor = self.textCursor()
            cursor.setPosition(block.position())
            cursor.setPosition(
                block.position() + max(0, block.length() - 1),
                QTextCursor.MoveMode.KeepAnchor,
            )
            sel.cursor = cursor
            selections.append(sel)
        self.setExtraSelections(selections)


def _editor_font() -> QFont:
    font = QFont()
    font.setFamilies(["Times New Roman", "Songti SC", "STSong", "SimSun"])
    font.setPointSize(11)
    return font


# ─────────────────────────────────────────────────────────────────────────────
#  网页风格下拉选择：占位文本 + 圆角弹出层 + 阴影 + 淡入下滑动画 + 悬停高亮
# ─────────────────────────────────────────────────────────────────────────────

class SelectBox(QWidget):
    """仿网页 <select>：默认显示占位文本，弹出层在正下方平滑展开。"""

    currentTextChanged = Signal(str)

    _SHADOW_M = 10  # 弹出层四周留给阴影的透明边距

    def __init__(self, placeholder: str = "请选择", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: list[str] = []
        self._current = -1
        self._popup: QWidget | None = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._field = QFrame()
        self._field.setObjectName("SelectField")
        fl = QHBoxLayout(self._field)
        fl.setContentsMargins(11, 7, 11, 7)
        fl.setSpacing(6)
        self._text = QLabel(placeholder)
        self._text.setObjectName("SelectText")
        self._text.setProperty("empty", True)
        self._chevron = QLabel()
        self._chevron.setFixedSize(16, 16)
        self._chevron.setScaledContents(True)
        fl.addWidget(self._text, 1)
        fl.addWidget(self._chevron)
        lay.addWidget(self._field)

    # ── 数据接口（对齐 QComboBox 常用面） ──────────────────────────────────────
    def addItem(self, text: str) -> None:
        self._items.append(text)

    def addItems(self, texts: list[str]) -> None:
        self._items.extend(texts)

    def currentText(self) -> str:
        return self._items[self._current] if self._current >= 0 else ""

    def setCurrentIndex(self, idx: int) -> None:
        if 0 <= idx < len(self._items):
            self._choose(idx)

    def set_theme(self, palette) -> None:
        self._chevron.setPixmap(chevron_pixmap(palette.subtle))

    # ── 弹出层 ──────────────────────────────────────────────────────────────
    def mousePressEvent(self, event) -> None:  # noqa: ARG002
        self._open_popup()

    def _open_popup(self) -> None:
        if not self._items or self._popup is not None:
            return
        m = self._SHADOW_M
        outer = QWidget(
            self,
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint,  # 关掉系统给弹窗叠的原生阴影描边
        )
        outer.setObjectName("SelectPopupWrap")  # QSS 置透明，否则全局背景色会画出方形外框
        outer.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        outer.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        ol = QVBoxLayout(outer)
        ol.setContentsMargins(m, m, m, m)

        inner = QFrame()
        inner.setObjectName("SelectPopup")
        # 阴影要足够柔和，否则在小卡片上会糊成一圈深色"描边"
        shadow = QGraphicsDropShadowEffect(inner)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 26))
        inner.setGraphicsEffect(shadow)
        il = QVBoxLayout(inner)
        il.setContentsMargins(5, 5, 5, 5)
        il.setSpacing(1)
        for i, text in enumerate(self._items):
            btn = QPushButton(text)
            btn.setObjectName("SelectItem")
            btn.setProperty("selected", i == self._current)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, idx=i: self._choose(idx))
            il.addWidget(btn)
        ol.addWidget(inner)

        outer.setFixedWidth(self._field.width() + 2 * m)
        outer.adjustSize()

        below = self._field.mapToGlobal(QPoint(0, self._field.height() + 4))
        end = QPoint(below.x() - m, below.y() - m)
        self._popup = outer
        self._set_open(True)
        outer.destroyed.connect(self._on_popup_closed)

        # 网页下拉效果：淡入 + 自上而下轻微滑入
        outer.move(end.x(), end.y() - 8)
        outer.setWindowOpacity(0.0)
        outer.show()
        self._fade = QPropertyAnimation(outer, b"windowOpacity", self)
        self._fade.setDuration(150)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._slide = QPropertyAnimation(outer, b"pos", self)
        self._slide.setDuration(150)
        self._slide.setStartValue(QPoint(end.x(), end.y() - 8))
        self._slide.setEndValue(end)
        self._slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.start()
        self._slide.start()

    def _on_popup_closed(self) -> None:
        self._popup = None
        self._set_open(False)

    def _choose(self, idx: int) -> None:
        changed = idx != self._current
        self._current = idx
        self._text.setText(self._items[idx])
        self._text.setProperty("empty", False)
        self._text.style().unpolish(self._text)
        self._text.style().polish(self._text)
        if self._popup is not None:
            self._popup.close()
        if changed:
            self.currentTextChanged.emit(self._items[idx])

    def _set_open(self, on: bool) -> None:
        self._field.setProperty("open", on)
        self._field.style().unpolish(self._field)
        self._field.style().polish(self._field)


# ─────────────────────────────────────────────────────────────────────────────
#  PDF 预览：工具条 + 竖向连续翻页大图（无侧栏、无模式切换，保持视图稳定）
# ─────────────────────────────────────────────────────────────────────────────

class PdfPreview(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._doc = QPdfDocument(self)
        self._zoom = 1.0
        self._doc.statusChanged.connect(self._on_status)
        self._build_ui()

    # ── UI ──────────────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        root.addLayout(self._build_toolbar())

        host = QWidget()
        grid = QGridLayout(host)
        grid.setContentsMargins(0, 0, 0, 0)
        self.view = QPdfView(self)
        self.view.setDocument(self._doc)
        self.view.setPageMode(QPdfView.PageMode.MultiPage)  # 竖向连续翻页
        self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.view.pageNavigator().currentPageChanged.connect(self._on_page_changed)
        grid.addWidget(self.view, 0, 0)

        self.placeholder = QLabel("未导入 PDF\n\n点击「打开 PDF」或将文件拖入窗口")
        self.placeholder.setObjectName("PreviewPlaceholder")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(self.placeholder, 0, 0, Qt.AlignmentFlag.AlignCenter)

        root.addWidget(host, 1)

    def _build_toolbar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(6)

        self.btn_prev = _ghost("‹", self._prev_page, tip="上一页")
        self.btn_next = _ghost("›", self._next_page, tip="下一页")
        self.page_label = QLabel("— / —")
        self.page_label.setObjectName("Hint")
        self.page_label.setMinimumWidth(64)
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        bar.addWidget(self.btn_prev)
        bar.addWidget(self.page_label)
        bar.addWidget(self.btn_next)
        bar.addSpacing(8)
        bar.addWidget(_ghost("－", lambda: self._set_zoom(self._zoom / 1.2), tip="缩小"))
        bar.addWidget(_ghost("＋", lambda: self._set_zoom(self._zoom * 1.2), tip="放大"))
        bar.addWidget(_ghost("适应宽度", self._fit_width, tip="适应宽度"))
        bar.addStretch(1)
        return bar

    def is_ready(self) -> bool:
        return self._doc.status() == QPdfDocument.Status.Ready

    def set_canvas_color(self, color: str) -> None:
        # QPdfView 用 QPalette 绘制页面外的画布底色，QSS 触达不到，单独设置
        col = QColor(color)
        pal = self.view.palette()
        for role in (QPalette.ColorRole.Dark, QPalette.ColorRole.Mid,
                     QPalette.ColorRole.Base, QPalette.ColorRole.Window):
            pal.setColor(role, col)
        self.view.setPalette(pal)
        self.view.viewport().setPalette(pal)

    # ── 文档加载 ─────────────────────────────────────────────────────────────
    def load(self, path: str) -> None:
        self._doc.load(path)

    def _on_status(self, status: QPdfDocument.Status) -> None:
        ready = status == QPdfDocument.Status.Ready
        self.placeholder.setVisible(not ready)
        if not ready:
            return
        self._zoom = 1.0
        self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self._update_page_label()

    # ── 导航 ────────────────────────────────────────────────────────────────
    def current_page(self) -> int:
        return self.view.pageNavigator().currentPage() + 1  # 1-based

    def jump_to(self, page_1based: int) -> None:
        if self._doc.status() != QPdfDocument.Status.Ready:
            return
        # 不传 zoom：FitToWidth 下传入 currentZoom()（常为 1.0）会先闪放再重排
        self.view.pageNavigator().jump(max(0, page_1based - 1), QPointF(0, 0))
        # QPdfView 按"视口中心所在页"判定当前页：页面比视口矮时，目标页顶在
        # 视口顶部会让中心落到下一页。跳后把目标页居中，使判定与目标一致。
        vbar = self.view.verticalScrollBar()
        vh = self.view.viewport().height()
        n = self._doc.pageCount()
        if n > 0 and vh > 0:
            page_h = (vbar.maximum() + vh) / n  # 含间距的平均页高（设备像素）
            overshoot = round((vh - page_h) / 2)
            if overshoot > 0:
                vbar.setValue(max(0, vbar.value() - overshoot))

    def _prev_page(self) -> None:
        self.jump_to(max(1, self.current_page() - 1))

    def _next_page(self) -> None:
        self.jump_to(min(self._doc.pageCount(), self.current_page() + 1))

    def _on_page_changed(self, _page0: int) -> None:
        self._update_page_label()

    def _update_page_label(self) -> None:
        total = self._doc.pageCount()
        if total <= 0:
            self.page_label.setText("— / —")
        else:
            self.page_label.setText(f"{self.current_page()} / {total}")

    def _set_zoom(self, factor: float) -> None:
        self._zoom = max(0.2, min(6.0, factor))
        self.view.setZoomMode(QPdfView.ZoomMode.Custom)
        self.view.setZoomFactor(self._zoom)

    def _fit_width(self) -> None:
        self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)


# ── 小工厂 ──────────────────────────────────────────────────────────────────

def _ghost(text: str, slot, tip: str = "") -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("Ghost")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    if tip:
        btn.setToolTip(tip)
    if slot is not None:
        btn.clicked.connect(slot)
    return btn
