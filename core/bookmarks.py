import os
import re
import shutil


def extract_bookmarks(pdf_path: str) -> str:
    """从 PDF 书签提取目录，返回带缩进的文本。无书签返回空字符串。"""
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            return ""

    try:
        reader = PdfReader(pdf_path)
        if not reader.outline:
            return ""
        lines: list[str] = []
        _collect_outlines(reader.outline, reader, lines, level=0)
        return "\n".join(lines)
    except Exception:
        return ""


def _collect_outlines(outlines, reader, lines: list[str], level: int) -> None:
    # 递归遍历嵌套书签树，子列表代表下一层级
    for item in outlines:
        if isinstance(item, list):
            _collect_outlines(item, reader, lines, level + 1)
        else:
            try:
                title = item.title.strip()
                page_num = reader.get_destination_page_number(item) + 1
                lines.append(f"{'  ' * level}{title} {page_num}")
            except Exception:
                pass


def write_bookmarks_to_pdf(src_path: str, toc_text: str, offset: int = 0) -> str:
    """
    将 toc_text 解析为书签写入 PDF 副本（同目录，文件名加 _toc 后缀）。

    toc_text 格式：每行 "[缩进]标题 页码"，两空格缩进 = 一级子项。
    offset：书中页码与 PDF 实际页码的差值（PDF页 = 书页 + offset）。
    返回副本路径。
    """
    try:
        from pypdf import PdfWriter, PdfReader
    except ImportError:
        from PyPDF2 import PdfWriter, PdfReader

    base, ext = os.path.splitext(src_path)
    dest_path = f"{base}_toc{ext}"
    shutil.copy2(src_path, dest_path)

    total_pages = len(PdfReader(src_path).pages)

    writer = PdfWriter()
    writer.append(src_path)
    # 删除原有书签，避免与新目录重复
    writer._root_object.pop("/Outlines", None)  # type: ignore[attr-defined]

    entries = _parse_toc_text(toc_text, offset, total_pages)

    parent_stack: list = [None] * 10
    for level, title, page_idx in entries:
        parent = parent_stack[level - 1] if level > 0 else None
        bookmark = writer.add_outline_item(title, writer.pages[page_idx], parent=parent)
        parent_stack[level] = bookmark
        for i in range(level + 1, 10):
            parent_stack[i] = None

    with open(dest_path, "wb") as f:
        writer.write(f)

    return dest_path


def _parse_toc_text(
    toc_text: str, offset: int, total_pages: int
) -> list[tuple[int, str, int]]:
    """解析目录文本，返回 (层级, 标题, 0-based页码) 列表。"""
    entries = []
    for line in toc_text.splitlines():
        if not line.strip():
            continue
        stripped = line.lstrip(" ")
        level = (len(line) - len(stripped)) // 2
        m = re.match(r"^(.*?)\s+(\d+)\s*$", stripped)
        if not m:
            continue
        title = m.group(1).strip()
        page_idx = int(m.group(2)) + offset - 1
        if page_idx < 0 or page_idx >= total_pages:
            raise ValueError(
                f'页码超出范围："{title}" 对应第 {int(m.group(2)) + offset} 页，'
                f"但 PDF 共 {total_pages} 页"
            )
        entries.append((level, title, page_idx))
    return entries
