# PDF 目录书签工具

[![Release](https://img.shields.io/badge/release-v1.0.0-blue)](https://github.com/zhufeng2/pdftocwriter/releases/tag/v1.0.0)

提取、编辑并写入 PDF 文件的目录书签，支持对扫描版 PDF 进行 OCR 识别。

## 功能特性

- **单文件工作流** —— 一次打开整本书，定位、识别、写入全程无需重新裁剪或重新选择文件
- **内置 PDF 预览**（PySide6 / QtPdf）—— 可视化标记目录页范围
- **自动检测目录页** 与 **自动页码偏移**（"将当前页设为正文第 1 页"）
- 按层级自动格式化目录；支持以OCR识别方式或直接以文本形式写入目录，编辑好的目录写入 `*_toc.pdf` 副本

## 快速开始
### 从源码运行

**环境要求：** Python 3.10–3.14

```bash
git clone https://github.com/zhufeng2/pdftocwriter.git
cd pdftocwriter
pip install -r requirements.txt
python main.py
```

## 使用说明

1. 点击 **打开 PDF**，或将 PDF 拖入窗口。打开**整本书**，已有书签会自动加载。
2. 在中间的预览区翻页找到目录页。点击 **自动检测目录页**，或使用 **当前页 → 起始 / 结束** 从当前浏览的页面标记范围。
3. 输入你的 API 令牌并点击 **识别选定页** —— 仅所选的目录页会被发送进行 OCR。
4. 在右侧编辑目录（使用 **自动格式化** 按层级缩进）。页码错误的行会以红色高亮。
5. 翻到书的正文第一页，点击 **用当前页为正文首页**，自动计算页码偏移。
6. 点击 **写入书签到 PDF** —— 会在原文件旁创建一个 `*_toc.pdf` 副本。

## API 令牌

### 获取 PaddleOCR API 令牌

OCR 功能需要 PaddleOCR API 令牌。按以下步骤获取：

1. 访问 [PaddleOCR AI Studio](https://aistudio.baidu.com/paddleocr)
2. 使用百度账号注册或登录
3. 进入 API 部分，创建一个新的 API 密钥
4. 复制你的 API 令牌

### 使用令牌

- 在应用的 **API Token** 输入框中填入你的令牌
- 令牌保存在本地的 `~/.pdftocwriter.json`

## 软件截图
![界面截图](img/en.png)

