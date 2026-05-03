import re


def detect_toc_level(title: str) -> int:
    """
    根据标题前缀推断目录层级（1-5）。

    优先级：数字序号 > 中文关键词 > 英文关键词 > 默认 1。
    """
    # 数字序号：点/连字符分隔，点数决定层级
    # 例：1→1, 1.1→2, 1.1.1→3, 1-1→2
    m = re.match(r"^(\d+(?:[.\-]\d+)*)", title)
    if m:
        dots = m.group(1).replace("-", ".").count(".")
        return min(dots + 1, 5)

    # 中文层级关键词
    CN_DIGITS = r"[零一二三四五六七八九十百千\d]+"
    if re.match(rf"^第{CN_DIGITS}[篇卷部章]", title):
        return 1
    if re.match(rf"^第{CN_DIGITS}[节]|^第{CN_DIGITS}单元", title):
        return 2
    if re.match(r"^[一二三四五六七八九十]+[、．.]", title):
        return 3
    if re.match(r"^（[一二三四五六七八九十]+）", title):
        return 3
    if re.match(r"^（\d+）|^\d+）", title):
        return 4
    if re.match(r"^[①②③④⑤⑥⑦⑧⑨⑩]", title):
        return 5
    if re.match(r"^[a-z]\.", title):
        return 5

    # 英文层级关键词
    if re.match(r"^(Part|Volume|Book|Chapter)\b", title, re.IGNORECASE):
        return 1
    if re.match(r"^(Section|Unit)\b", title, re.IGNORECASE):
        return 2
    if re.match(r"^(Subsection|Article)\b", title, re.IGNORECASE):
        return 3
    if re.match(r"^(Item|Clause)\b", title, re.IGNORECASE):
        return 4

    return 1


def auto_format(raw_text: str) -> str:
    """
    将原始目录文本按层级缩进格式化。

    每行格式应为 "标题 页码"，缩进由 detect_toc_level 决定。
    无法识别页码的行原样保留。
    """
    result = []
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            result.append("")
            continue
        m = re.match(r"^(.*?)\s+(\d+)\s*$", line)
        if not m:
            result.append(line)
            continue
        title, page = m.group(1).strip(), m.group(2)
        indent = "    " * (detect_toc_level(title) - 1)
        result.append(f"{indent}{title} {page}")
    return "\n".join(result)
