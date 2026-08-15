"""
rag/pdf_parser.py - PDF 下载与文本解析
"""
import logging
import os
import random
import time
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
import requests
import yaml

logger = logging.getLogger(__name__)

PDF_DIR = Path("data/pdfs")
PDF_DIR.mkdir(parents=True, exist_ok=True)

# ===== User-Agent 池 =====
_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# ===== 代理配置 =====
_proxy_config: dict = {}


def load_proxy_config() -> dict:
    """从 config.yaml 加载代理配置"""
    global _proxy_config
    if _proxy_config:
        return _proxy_config

    config_path = Path("config.yaml")
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            _proxy_config = config.get("proxy", {})
    else:
        _proxy_config = {}
    return _proxy_config


def get_random_user_agent() -> str:
    """随机选择一个 User-Agent"""
    return random.choice(_USER_AGENTS)


def clear_proxy_env() -> None:
    """清除代理环境变量，确保 direct 模式不会继承 shell 代理。"""
    for k in (
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
    ):
        os.environ.pop(k, None)


def get_proxy() -> Optional[dict]:
    """
    根据配置获取代理。

    Returns:
        dict: {"http": "http://...", "https": "http://..."} 或 None（直接连接）
    """
    config = load_proxy_config()

    if not config.get("enabled", False):
        clear_proxy_env()
        return None

    mode = config.get("mode", "single")

    if mode == "direct":
        clear_proxy_env()
        return None

    if mode == "single":
        proxy = config.get("single_proxy")
        if proxy:
            return {"http": proxy, "https": proxy}

    elif mode == "pool":
        pool = config.get("proxy_pool", [])
        if pool:
            proxy = random.choice(pool)
            return {"http": proxy, "https": proxy}

    return None


def get_request_delay() -> float:
    """根据配置获取随机请求延迟"""
    config = load_proxy_config()
    min_delay = config.get("min_delay", 3.0)
    max_delay = config.get("max_delay", 8.0)
    return random.uniform(min_delay, max_delay)

# ===== 任务大类映射 =====
# 从 config.yaml topics 抽象出来的更高层分类
_TOPIC_CATEGORY_MAP: list[tuple[list[str], str]] = [
    # GUI agents / computer-use agents
    (["graphical user interface", "gui agent", "gui agents", "gui automation",
      "gui grounding", "gui navigation", "gui testing", "mobile gui", "desktop gui",
      "ui automation", "ui grounding", "ui instruction", "user interface",
      "web-based agent", "web agents", "web agent", "web interaction",
      "web navigation", "web task", "web support", "webpage", "website navigation",
      "computer control", "computer use", "device control", "desktop automation",
      "mobile device control", "mobile agent", "smartphone gui", "android agent",
      "android device control", "screen reading", "screen understanding"], "gui"),
    # 专病系列（优先级最高，匹配到就直接归类）
    (["yolov", "yolo11", "yolo26", "you only look once"], "yolo"),
    (["mobilenetv", "mobilenet v", "efficientnet", "efficient conv"], "mobilenet"),
    # 通用任务
    (["object detection", "3D detection", "detection"], "detection"),
    (["semantic segmentation", "instance segmentation", "panoptic segmentation",
      "video segmentation", "segmentation", "medical image segmentation"], "segmentation"),
    (["tracking", "multi-object tracking"], "tracking"),
    (["image generation", "text-to-image", "video generation", "diffusion model",
      "image editing", "image-to-image"], "generation"),
    (["vision-language model", "multimodal learning", "visual question answering",
      "image captioning", "visual grounding", "CLIP", "Segment Anything",
      "GPT-4V", "large multimodal model", "vlm"], "multimodal"),
    (["3D reconstruction", "NeRF", "point cloud", "scene understanding", "novel view"], "3d"),
    (["pose estimation", "human pose estimation"], "pose"),
    (["autonomous driving perception", "BEV perception", "LiDAR", "occupancy prediction"], "perception"),
    (["medical image classification", "medical image segmentation"], "medical"),
    (["image classification", "self-supervised learning", "vision transformer",
      "OCR", "depth estimation", "image retrieval"], "classification"),
]


def infer_category(title: str, abstract: str = "") -> str:
    """
    根据论文标题和摘要推断任务大类。

    匹配逻辑：按 _TOPIC_CATEGORY_MAP 顺序查找关键词，首次命中即返回分类名。
    全文优先：先匹配摘要，再匹配标题，命中后立即返回。
    匹配不区分大小写。
    """
    text = f"{title} {abstract}".lower()

    for keywords, category in _TOPIC_CATEGORY_MAP:
        for kw in keywords:
            if kw.lower() in text:
                return category

    return "other"


def get_pdf_dir(category: str) -> Path:
    """获取某类别的 PDF 目录，不使用日期。"""
    pdf_dir = PDF_DIR / category
    pdf_dir.mkdir(parents=True, exist_ok=True)
    return pdf_dir


def build_pdf_path(
    paper_id: str,
    title: str = "",
    abstract: str = "",
    category_override: str | None = None,
) -> tuple[Path, str]:
    """
    构建 PDF 文件路径。

    返回 (path, category)
    路径格式：data/pdfs/{category}/{paper_id}.pdf

    Args:
        paper_id: 论文 ID（用于文件名）
        title: 论文标题（用于推断分类）
        abstract: 论文摘要（用于推断分类）
        category_override: 显式保存类别；传入时跳过自动推断

    Returns:
        (PDF 文件路径, 推断出的分类名)
    """
    category = category_override or infer_category(title, abstract)
    safe_id = paper_id.replace("/", "_")
    pdf_dir = get_pdf_dir(category)
    return pdf_dir / f"{safe_id}.pdf", category


def download_pdf(
    paper_id: str,
    pdf_url: str,
    title: str = "",
    abstract: str = "",
    timeout: int = 120,
    category_override: str | None = None,
) -> tuple[Optional[Path], str]:
    """
    下载 PDF 文件到本地。

    保存路径：data/pdfs/{category}/{paper_id}.pdf
    遇到 429 限流时自动重试 1 次。

    Args:
        paper_id: 论文 ID
        pdf_url: PDF 下载地址
        title: 论文标题（用于推断分类）
        abstract: 论文摘要（用于推断分类）
        timeout: 超时秒数
        category_override: 显式保存类别；传入时跳过自动推断

    Returns:
        (PDF 文件路径, 分类名)，失败时 (None, category)
    """
    path, category = build_pdf_path(paper_id, title, abstract, category_override)

    if path.exists() and path.stat().st_size > 1024:
        logger.debug(f"PDF 已存在，跳过下载: {path.name}")
        return path, category

    proxy = get_proxy()
    max_retries = 2

    for attempt in range(max_retries + 1):
        try:
            # 每次请求使用随机 User-Agent
            headers = {
                "User-Agent": get_random_user_agent(),
                "Accept": "application/pdf,application/octet-stream",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://arxiv.org/",
            }

            logger.info(f"下载 PDF: {paper_id} <- {pdf_url} (attempt {attempt + 1}/{max_retries + 1})")
            if proxy:
                logger.debug(f"使用代理: {proxy.get('http', 'N/A')}")

            response = requests.get(
                pdf_url,
                headers=headers,
                proxies=proxy,
                timeout=timeout,
                stream=True,
            )
            response.raise_for_status()

            path.write_bytes(response.content)

            if path.stat().st_size < 1024:
                logger.warning(f"PDF 文件太小，可能是错误页面: {path}")
                path.unlink(missing_ok=True)
                return None, category

            logger.info(f"PDF 下载成功: {path} ({path.stat().st_size / 1024:.1f} KB)")
            return path, category

        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                if attempt >= max_retries:
                    logger.warning(f"PDF 下载 429 限流，已达到最大重试次数: {paper_id}")
                    return None, category

                wait = 5 + random.uniform(0, 3)
                logger.warning(
                    f"PDF 下载 429 限流，等待 {wait:.0f}s 后重试（第 {attempt + 1}/{max_retries} 次）..."
                )
                time.sleep(wait)
                continue
            logger.error(f"PDF 下载 HTTP 错误: {paper_id} - {e}")
            return None, category

        except requests.exceptions.Timeout:
            logger.error(f"PDF 下载超时: {paper_id}")
            return None, category

        except (requests.exceptions.ConnectionError, requests.exceptions.SSLError) as e:
            if attempt >= max_retries:
                logger.error(f"PDF 下载连接失败: {paper_id} - {e}")
                return None, category
            wait = 3 + random.uniform(0, 2)
            logger.warning(
                "PDF 下载连接中断，等待 %.0fs 后重试（第 %d/%d 次）: %s",
                wait,
                attempt + 1,
                max_retries,
                paper_id,
            )
            time.sleep(wait)
            continue

        except Exception as e:
            logger.error(f"PDF 下载失败: {paper_id} - {e}")
            return None, category

    logger.error(f"PDF 下载失败（已达最大重试次数）: {paper_id}")
    return None, category


def parse_pdf_text(pdf_path: Path, max_pages: int = 0) -> str:
    """
    从 PDF 中提取全文文本

    Args:
        pdf_path: PDF 文件路径
        max_pages: 最多解析多少页（0 = 不限制）

    Returns:
        PDF 全文文本
    """
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)

        if max_pages > 0 and total_pages > max_pages:
            total_pages = max_pages
            logger.debug(f"限制解析页数: {max_pages} / {len(doc)}")

        texts = []
        for i, page in enumerate(doc[:total_pages]):
            text = page.get_text("text")
            if text.strip():
                texts.append(text)

        doc.close()

        full_text = "\n".join(texts)
        logger.debug(f"PDF 解析完成: {pdf_path.name}, {len(full_text)} 字符")
        return full_text

    except Exception as e:
        logger.error(f"PDF 解析失败: {pdf_path} - {e}")
        return ""


def extract_sections(text: str) -> dict[str, str]:
    """
    简单按章节分割论文文本

    常见章节关键词：Abstract, 1 Introduction, 2 Related Work, 3 Method, ...
    """
    import re

    sections = {}
    current_section = "preamble"
    current_content: list[str] = []

    # 匹配各种章节标题格式
    section_patterns = [
        r"(?m)^(?:Abstract|摘要)\s*$",
        r"(?m)^(?:1\s+)?(?:Introduction|简介|引言)\s*$",
        r"(?m)^(?:2\s+)?(?:Related Work|相关工作)\s*$",
        r"(?m)^(?:3\s+)?(?:Method|Methodology|方法)\s*$",
        r"(?m)^(?:4\s+)?(?:Experiment|实验)\s*$",
        r"(?m)^(?:5\s+)?(?:Conclusion|结论|总结)\s*$",
        r"(?m)^(?:References|参考文献)\s*$",
    ]

    section_names = [
        "abstract", "introduction", "related_work",
        "method", "experiment", "conclusion", "references"
    ]

    lines = text.split("\n")
    for line in lines:
        matched = False
        for pattern, name in zip(section_patterns, section_names):
            if re.search(pattern, line, re.IGNORECASE):
                if current_content:
                    sections[current_section] = "\n".join(current_content)
                current_section = name
                current_content = []
                matched = True
                break
        if not matched:
            current_content.append(line)

    if current_content:
        sections[current_section] = "\n".join(current_content)

    return sections


def get_pdf_page_count(pdf_path: Path) -> int:
    """获取 PDF 页数"""
    try:
        doc = fitz.open(pdf_path)
        count = len(doc)
        doc.close()
        return count
    except Exception:
        return 0
