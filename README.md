# PDF TOC Writer

[![Release](https://img.shields.io/badge/release-v1.0.0-blue)](https://github.com/zhufeng2/pdftocwriter/releases/tag/v1.0.0)

Extract, edit, and write table of contents bookmarks into PDF files. Supports OCR for scanned PDFs.

## Features

- **Single-file workflow** — open the whole book once; locate, recognize and write without re-cropping or re-selecting the file
- **Built-in PDF preview** (PySide6 / QtPdf) — thumbnail navigation + page view; mark the TOC page range visually
- **Auto-detect TOC pages** and **auto page-offset** ("set current page as body page 1")
- Auto-load existing PDF bookmarks into the editor
- TOC editor with level-aware highlighting, monospace font and **real-time validation** (out-of-range / unparsable lines are flagged)
- Auto-format the TOC by hierarchy level; import / export TOC as text
- OCR via PaddleOCR API — only the selected TOC pages are sent
- Light / dark theme, remembers window size
- Write the edited TOC as bookmarks into a `*_toc.pdf` copy

## Quick Start

### Download Executable (Windows)

Download the latest release from [GitHub Releases](https://github.com/zhufeng2/pdftocwriter/releases):
- `PDFTOCWriter.exe` — Standalone executable, no Python installation required

### From Source

**Requirements:** Python 3.10–3.14

```bash
git clone https://github.com/zhufeng2/pdftocwriter.git
cd pdftocwriter
pip install -r requirements.txt
python main.py
```

## Usage

1. Click **打开 PDF** (Open PDF) — or drag a PDF onto the window. Open the **whole book**; existing bookmarks load automatically.
2. In the center preview, page through to find the contents pages. Click **自动检测目录页** (auto-detect), or use **当前页 → 起始 / 结束** to mark the range from the page you are viewing.
3. Enter your API token and click **识别选定页** (Recognize) — only the selected TOC pages are sent to OCR.
4. Edit the TOC on the right (use **自动格式化** to indent by level). Lines with bad page numbers are highlighted in red.
5. Turn to the book's first body page and click **用当前页为正文首页** to compute the page offset automatically.
6. Click **写入书签到 PDF** (Write) — a `*_toc.pdf` copy is created next to the original, no second file picker.

## TOC Format

Each line follows `Title PageNumber`. Six-space indentation marks a sub-level:

```
Chapter 1 Introduction 1
      1.1 Background 1
      1.2 Purpose 2
            1.2.1 Scope 3
Chapter 2 Related Work 5
```

Auto Format detects the heading prefix (`1.1.1`, `Chapter`, `Section`, etc.) and applies indentation automatically.

## Screenshots
![English Interface](img/en.png)

## Building from Source

### Prerequisites

```bash
pip install pyinstaller -r requirements.txt
```

### Build Executable

```bash
pyinstaller PDFTOCWriter.spec
```

Output: `dist/PDFTOCWriter/PDFTOCWriter.exe`

For a single-file executable, modify `PDFTOCWriter.spec` and set `onefile=True` in the EXE section.

## API Token

### Getting Your PaddleOCR API Token

The OCR feature requires a PaddleOCR API token. Follow these steps to get one:

1. Visit [PaddleOCR AI Studio](https://aistudio.baidu.com/paddleocr)
2. Sign up or log in with your Baidu account
3. Navigate to the API section and create a new API key
4. Copy your API token

### Using the Token

- Enter your token in the app's **API Token** field
- The token is stored locally in `~/.pdftocwriter.json` (outside the project directory, not tracked by git)
- Your token is never uploaded or shared

## Changelog

### v1.0.0 (2026-05-01)
- Initial release
- PDF bookmark extraction and editing
- OCR support for scanned PDFs
- Auto-formatting for table of contents
- Windows executable available

## License

MIT
