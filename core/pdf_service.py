"""PDF 服务层：封装"打开 / 取页文本 / 抽取页范围 / 自动检测目录页"。

UI 只依赖本服务，便于后续测试与复用（见 plan.md 第 2 部分）。
"""
import os
import re
import tempfile

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:  # pragma: no cover - 兼容旧环境
    from PyPDF2 import PdfReader, PdfWriter  # type: ignore

# 命中这些关键词的页大概率是目录页
_TOC_KEYWORDS = re.compile(r"(目\s*录|目錄|contents|table\s+of\s+contents)", re.IGNORECASE)
# 行尾页码：用于判断"大量行以页码结尾"的目录特征
_TRAILING_PAGE = re.compile(r"\d+\s*$")


class PdfService:
    """围绕单个 PDF 文件的轻量服务对象。"""

    def __init__(self, path: str) -> None:
        self.path = path
        self._reader = PdfReader(path)
        self._text_cache: dict[int, str] = {}

    @property
    def page_count(self) -> int:
        return len(self._reader.pages)

    def page_text(self, index: int) -> str:
        """返回第 index 页（0-based）的可提取文本，失败返回空串。"""
        if index in self._text_cache:
            return self._text_cache[index]
        try:
            text = self._reader.pages[index].extract_text() or ""
        except Exception:
            text = ""
        self._text_cache[index] = text
        return text

    def extract_pages(self, start: int, end: int) -> str:
        """抽取 [start, end]（1-based，含端点）到临时 PDF，返回其路径。

        供识别后端只处理目录页使用，避免对整本书 OCR。
        """
        start = max(1, start)
        end = min(self.page_count, end)
        if end < start:
            raise ValueError("目录页范围无效")

        writer = PdfWriter()
        for i in range(start - 1, end):
            writer.add_page(self._reader.pages[i])

        fd, tmp_path = tempfile.mkstemp(suffix="_tocpages.pdf")
        os.close(fd)
        with open(tmp_path, "wb") as f:
            writer.write(f)
        return tmp_path

    def detect_toc_pages(self, scan_limit: int = 40) -> tuple[int, int] | None:
        """扫描前若干页，返回猜测的目录页范围 (start, end)（1-based）或 None。

        规则：命中"目录/Contents"关键词，或该页有大量以页码结尾的行。
        """
        limit = min(scan_limit, self.page_count)
        hits = [i for i in range(limit) if self._looks_like_toc(self.page_text(i))]
        if not hits:
            return None

        # 取包含首个命中页的连续区间
        start = hits[0]
        end = start
        hit_set = set(hits)
        while end + 1 in hit_set:
            end += 1
        return start + 1, end + 1

    @staticmethod
    def _looks_like_toc(text: str) -> bool:
        if not text:
            return False
        if _TOC_KEYWORDS.search(text):
            return True
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if len(lines) < 5:
            return False
        trailing = sum(1 for ln in lines if _TRAILING_PAGE.search(ln))
        return trailing >= max(5, int(len(lines) * 0.4))
