import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

from core.bookmarks import extract_bookmarks, write_bookmarks_to_pdf
from core.config import load_config, save_config
from core.ocr import extract_toc_via_ocr
from ui.toc_formatter import auto_format

EXAMPLE_TOC = (
    "Chapter 1 Introduction 1\n"
    "1.1 Background 1\n"
    "1.2 Purpose 2\n"
    "1.2.1 Scope 3\n"
    "Chapter 2 Related Work 5\n"
    "2.1 Overview 5\n"
    "2.2 Methods 8\n"
    "Chapter 3 Methodology 12\n"
)

HELP_TEXT = (
    "1. Upload a PDF file\n"
    "2. Enter your API token\n"
    "3. (Optional) Run OCR if no bookmarks\n"
    "4. Edit the table of contents\n"
    "5. Click \"Write TOC\" to save"
)

# ── Colour palette ─────────────────────────────────────────────────────────────
CLR_ACCENT  = "#5b8dee"
CLR_ACCENT2 = "#4a7de0"
CLR_BG      = "#f5f5f5"
CLR_PANEL   = "#ffffff"
CLR_BORDER  = "#e0e0e0"
CLR_BORDER2 = "#e8e8e8"
CLR_FG      = "#2d2d2d"
CLR_FG_DIM  = "#555"
CLR_FG_HINT = "#888"
CLR_FG_HELP = "#777"


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("PDF TOC Writer")
        self.geometry("1000x650")
        self.minsize(800, 500)
        self.configure(bg=CLR_BG)

        self.pdf_path: str | None = None
        self._config = load_config()

        self._set_icon()
        self._build_ui()

    # ── Icon ───────────────────────────────────────────────────────────────────

    def _set_icon(self) -> None:
        # 用 PhotoImage.put 绘制简单色块图标，无需外部文件
        icon = tk.PhotoImage(width=16, height=16)
        icon.put(CLR_ACCENT, to=(0, 0, 16, 16))
        icon.put(CLR_PANEL,  to=(3, 2, 13, 12))
        icon.put(CLR_ACCENT, to=(9, 2, 13, 6))
        self.iconphoto(True, icon)
        self._icon = icon  # 防止被 GC 回收

    # ── Layout ─────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self._build_titlebar()
        _divider(self)

        body = tk.Frame(self, bg=CLR_BG)
        body.pack(fill=tk.BOTH, expand=True)
        self._build_left(body)
        self._build_right(body)

        _divider(self)
        self._build_statusbar()

    def _build_titlebar(self) -> None:
        frame = tk.Frame(self, bg=CLR_PANEL, pady=12)
        frame.pack(fill=tk.X)
        tk.Label(
            frame,
            text="PDF TOC Writer",
            font=("Segoe UI", 16, "bold"),
            bg=CLR_PANEL, fg=CLR_FG,
        ).pack()

    def _build_statusbar(self) -> None:
        self.status_var = tk.StringVar(value="Status")
        tk.Label(
            self, textvariable=self.status_var,
            font=("Segoe UI", 9), bg="#f0f0f0", fg=CLR_FG_DIM,
            anchor="w", padx=12, pady=5,
        ).pack(fill=tk.X, side=tk.BOTTOM)

    # ── Left panel ─────────────────────────────────────────────────────────────

    def _build_left(self, parent: tk.Frame) -> None:
        left = tk.Frame(
            parent, bg=CLR_PANEL, width=240,
            highlightbackground=CLR_BORDER, highlightcolor=CLR_BORDER,
            highlightthickness=1,
        )
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(12, 6), pady=12)
        left.pack_propagate(False)

        self._build_upload_section(left)
        _divider(left, padx=10, pady=4)
        self._build_ocr_section(left)
        _divider(left, padx=10, pady=4)
        self._build_help_section(left)

    def _build_upload_section(self, parent: tk.Frame) -> None:
        _section_label(parent, "Upload PDF")
        _blue_button(parent, "Upload PDF", self._pick_file)
        self.file_label = tk.Label(
            parent, text="Current file: No file selected",
            font=("Segoe UI", 8), bg=CLR_PANEL, fg=CLR_FG_HINT,
            wraplength=210, justify="left",
        )
        self.file_label.pack(anchor="w", padx=14, pady=(4, 12))

    def _build_ocr_section(self, parent: tk.Frame) -> None:
        _section_label(parent, "OCR (Optional)")
        tk.Label(
            parent,
            text="Use OCR to recognize the table of\ncontents from scanned PDF.",
            font=("Segoe UI", 9), bg=CLR_PANEL, fg=CLR_FG_HELP,
            justify="center",
        ).pack(anchor="center", padx=14, pady=(0, 6))

        self.ocr_btn = _blue_button(parent, "Start OCR", self._start_ocr)
        self.ocr_status = tk.Label(
            parent, text="OCR status: Not run",
            font=("Segoe UI", 8), bg=CLR_PANEL, fg=CLR_FG_HINT,
        )
        self.ocr_status.pack(anchor="w", padx=14, pady=(4, 6))

        tk.Label(parent, text="API Token:",
                 font=("Segoe UI", 9), bg=CLR_PANEL, fg=CLR_FG_DIM,
                 ).pack(anchor="w", padx=14)
        self._build_token_row(parent)

    def _build_token_row(self, parent: tk.Frame) -> None:
        self.token_var = tk.StringVar(value=self._config.get("token", ""))
        self._token_visible = False

        row = tk.Frame(parent, bg=CLR_PANEL)
        row.pack(fill=tk.X, padx=14, pady=(2, 12))

        self.token_entry = tk.Entry(
            row, textvariable=self.token_var,
            font=("Segoe UI", 9), relief=tk.FLAT,
            highlightbackground="#ccc", highlightcolor="#ccc", highlightthickness=1,
            show="*",
        )
        self.token_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)

        self.eye_label = tk.Label(
            row, text="👁",
            font=("Segoe UI", 9), bg=CLR_PANEL, fg=CLR_FG_HINT,
            cursor="hand2", padx=4,
        )
        self.eye_label.pack(side=tk.LEFT, padx=(4, 0))
        self.eye_label.bind("<Button-1>", lambda _: self._toggle_token_visibility())

        self.token_var.trace_add("write", self._on_token_change)

    def _build_help_section(self, parent: tk.Frame) -> None:
        _section_label(parent, "How to use")
        tk.Label(
            parent, text=HELP_TEXT,
            font=("Segoe UI", 9), bg=CLR_PANEL, fg=CLR_FG_HELP,
            justify="left", wraplength=210,
        ).pack(anchor="w", padx=14, pady=(8, 12))

    # ── Right panel ────────────────────────────────────────────────────────────

    def _build_right(self, parent: tk.Frame) -> None:
        right = tk.Frame(parent, bg=CLR_BG)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True,
                   padx=(6, 12), pady=12)

        self._build_editor_titlerow(right)
        self._build_editor(right)
        self._build_action_bar(right)

    def _build_editor_titlerow(self, parent: tk.Frame) -> None:
        row = tk.Frame(parent, bg=CLR_BG)
        row.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            row,
            text="Edit Table of Contents",
            font=("Segoe UI", 10, "bold"), bg=CLR_BG, fg=CLR_FG,
        ).pack(side=tk.LEFT)

        for label, cmd in [
            ("Load Example", self._load_example),
            ("Clear",        self._clear_editor),
            ("Auto Format",  self._auto_format),
        ]:
            btn = tk.Label(
                row, text=label,
                font=("Segoe UI", 9), bg=CLR_BORDER2, fg="#333",
                cursor="hand2", padx=10, pady=4,
            )
            btn.pack(side=tk.RIGHT, padx=(4, 0))
            btn.bind("<Button-1>", lambda _, c=cmd: c())
            btn.bind("<Enter>", lambda _, b=btn: b.config(bg="#d0d0d0"))
            btn.bind("<Leave>", lambda _, b=btn: b.config(bg=CLR_BORDER2))

    def _build_editor(self, parent: tk.Frame) -> None:
        frame = tk.Frame(
            parent, bg=CLR_PANEL,
            highlightbackground="#d0d0d0", highlightcolor="#d0d0d0",
            highlightthickness=1,
        )
        frame.pack(fill=tk.BOTH, expand=True)

        self.editor = scrolledtext.ScrolledText(
            frame,
            font=("Consolas", 10), relief=tk.FLAT,
            bg=CLR_PANEL, fg="#222", padx=12, pady=10,
            wrap=tk.NONE, undo=True, highlightthickness=0,
        )
        self.editor.pack(fill=tk.BOTH, expand=True)

    def _build_action_bar(self, parent: tk.Frame) -> None:
        bar = tk.Frame(parent, bg=CLR_BG)
        bar.pack(fill=tk.X, pady=(8, 0))

        tk.Label(bar, text="Page offset:",
                 font=("Segoe UI", 9), bg=CLR_BG, fg=CLR_FG_DIM,
                 ).pack(side=tk.LEFT, padx=(0, 4))
        self.offset_var = tk.StringVar(value="0")
        tk.Entry(
            bar, textvariable=self.offset_var,
            font=("Segoe UI", 9), width=5, relief=tk.FLAT,
            highlightbackground="#ccc", highlightthickness=1,
        ).pack(side=tk.LEFT, ipady=4, padx=(0, 16))

        write_btn = tk.Label(
            bar, text="Write TOC to PDF",
            font=("Segoe UI", 10, "bold"), bg=CLR_ACCENT, fg="white",
            cursor="hand2", padx=20, pady=7,
        )
        write_btn.pack(side=tk.RIGHT)
        write_btn.bind("<Button-1>", lambda _: self._write_toc())
        write_btn.bind("<Enter>", lambda _: write_btn.config(bg=CLR_ACCENT2))
        write_btn.bind("<Leave>", lambda _: write_btn.config(bg=CLR_ACCENT))

    # ── Event handlers ─────────────────────────────────────────────────────────

    def _on_token_change(self, *_) -> None:
        self._config["token"] = self.token_var.get()
        save_config(self._config)

    def _toggle_token_visibility(self) -> None:
        self._token_visible = not self._token_visible
        self.token_entry.config(show="" if self._token_visible else "*")
        self.eye_label.config(fg=CLR_FG if self._token_visible else CLR_FG_HINT)

    def _pick_file(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("PDF Files", "*.pdf")])
        if not path:
            return
        self.pdf_path = path
        self.file_label.config(text=f"Current file: {os.path.basename(path)}")
        self.status_var.set(path)
        threading.Thread(target=self._load_bookmarks, daemon=True).start()

    def _load_bookmarks(self) -> None:
        bookmarks = extract_bookmarks(self.pdf_path)
        if bookmarks:
            self.after(0, self._show_in_editor, bookmarks)

    def _start_ocr(self) -> None:
        if not self.pdf_path:
            self.status_var.set("Please upload a PDF first.")
            return
        self.ocr_btn.config(text="Running...", bg="#aaa", cursor="")
        self.ocr_btn.unbind("<Button-1>")
        self.ocr_status.config(text="OCR status: Running...")
        threading.Thread(target=self._run_ocr, daemon=True).start()

    def _run_ocr(self) -> None:
        token = self.token_var.get().strip()
        if not token:
            self.after(0, messagebox.showerror, "Error", "Please enter an API token.")
            self.after(0, self.ocr_status.config, {"text": "OCR status: No token"})
            self.after(0, self._reset_ocr_btn)
            return
        try:
            text = extract_toc_via_ocr(self.pdf_path, token, progress_cb=self._set_status)
            self.after(0, self._show_in_editor, text)
            self.after(0, self.ocr_status.config, {"text": "OCR status: Done"})
            self.after(0, self.status_var.set, "OCR completed.")
        except Exception as e:
            self.after(0, self.ocr_status.config, {"text": "OCR status: Error"})
            self._set_status(f"OCR error — {e}")
        finally:
            self.after(0, self._reset_ocr_btn)

    def _reset_ocr_btn(self) -> None:
        self.ocr_btn.config(text="Start OCR", bg=CLR_ACCENT, cursor="hand2")
        self.ocr_btn.bind("<Button-1>", lambda _: self._start_ocr())

    def _write_toc(self) -> None:
        text = self.editor.get("1.0", tk.END).strip()
        if not text:
            messagebox.showerror("Error", "No content to write.")
            return
        try:
            offset = int(self.offset_var.get() or 0)
        except ValueError:
            messagebox.showerror("Error", "Page offset must be an integer.")
            return

        pdf_path = filedialog.askopenfilename(
            title="选择目标 PDF 文件",
            filetypes=[("PDF Files", "*.pdf")],
        )
        if not pdf_path:
            return

        try:
            dest = write_bookmarks_to_pdf(pdf_path, text, offset)
            self.status_var.set(f"已写入: {dest}")
        except Exception as e:
            messagebox.showerror("Error", f"写入失败: {e}")

    def _show_in_editor(self, text: str) -> None:
        self.editor.delete("1.0", tk.END)
        self.editor.insert("1.0", text)

    def _set_status(self, msg: str) -> None:
        self.after(0, self.status_var.set, msg)

    def _auto_format(self) -> None:
        self._show_in_editor(auto_format(self.editor.get("1.0", tk.END)))

    def _clear_editor(self) -> None:
        self.editor.delete("1.0", tk.END)

    def _load_example(self) -> None:
        self._show_in_editor(EXAMPLE_TOC)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _divider(parent: tk.Widget, padx: int = 0, pady: int = 0) -> None:
    tk.Frame(parent, bg=CLR_BORDER, height=1).pack(fill=tk.X, padx=padx, pady=pady)


def _section_label(parent: tk.Widget, text: str) -> None:
    tk.Label(
        parent, text=text,
        font=("Segoe UI", 10, "bold"), bg=CLR_PANEL, fg=CLR_FG,
    ).pack(anchor="w", padx=14, pady=(12, 4))


def _blue_button(parent: tk.Widget, text: str, command) -> tk.Label:
    btn = tk.Label(
        parent, text=text,
        font=("Segoe UI", 10), bg=CLR_ACCENT, fg="white",
        cursor="hand2", pady=6,
    )
    btn.pack(fill=tk.X, padx=14)
    btn.bind("<Button-1>", lambda _: command())
    btn.bind("<Enter>", lambda _: btn.config(bg=CLR_ACCENT2))
    btn.bind("<Leave>", lambda _: btn.config(bg=CLR_ACCENT))
    return btn
