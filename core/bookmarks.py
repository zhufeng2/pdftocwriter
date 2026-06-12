import os
import re

INDENT = "      "  # 一级缩进 = 6 空格，层级视觉上更分明
INDENT_WIDTH = len(INDENT)

# 目录行文法：标题 + 末尾页码。三处（校验 / 解析 / 自动格式化）共用，避免各写一份后漂移。
TOC_LINE_RE = re.compile(r"^(.*?)\s+(\d+)\s*$")


def _leading_indent(line: str) -> int:
    """前导空白宽度；Tab 折算为一个缩进单位，避免 Tab 缩进被当成 0 级。"""
    width = 0
    for ch in line:
        if ch == " ":
            width += 1
        elif ch == "\t":
            width += INDENT_WIDTH
        else:
            break
    return width


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
                lines.append(f"{INDENT * level}{title} {page_num}")
            except Exception:
                pass


def write_bookmarks_to_pdf(src_path: str, toc_text: str, offset: int = 0) -> str:
    """
    将 toc_text 解析为书签写入 PDF 副本（同目录，文件名加 _toc 后缀）。

    toc_text 格式：每行 "[缩进]标题 页码"，每 6 空格缩进 = 一级子项。
    offset：书中页码与 PDF 实际页码的差值（PDF页 = 书页 + offset）。
    返回副本路径。
    """
    try:
        from pypdf import PdfWriter, PdfReader
    except ImportError:
        from PyPDF2 import PdfWriter, PdfReader

    total_pages = len(PdfReader(src_path).pages)
    # 先解析校验，再落盘：页码越界会在此抛错，避免留下一个没有书签的副本冒充成功输出。
    entries = _parse_toc_text(toc_text, offset, total_pages)

    base, ext = os.path.splitext(src_path)
    dest_path = f"{base}_toc{ext}"

    writer = PdfWriter()
    writer.append(src_path)
    # 删除原有书签，避免与新目录重复
    writer._root_object.pop("/Outlines", None)  # type: ignore[attr-defined]

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


def validate_toc_text(
    toc_text: str, offset: int, total_pages: int
) -> dict[int, str]:
    """逐行校验目录文本，返回 {行号(0-based): 错误信息}。

    用于编辑器实时标红，不抛异常。空行忽略。
    """
    errors: dict[int, str] = {}
    for idx, line in enumerate(toc_text.splitlines()):
        if not line.strip():
            continue
        stripped = line.lstrip(" \t")
        m = TOC_LINE_RE.match(stripped)
        if not m:
            errors[idx] = "无法解析页码"
            continue
        page = int(m.group(2)) + offset
        if page < 1 or page > total_pages:
            errors[idx] = f"页码 {page} 超出范围（共 {total_pages} 页）"
    return errors


def _parse_toc_text(
    toc_text: str, offset: int, total_pages: int
) -> list[tuple[int, str, int]]:
    """解析目录文本，返回 (层级, 标题, 0-based页码) 列表。

    层级按「相对缩进」推断：缩进比上一层深就下钻一级，比它浅就回退。
    这样无论一级缩进是 2 / 4 / 6 个空格还是 Tab 都能正确分层，旧版本（4 空格）
    导出的目录重新导入时不会被压平。
    """
    entries = []
    indent_stack: list[int] = []  # 每个元素是某一层级的前导缩进宽度，栈深 = 层级 + 1
    for line in toc_text.splitlines():
        if not line.strip():
            continue
        stripped = line.lstrip(" \t")
        m = TOC_LINE_RE.match(stripped)
        if not m:
            continue  # 无法解析的行不参与层级推断，避免污染缩进栈
        indent = _leading_indent(line)
        while indent_stack and indent < indent_stack[-1]:
            indent_stack.pop()
        if not indent_stack or indent > indent_stack[-1]:
            indent_stack.append(indent)
        level = len(indent_stack) - 1
        title = m.group(1).strip()
        page_idx = int(m.group(2)) + offset - 1
        if page_idx < 0 or page_idx >= total_pages:
            raise ValueError(
                f'页码超出范围："{title}" 对应第 {int(m.group(2)) + offset} 页，'
                f"但 PDF 共 {total_pages} 页"
            )
        entries.append((level, title, page_idx))
    return entries
