"""PySide6 主窗口：三栏布局（操作 / 预览 / 编辑），单文件走完全程。

对应 plan.md 第 1、2 部分：在应用内预览 PDF、框选目录页、同一份文件写入。
"""
from __future__ import annotations

import os

from PySide6.QtCore import QByteArray, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.bookmarks import extract_bookmarks, write_bookmarks_to_pdf
from core.config import load_config, save_config
from core.ocr import extract_toc_via_ocr
from core.pdf_service import PdfService
from ui.qt_theme import Palette, build_qss, make_eye_icon
from ui.qt_widgets import ElideLabel, PdfPreview, SelectBox, TocEditor
from ui.toc_formatter import auto_format


MAX_OCR_PAGES = 20  # 一次识别的页数上限：目录通常只有几页，防止误传整本书

# 识别后端注册表：新增服务商时在此登记 名称 → 函数(pdf_path, token, progress_cb) -> str，
# 下拉选项自动生成（plan P1 的 Claude 视觉识别等将来在这里接入）
OCR_BACKENDS = {
    "PaddleOCR 云 API": extract_toc_via_ocr,
}

EXAMPLE_TOC = (
    "第1章 绪论 1\n"
    "      1.1 研究背景 1\n"
    "      1.2 研究目的 2\n"
    "            1.2.1 范围界定 3\n"
    "第2章 相关工作 5\n"
    "      2.1 综述 5\n"
    "      2.2 方法 8\n"
    "第3章 方法论 12\n"
)


class OcrWorker(QThread):
    progress = Signal(str)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, pdf_path: str, token: str, backend) -> None:
        super().__init__()
        self.pdf_path = pdf_path  # 待识别的临时 PDF；线程结束后由主窗口负责删除
        self._token = token
        self._backend = backend

    def run(self) -> None:
        try:
            text = self._backend(self.pdf_path, self._token, progress_cb=self.progress.emit)
            self.done.emit(text)
        except Exception as exc:  # noqa: BLE001 - 反馈给 UI
            self.failed.emit(str(exc))


class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._config = load_config()
        self._dark = self._config.get("theme") == "dark"
        self._palette = Palette(self._dark)
        self._pdf: PdfService | None = None
        self._pdf_path: str | None = None
        self._ocr_worker: OcrWorker | None = None  # 当前结果归属的 worker（None = 无进行中识别）
        self._ocr_workers: set[OcrWorker] = set()  # 所有存活线程，保活引用直到 finished 后回收

        self.setWindowTitle(f"PDF TOC Writer")
        self.setAcceptDrops(True)
        self.setMinimumSize(1080, 680)

        self._build_ui()
        self._apply_theme()
        self._restore_geometry()

    # ── 布局 ────────────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        # 固定三栏：不可拖拽改宽，避免拉伸破坏视图
        columns = QHBoxLayout()
        columns.setSpacing(12)
        left = self._build_left_panel()
        left.setFixedWidth(272)
        right = self._build_right_panel()
        right.setFixedWidth(390)
        columns.addWidget(left)
        columns.addWidget(self._build_center_panel(), 1)
        columns.addWidget(right)

        wrap = QWidget()
        wrap_l = QVBoxLayout(wrap)
        wrap_l.setContentsMargins(12, 8, 12, 8)
        wrap_l.addLayout(columns)
        root.addWidget(wrap, 1)

        root.addWidget(self._build_statusbar())

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("Header")
        lay = QHBoxLayout(header)
        lay.setContentsMargins(18, 12, 14, 12)

        title = QLabel("PDF TOC Writer")
        title.setObjectName("AppTitle")
        lay.addWidget(title)
        lay.addStretch(1)

        self.theme_btn = QPushButton("🌙 深色" if not self._dark else "☀️ 浅色")
        self.theme_btn.setObjectName("Ghost")
        self.theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_btn.clicked.connect(self._toggle_theme)
        help_btn = QPushButton("使用帮助")
        help_btn.setObjectName("Ghost")
        help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        help_btn.clicked.connect(self._show_help)
        lay.addWidget(help_btn)
        lay.addWidget(self.theme_btn)
        return header

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        col = QVBoxLayout(panel)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(12)

        # 1) 文件
        f_frame, f_box = _section("文件")
        self.open_btn = _primary("打开 PDF", self._pick_file)
        # 单行中部省略：长文件名不换行（换行后各行左对齐难看），完整名见 tooltip
        self.file_label = ElideLabel("尚未选择文件")
        self.file_label.setObjectName("Hint")
        self.pages_label = QLabel("")
        self.pages_label.setObjectName("Hint")
        self.pages_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        f_box.addWidget(self.open_btn)
        f_box.addWidget(self.file_label)
        f_box.addWidget(self.pages_label)
        col.addWidget(f_frame)

        # 2) 目录页范围
        r_frame, r_box = _section("目录页范围")
        range_row = QHBoxLayout()
        self.start_spin = _spin(1, 1, width=84)
        self.end_spin = _spin(1, 1, width=84)
        range_row.addWidget(QLabel("从"))
        range_row.addWidget(self.start_spin, 1)
        range_row.addWidget(QLabel("到"))
        range_row.addWidget(self.end_spin, 1)
        r_box.addLayout(range_row)

        mark_row = QHBoxLayout()
        mark_row.addWidget(_button("当前页 → 起始", lambda: self._mark_from_preview(self.start_spin)))
        mark_row.addWidget(_button("当前页 → 结束", lambda: self._mark_from_preview(self.end_spin)))
        r_box.addLayout(mark_row)
        r_box.addWidget(_primary("自动检测目录页", self._detect_toc))
        col.addWidget(r_frame)

        # 3) 识别
        o_frame, o_box = _section("识别目录")
        self.backend_combo = SelectBox(placeholder="请选择")
        self.backend_combo.addItems(list(OCR_BACKENDS))
        self.backend_combo.setCurrentIndex(0)  # 仅一个后端时默认选中
        o_box.addWidget(self.backend_combo)

        self.token_edit = QLineEdit(self._config.get("token", ""))
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_edit.setPlaceholderText("API Token")
        self.token_edit.textChanged.connect(self._on_token_change)
        # 在输入框内嵌"眼睛"图标切换可见性（与浏览器密码框一致）
        self._eye_action = self.token_edit.addAction(
            make_eye_icon(self._palette, off=False),
            QLineEdit.ActionPosition.TrailingPosition,
        )
        self._eye_action.setToolTip("显示 / 隐藏 Token")
        self._eye_action.triggered.connect(self._toggle_token_visibility)
        o_box.addWidget(self.token_edit)

        # 识别按钮：仿 Claude 发送键，识别中切换为可随时点击的「停止」
        self.ocr_btn = _primary("识别选定页", self._on_ocr_btn)
        o_box.addWidget(self.ocr_btn)
        col.addWidget(o_frame)

        # 4) 页码偏移
        off_frame, off_box = _section("页码偏移")
        off_row = QHBoxLayout()
        # 84px 足够容纳 "-9999"；默认 96px 会把同行按钮挤到比文字最小宽度还窄，导致文字两侧被裁
        self.offset_spin = _spin(-9999, 0, 9999, width=84)
        self.offset_spin.valueChanged.connect(self._on_offset_change)
        off_row.addWidget(self.offset_spin)
        off_row.addWidget(_button("用当前页为正文首页", self._set_offset_from_preview), 1)
        off_box.addLayout(off_row)
        col.addWidget(off_frame)

        col.addStretch(1)
        return panel

    def _build_center_panel(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("Panel")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(10, 10, 10, 10)
        self.preview = PdfPreview()
        lay.addWidget(self.preview)
        return frame

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        col = QVBoxLayout(panel)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(8)

        head = QHBoxLayout()
        head.addWidget(QLabel("目录编辑"))
        head.addStretch(1)
        for text, slot in (
            ("示例", self._load_example),
            ("清空", lambda: self.editor.clear()),
            ("自动格式化", self._auto_format),
            ("导入", self._import_toc),
            ("导出", self._export_toc),
        ):
            head.addWidget(_chip(text, slot))
        col.addLayout(head)

        editor_frame = QFrame()
        editor_frame.setObjectName("Panel")
        ef = QVBoxLayout(editor_frame)
        ef.setContentsMargins(12, 10, 8, 10)
        self.editor = TocEditor()
        self.editor.errorsChanged.connect(self._on_errors_changed)
        ef.addWidget(self.editor)
        col.addWidget(editor_frame, 1)

        self.write_btn = _primary("写入书签到 PDF", self._write_toc)
        col.addWidget(self.write_btn)
        return panel

    def _build_statusbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("Header")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 6, 16, 6)
        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("Hint")
        self.error_label = QLabel("")
        self.error_label.setObjectName("Hint")
        lay.addWidget(self.status_label)
        lay.addStretch(1)
        lay.addWidget(self.error_label)
        return bar

    # ── 文件 / 流程 ───────────────────────────────────────────────────────────
    def _pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 PDF", self._config.get("last_dir", ""), "PDF 文件 (*.pdf)"
        )
        if path:
            self._open_pdf(path)

    def _open_pdf(self, path: str) -> None:
        try:
            self._pdf = PdfService(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "无法打开", f"读取 PDF 失败：{exc}")
            return

        # 切换文件前放弃进行中的识别，否则旧书的结果会落进新书的编辑器
        if self._ocr_worker is not None:
            self._reset_ocr_ui()

        self._pdf_path = path
        self._config["last_dir"] = os.path.dirname(path)
        save_config(self._config)

        total = self._pdf.page_count
        self.file_label.set_full_text(os.path.basename(path))
        self.pages_label.setText(f"共 {total} 页")
        self.start_spin.setMaximum(total)
        self.end_spin.setMaximum(total)
        self.end_spin.setValue(min(total, 8))

        self.preview.load(path)
        self.editor.set_context(total, self.offset_spin.value())

        bookmarks = extract_bookmarks(path)
        if bookmarks:
            self.editor.setPlainText(bookmarks)
            self._set_status("已载入文件中现有书签，可直接编辑或重新识别。")
        else:
            self._set_status("已打开 PDF。请在预览中定位目录页后点击「识别选定页」。")

        guess = self._pdf.detect_toc_pages()
        if guess:
            self.start_spin.setValue(guess[0])
            self.end_spin.setValue(guess[1])
            self.preview.jump_to(guess[0])
            self._set_status(f"已自动建议目录页范围：第 {guess[0]}–{guess[1]} 页，请在预览中确认。")

    def _detect_toc(self) -> None:
        if not self._pdf:
            self._set_status("请先打开 PDF。")
            return
        guess = self._pdf.detect_toc_pages()
        if guess:
            self.start_spin.setValue(guess[0])
            self.end_spin.setValue(guess[1])
            self.preview.jump_to(guess[0])
            self._set_status(f"检测到目录页范围：第 {guess[0]}–{guess[1]} 页。")
        else:
            self._set_status("未能自动识别目录页。")
            self._info("未自动检测到目录页，请在预览中手动标记。")

    def _mark_from_preview(self, spin: QSpinBox) -> None:
        if not self._pdf or not self.preview.is_ready():
            self._set_status("请先打开 PDF。")
            return
        spin.setValue(self.preview.current_page())

    def _set_offset_from_preview(self) -> None:
        if not self._pdf or not self.preview.is_ready():
            self._set_status("请先打开 PDF。")
            return
        page = self.preview.current_page()
        # 把当前预览页设为"正文第 1 页"：page_idx = 1 + offset - 1 = page-1
        self.offset_spin.setValue(page - 1)
        self._set_status(f"已将第 {page} 页设为正文第 1 页（页码偏移 = {page - 1}）。")

    # ── OCR ────────────────────────────────────────────────────────────────
    def _on_ocr_btn(self) -> None:
        # 识别中点击 = 停止；否则 = 开始（仿 Claude 发送/停止键）
        if self._ocr_worker is not None:
            self._cancel_ocr()
        else:
            self._start_ocr()

    def _start_ocr(self) -> None:
        if not self._pdf or not self._pdf_path:
            self._set_status("请先打开 PDF。")
            return
        token = self.token_edit.text().strip()
        if not token:
            QMessageBox.warning(self, "缺少 Token", "请先填写 API Token。")
            return

        start, end = self.start_spin.value(), self.end_spin.value()
        if end < start:
            QMessageBox.warning(self, "范围无效", "目录页「到」不能小于「从」。")
            return
        count = end - start + 1
        if count > MAX_OCR_PAGES:
            QMessageBox.warning(
                self, "范围过大",
                f"一次最多识别 {MAX_OCR_PAGES} 页（当前选了 {count} 页）。\n"
                "目录通常只有几页，请确认框选的是目录页而不是整本书。",
            )
            return

        try:
            tmp = self._pdf.extract_pages(start, end)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "抽取失败", str(exc))
            return

        self.ocr_btn.setText("■ 停止识别")
        self._set_status("识别中…")

        backend = OCR_BACKENDS[self.backend_combo.currentText()]
        worker = OcrWorker(tmp, token, backend)
        self._ocr_worker = worker
        self._ocr_workers.add(worker)
        worker.progress.connect(self._on_ocr_progress)
        worker.done.connect(self._on_ocr_done)
        worker.failed.connect(self._on_ocr_failed)
        # 线程真正结束后再清理临时文件并归还 C++ 对象，避免“运行中被销毁”崩溃
        worker.finished.connect(lambda: self._reap_worker(worker))
        worker.start()

    def _cancel_ocr(self) -> None:
        # 网络请求无法硬中断：放弃当前结果归属并恢复界面；后台线程跑完后由 _reap_worker 回收。
        self._reset_ocr_ui()
        self._set_status("已取消识别。")

    def _on_ocr_progress(self, message: str) -> None:
        if self.sender() is not self._ocr_worker:  # 来自已放弃的旧任务，忽略
            return
        self._set_status(message)

    def _on_ocr_done(self, text: str) -> None:
        if self.sender() is not self._ocr_worker:  # 已取消 / 已切换文件，丢弃过期结果
            return
        self.editor.setPlainText(auto_format(text))
        self._reset_ocr_ui()
        self._set_status("识别完成，已自动格式化层级，请核对。")

    def _on_ocr_failed(self, message: str) -> None:
        if self.sender() is not self._ocr_worker:
            return
        self._reset_ocr_ui()
        self._set_status(f"识别失败：{message}")
        QMessageBox.critical(self, "识别失败", message)

    def _reset_ocr_ui(self) -> None:
        """放弃当前 worker 的结果归属并复位按钮；后台线程仍会自行跑完并回收。"""
        self._ocr_worker = None
        self.ocr_btn.setText("识别选定页")

    def _reap_worker(self, worker: OcrWorker) -> None:
        # finished 已触发 → 线程确已结束，可安全删除临时文件并释放对象
        if worker.pdf_path and os.path.exists(worker.pdf_path):
            try:
                os.remove(worker.pdf_path)
            except OSError:
                pass
        self._ocr_workers.discard(worker)
        worker.deleteLater()

    # ── 写入 ────────────────────────────────────────────────────────────────
    def _write_toc(self) -> None:
        if not self._pdf_path:
            QMessageBox.warning(self, "无文件", "请先打开 PDF。")
            return
        text = self.editor.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "无内容", "目录为空，无法写入。")
            return

        if self.editor.error_count() > 0:
            ans = QMessageBox.question(
                self, "存在问题行",
                f"有 {self.editor.error_count()} 行被标红（页码越界或无法解析），仍要继续吗？",
            )
            if ans != QMessageBox.StandardButton.Yes:
                return

        try:
            dest = write_bookmarks_to_pdf(self._pdf_path, text, self.offset_spin.value())
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "写入失败", str(exc))
            self._set_status(f"写入失败：{exc}")
            return

        self._set_status(f"已写入：{dest}")
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("完成")
        box.setText(f"书签已写入：\n{dest}")
        open_btn = box.addButton("打开所在文件夹", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("关闭", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(dest)))

    # ── 编辑器辅助 ─────────────────────────────────────────────────────────────
    def _auto_format(self) -> None:
        self.editor.setPlainText(auto_format(self.editor.toPlainText()))

    def _load_example(self) -> None:
        self.editor.setPlainText(EXAMPLE_TOC)

    def _import_toc(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "导入目录文本", self._config.get("last_dir", ""), "文本 (*.txt);;所有文件 (*)"
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                self.editor.setPlainText(f.read())
            self._set_status(f"已导入：{os.path.basename(path)}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "导入失败", str(exc))

    def _export_toc(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "导出目录文本", self._config.get("last_dir", "toc.txt"), "文本 (*.txt)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.editor.toPlainText())
            self._set_status(f"已导出：{os.path.basename(path)}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "导出失败", str(exc))

    def _on_offset_change(self, value: int) -> None:
        self.editor.set_offset(value)

    def _on_errors_changed(self, count: int) -> None:
        if count:
            self.error_label.setText(f"⚠ {count} 行存在问题")
        elif not self.editor.toPlainText().strip():
            self.error_label.setText("")
        elif self._pdf is None:
            # 还没打开 PDF，页码无从校验——别用绿勾误导用户以为已通过
            self.error_label.setText("")
        else:
            self.error_label.setText("✓ 目录校验通过")

    def _on_token_change(self, text: str) -> None:
        # 只更新内存，避免每敲一个字就同步写一次配置文件；退出 / 切文件 / 切主题时统一落盘
        self._config["token"] = text

    def _toggle_token_visibility(self) -> None:
        hidden = self.token_edit.echoMode() == QLineEdit.EchoMode.Password
        self.token_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if hidden else QLineEdit.EchoMode.Password
        )
        self._update_eye_icon()

    def _update_eye_icon(self) -> None:
        showing = self.token_edit.echoMode() == QLineEdit.EchoMode.Normal
        self._eye_action.setIcon(make_eye_icon(self._palette, off=showing))

    # ── 主题 / 帮助 / 持久化 ────────────────────────────────────────────────────
    def _apply_theme(self) -> None:
        self._palette = Palette(self._dark)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_qss(self._palette))
        self.preview.set_canvas_color(self._palette.canvas)
        self.editor.set_theme(self._palette)
        self.backend_combo.set_theme(self._palette)
        self._update_eye_icon()

    def _toggle_theme(self) -> None:
        self._dark = not self._dark
        self._config["theme"] = "dark" if self._dark else "light"
        save_config(self._config)
        self.theme_btn.setText("☀️ 浅色" if self._dark else "🌙 深色")
        self._apply_theme()

    def _show_help(self) -> None:
        QMessageBox.information(
            self, "使用帮助",
            "1. 打开或拖入整本 PDF\n"
            "2. 预览翻到目录页，标记起始 / 结束\n"
            "3. 填 Token，点「识别选定页」\n"
            "4. 在右侧编辑目录，红色行 = 页码有误\n"
            "5. 翻到正文第 1 页，点「用当前页为正文首页」\n"
            "6. 点「写入书签到 PDF」生成副本",
        )

    def _info(self, text: str) -> None:
        # 简洁提示，按钮居中
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("提示")
        box.setText(text)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.button(QMessageBox.StandardButton.Ok).setText("确定")
        label = box.findChild(QLabel, "qt_msgbox_label")
        if label is not None:
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bb = box.findChild(QDialogButtonBox)
        if bb is not None:
            bb.setCenterButtons(True)
        box.exec()

    def _set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def _restore_geometry(self) -> None:
        geo = self._config.get("geometry")
        if geo:
            try:
                # restoreGeometry 对损坏数据返回 False 而非抛错；返回值未成功才回退默认尺寸
                if self.restoreGeometry(QByteArray.fromBase64(geo.encode("ascii"))):
                    return
            except Exception:  # noqa: BLE001
                pass
        self.resize(1240, 760)

    # ── 拖拽打开 ───────────────────────────────────────────────────────────────
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls() and any(
            u.toLocalFile().lower().endswith(".pdf") for u in event.mimeData().urls()
        ):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".pdf"):
                self._open_pdf(path)
                break

    def closeEvent(self, event) -> None:
        # 等识别线程跑完再退出，否则销毁运行中的 QThread 会导致进程崩溃
        for worker in list(self._ocr_workers):
            worker.wait(5000)
        self._config["geometry"] = bytes(self.saveGeometry().toBase64()).decode("ascii")
        save_config(self._config)
        super().closeEvent(event)


# ── 小工厂 ──────────────────────────────────────────────────────────────────

def _section(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("Panel")
    box = QVBoxLayout(frame)
    box.setContentsMargins(14, 12, 14, 14)
    box.setSpacing(8)
    label = QLabel(title)
    label.setObjectName("SectionLabel")
    box.addWidget(label)
    return frame, box


def _primary(text: str, slot) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("Primary")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.clicked.connect(slot)
    return btn


def _button(text: str, slot) -> QPushButton:
    btn = QPushButton(text)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.clicked.connect(slot)
    return btn


def _chip(text: str, slot) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("Chip")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.clicked.connect(slot)
    return btn


def _spin(minimum: int, value: int, maximum: int | None = None, width: int = 96) -> QSpinBox:
    spin = QSpinBox()
    spin.setMinimum(minimum)
    spin.setMaximum(maximum if maximum is not None else 1)
    spin.setValue(value)
    spin.setMinimumWidth(width)  # 容纳多位数 + 步进器，避免数字被遮挡
    return spin


def run() -> None:
    import sys


    app = QApplication(sys.argv)
    app.setApplicationName("PDF TOC Writer")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
