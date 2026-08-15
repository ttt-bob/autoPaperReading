#!/usr/bin/env python3
"""
jobs/ingest_url.py - 通过论文 URL / arXiv ID / 任意 PDF 链接抓取并总结单篇论文

支持的输入格式：
  - arXiv URL:  https://arxiv.org/abs/1706.03762
  - arXiv ID:   1706.03762
  - 任意 PDF:   https://proceedings.neurips.cc/paper_files/paper/2012/.../Paper.pdf

对于非 arXiv 的 PDF，脚本会：
  1. 下载 PDF 并解析文本
  2. 从文本中提取标题、作者（从 PDF 元数据或文本推断）
  3. 调用 LLM 从全文生成结构化总结

用法:
    uv run python jobs/ingest_url.py https://arxiv.org/abs/1706.03762
    uv run python jobs/ingest_url.py 1706.03762
    uv run python jobs/ingest_url.py https://proceedings.neurips.cc/paper_files/paper/2012/...
    uv run python jobs/ingest_url.py URL --force   # 强制重新总结
"""
import sys
import os

# 强制清除代理环境变量（防止 clash 等本地代理干扰 arXiv API 和 requests）
for _k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
           "all_proxy", "ALL_PROXY", "no_proxy", "NO_PROXY"):
    os.environ.pop(_k, None)
    os.environ.pop(_k.lower(), None)

import logging
import argparse
import re
import hashlib
import requests
from pathlib import Path
import shutil  # for file copy

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
import arxiv
import fitz  # PyMuPDF
from rag import db, pdf_parser, summarizer, tag_utils

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ingest_url")


# ============================================================
# 步骤一：解析输入为统一类型
# ============================================================

class InputKind:
    ARXIV = "arxiv"       # 有 arXiv ID 的 URL
    PDF_URL = "pdf_url"   # 任意 PDF URL


def parse_input(raw: str) -> tuple[InputKind, str, str | None]:
    """
    解析任意格式的输入，返回 (类型, 原始输入, arXiv ID 或 None)

    支持的格式:
      - https://arxiv.org/abs/1706.03762        → (ARXIV, raw, "1706.03762")
      - https://arxiv.org/abs/1706.03762v2      → (ARXIV, raw, "1706.03762")
      - https://arxiv.org/html/1706.03762v2     → (ARXIV, raw, "1706.03762")
      - https://arxiv.org/pdf/1706.03762.pdf    → (ARXIV, raw, "1706.03762")
      - 1706.03762                               → (ARXIV, raw, "1706.03762")
      - https://xxx.pdf / https://xxx/Paper.pdf  → (PDF_URL, raw, None)
    """
    raw = raw.strip()

    # 1. 尝试提取 arXiv ID（优先）
    arxiv_id = _extract_arxiv_id(raw)
    if arxiv_id:
        return InputKind.ARXIV, raw, arxiv_id

    # 2. 任意 HTTP(S) PDF / 下载链接。有些出版站点的下载端点并不以 .pdf 结尾，
    #    例如 /article/download/...、/pdfft?... 或 /stamp/stamp.jsp?....
    if _looks_like_paper_url(raw):
        return InputKind.PDF_URL, raw, None

    raise ValueError(
        f"无法识别输入格式: '{raw}'\n"
        f"  支持: arXiv URL (https://arxiv.org/abs/...), "
        f"arXiv ID (1706.03762), 或任意 HTTP(S) PDF / 下载链接"
    )


def _extract_arxiv_id(raw: str) -> str | None:
    """从字符串中提取 arXiv ID，返回不含版本号的 API 查询 ID。"""
    arxiv_id_pattern = r"(\d{4}\.\d{4,5})(?:v\d+)?"

    # arXiv URL: /abs/、/pdf/ 或 /html/ 后缀
    m = re.search(
        rf"arxiv\.org/(?:abs|pdf|html)/{arxiv_id_pattern}(?:\.pdf)?",
        raw,
        re.IGNORECASE,
    )
    if m:
        return m.group(1)

    # 直接是纯 ID: 1706.03762 / 1706.03762v2
    m = re.match(rf"^{arxiv_id_pattern}$", raw.strip(), re.IGNORECASE)
    if m:
        return m.group(1)

    return None


def _looks_like_paper_url(raw: str) -> bool:
    """判断是否为可交给下载器处理的 HTTP(S) 论文链接。"""
    return re.match(r"^https?://\S+$", raw, re.IGNORECASE) is not None


# ============================================================
# 步骤二：从不同来源获取论文元数据
# ============================================================

def fetch_arxiv_paper(arxiv_id: str) -> dict:
    """通过 arXiv API 获取论文元数据"""
    client = arxiv.Client(page_size=1, delay_seconds=1.0, num_retries=3)

    search = arxiv.Search(
        query=f"id:{arxiv_id}",
        max_results=1,
        sort_by=arxiv.SortCriterion.Relevance,
    )

    results = list(client.results(search))
    if not results:
        raise RuntimeError(f"arXiv 上未找到论文: {arxiv_id}")

    result = results[0]

    def _clean(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    return {
        "paper_id": result.get_short_id(),
        "title": _clean(result.title),
        "authors": ", ".join(a.name for a in result.authors),
        "abstract": _clean(result.summary),
        "published": result.published.isoformat(),
        "updated": (
            result.updated.isoformat()
            if hasattr(result, "updated")
            else result.published.isoformat()
        ),
        "pdf_url": result.pdf_url,
        "entry_url": result.entry_id,
        "comment": getattr(result, "comment", "") or "",
        "doi": getattr(result, "doi", "") or "",
        "journal_ref": getattr(result, "journal_ref", "") or "",
        "primary_category": result.primary_category,
        "categories": ", ".join(result.categories),
    }


def _build_pdf_url_download_path(pdf_url: str, save_category: str | None = None) -> tuple[str, Path]:
    """为 PDF URL 构建稳定 paper_id 和下载路径。"""
    safe_name = hashlib.sha256(pdf_url.encode()).hexdigest()[:16]
    paper_id = f"pdf_{safe_name}"
    path, _ = pdf_parser.build_pdf_path(paper_id, category_override=save_category)
    return paper_id, path


def fetch_metadata_from_pdf(pdf_url: str, config: dict, save_category: str | None = None) -> dict:
    """
    从任意 PDF URL 下载并解析元数据。

    策略：
      1. 下载 PDF 到临时目录
      2. 从 PDF 元数据（Title / Author）读取基本信息
      3. 若 PDF 元数据不足，从首页文本中提取
      4. 用 LLM 从首页推断标题、作者、摘要（兜底）
      5. 生成一个稳定的 paper_id（URL 的 SHA256 前缀）
    """
    logger.info(f"📥 下载 PDF: {pdf_url}")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        )
    }
    resp = requests.get(pdf_url, headers=headers, timeout=120, stream=True)
    resp.raise_for_status()

    content = resp.content
    if len(content) < 1024:
        raise RuntimeError(f"PDF 文件太小，可能是错误页面")

    paper_id, tmp_path = _build_pdf_url_download_path(pdf_url, save_category)
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path.write_bytes(content)
    logger.info(f"   保存至: {tmp_path} ({len(content) / 1024:.0f} KB)")

    # --- 从 PDF 元数据读取 ---
    safe_name = paper_id.removeprefix("pdf_")
    title = ""
    authors = ""
    abstract = ""

    try:
        doc = fitz.open(tmp_path)
        # 读取 PDF 标准元数据
        meta = doc.metadata
        title = (meta.get("title") or "").strip()
        author_str = meta.get("author") or ""
        authors = author_str.strip()

        # 解析首页文本（找标题、作者）
        if len(doc) > 0:
            first_page_text = doc[0].get_text("text")
            title_candidates = _extract_title_from_text(first_page_text)
            if title_candidates and (not title or len(title_candidates) > len(title)):
                title = title_candidates

        doc.close()
    except Exception as e:
        logger.warning(f"   PDF 元数据解析失败: {e}，将使用 LLM 推断")
        first_page_text = ""
        # 从临时文件读取首页文本
        try:
            doc = fitz.open(tmp_path)
            if len(doc) > 0:
                first_page_text = doc[0].get_text("text")
            doc.close()
        except Exception:
            pass

    # --- LLM 推断元数据（兜底）---
    if not title or len(title) < 5:
        logger.info("   PDF 元数据不足，调用 LLM 从首页推断元数据...")
        title, authors, abstract = _llm_infer_metadata(pdf_url, tmp_path, config)

    if not title:
        title = f"Unknown Paper ({safe_name})"

    logger.info(f"   标题: {title[:80]}")
    if authors:
        logger.info(f"   作者: {authors[:80]}")

    return {
        "paper_id": paper_id,
        "title": title,
        "authors": authors or "Unknown",
        "abstract": abstract or "",
        "published": "unknown",
        "updated": "unknown",
        "pdf_url": pdf_url,
        "entry_url": pdf_url,
        "comment": "",
        "doi": "",
        "journal_ref": "",
        "primary_category": save_category or "other",
        "categories": save_category or "other",
        "_tmp_pdf_path": str(tmp_path),  # 供 process_paper 复用
    }


def _extract_title_from_text(text: str) -> str:
    """从 PDF 首页文本中提取标题（粗略）"""
    if not text:
        return ""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    # 跳过太短的行，第一条长行通常是标题
    for line in lines[:10]:
        if 10 < len(line) < 300 and not line.startswith(("http", "www", "doi")):
            # 过滤掉明显不是标题的
            lower = line.lower()
            if any(kw in lower for kw in ["abstract", "introduction", "fig.", "figure", "table", "http"]):
                continue
            return line
    return ""


def _llm_infer_metadata(pdf_url: str, pdf_path: Path, config: dict) -> tuple[str, str, str]:
    """用 LLM 从 PDF 首页推断标题、作者、摘要"""
    llm_cfg = config.get("llm", {})
    model = llm_cfg.get("model", "deepseek-v4-flash")

    # 读取首页文本（限制长度）
    try:
        doc = fitz.open(pdf_path)
        first_pages_text = ""
        for page in doc[:3]:  # 取前 3 页，应该足够找到标题和摘要
            first_pages_text += page.get_text("text")
        doc.close()
        first_pages_text = first_pages_text[:5000]  # 限制 token
    except Exception:
        first_pages_text = "(无法读取 PDF 文本)"

    prompt = f"""这是一篇学术论文的首页/前几页文本。请从中提取：

1. 论文标题（title）：原文，不要翻译
2. 作者列表（authors）：原文，逗号分隔，只写名字
3. 论文摘要（abstract）：如果文本中有摘要部分就复制原文，没有就写"无"

只输出以下格式，不要添加任何解释或说明：

TITLE: xxx
AUTHORS: xxx
ABSTRACT: xxx"""

    try:
        from rag.llm_client import chat
        resp = chat(
            prompt=prompt + f"\n\n---论文首页文本---\n{first_pages_text}",
            model=model,
            system="你是一个学术论文元数据提取助手。",
        )

        title_m = re.search(r"TITLE:\s*(.+?)(?=AUTHORS:|$)", resp, re.DOTALL)
        authors_m = re.search(r"AUTHORS:\s*(.+?)(?=ABSTRACT:|$)", resp, re.DOTALL)
        abstract_m = re.search(r"ABSTRACT:\s*(.+)", resp, re.DOTALL)

        title = (title_m.group(1).strip() if title_m else "").split("\n")[0]
        authors = (authors_m.group(1).strip() if authors_m else "").split("\n")[0]
        abstract = (abstract_m.group(1).strip() if abstract_m else "")

        return title, authors, abstract
    except Exception as e:
        logger.warning(f"   LLM 元数据推断失败: {e}")
        return "", "", ""


# ============================================================
# 步骤三：处理论文（下载 PDF / 总结 / 入库）
# ============================================================

def load_config() -> dict:
    cfg_path = Path("config.yaml")
    if not cfg_path.exists():
        return {}
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_inputs(cli_inputs: list[str], from_file: str | None = None) -> list[str]:
    """合并命令行输入和文件输入；文件中空行及 # 注释会被忽略。"""
    inputs = [i.strip() for i in cli_inputs if i.strip()]
    if from_file:
        path = Path(from_file)
        for line in path.read_text(encoding="utf-8").splitlines():
            item = line.strip()
            if item and not item.startswith("#"):
                inputs.append(item)
    return inputs


def process_paper(
    paper: dict,
    config: dict,
    force: bool = False,
    skip_summary: bool = False,
    save_category: str | None = None,
) -> bool:
    """
    处理单篇论文：下载 PDF → 解析文本 → 生成总结 → 存入数据库。
    如果 paper 包含 _tmp_pdf_path，则复用该路径（已在 fetch_metadata_from_pdf 中下载）。
    """
    pid = paper["paper_id"]
    title_short = paper["title"][:60]

    # --- 断点续传检查 ---
    if not force and db.paper_exists(pid):
        existing = db.get_paper_by_id(pid)
        has_summary = bool(existing and summarizer.has_valid_summary(existing.get("summary", "")))
        if has_summary:
            logger.info(f"⏭️  已存在且有总结，跳过: {title_short}")
            return False
        logger.info(f"🔄  已存在但无总结，重新生成: {title_short}")

    # --- 1. 下载或复用 PDF ---
    tmp_path = paper.pop("_tmp_pdf_path", None)  # 可能已被 fetch_metadata_from_pdf 下载
    if tmp_path and Path(tmp_path).exists():
        # 从已下载的 PDF 复用，构造路径（copy 到正确的 category 目录）
        pdf_path, category = pdf_parser.build_pdf_path(
            pid,
            paper["title"],
            paper["abstract"],
            category_override=save_category,
        )
        if not pdf_path.exists():
            shutil.copy(tmp_path, pdf_path)
        paper["_reused_pdf_path"] = str(pdf_path)
        logger.info(f"📥 复用已下载 PDF: {title_short}")
    else:
        pdf_path, category = pdf_parser.download_pdf(
            paper_id=pid,
            pdf_url=paper["pdf_url"],
            title=paper["title"],
            abstract=paper["abstract"],
            category_override=save_category,
        )
        if not pdf_path:
            raise RuntimeError(f"PDF 下载失败: {pid}")
        paper["_reused_pdf_path"] = str(pdf_path)

    logger.info(f"   分类: {category} | 路径: {paper['_reused_pdf_path']}")

    # --- 2. 解析 PDF 文本 ---
    logger.info("📖 解析 PDF 文本...")
    actual_pdf_path = Path(paper["_reused_pdf_path"])
    full_text = pdf_parser.parse_pdf_text(actual_pdf_path)
    if not full_text.strip():
        raise RuntimeError("PDF 解析文本为空")
    paper["full_text"] = full_text

    # --- 3. 生成总结 ---
    if skip_summary:
        paper["summary"] = ""
        paper["tags"] = ""
    else:
        llm_cfg = config.get("llm", {})
        model = llm_cfg.get("model", "deepseek-v4-flash")
        max_chars = llm_cfg.get("max_text_chars", 20000)
        lang = config.get("summary_language", "zh")
        allowed_tags = config.get("allowed_tags", [])

        logger.info(f"🤖 调用 LLM 生成总结 (model={model})...")
        try:
            summary = summarizer.summarize_paper(
                title=paper["title"],
                abstract=paper.get("abstract", ""),
                full_text=full_text[:max_chars],
                model=model,
                language=lang,
            )
            if not summarizer.has_valid_summary(summary):
                raise RuntimeError("总结为空或为失败占位内容")
            paper["summary"] = summary

            paper["affiliations"] = summarizer.extract_affiliations_from_summary(summary)
            tags = summarizer.infer_tags_from_summary(
                summary,
                model=model,
                allowed_tags=allowed_tags,
            )
            if category == "gui" and "gui" not in {t.strip().lower() for t in tags.split(",")}:
                tags = ", ".join([t for t in [tags, "gui"] if t])
            if allowed_tags:
                tags = tag_utils.normalize_tags_str(tags, allowed_tags)
            paper["tags"] = tags
            logger.info(f"✅ 总结生成成功 | 标签: {tags}")
        except Exception as e:
            logger.warning(f"⚠️  总结生成失败: {e}，将保存不带总结的记录")
            paper["summary"] = ""
            paper["tags"] = ""
            paper["affiliations"] = ""

    # --- 4. 存入数据库 ---
    db.save_paper(paper)
    logger.info(f"💾 入库成功: {title_short}")
    return True


# ============================================================
# 主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="通过 URL / arXiv ID / PDF 链接抓取并总结单篇论文",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
支持的输入格式:
  - arXiv URL:  https://arxiv.org/abs/1706.03762
  - arXiv ID:   1706.03762
  - 任意 PDF:   https://proceedings.neurips.cc/paper_files/paper/2012/...

示例:
  uv run python jobs/ingest_url.py https://arxiv.org/abs/1706.03762
  uv run python jobs/ingest_url.py 1706.03762
  uv run python jobs/ingest_url.py https://proceedings.neurips.cc/paper_files/paper/2012/...
  uv run python jobs/ingest_url.py URL1 URL2 URL3          # 批量
  uv run python jobs/ingest_url.py URL --force             # 强制重处理
  uv run python jobs/ingest_url.py URL --skip-summary      # 仅下载 PDF
        """,
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        help="arXiv URL、arXiv ID 或任意 PDF 链接，支持批量",
    )
    parser.add_argument(
        "--from-file",
        help="从文件读取输入，每行一个 URL / arXiv ID；空行和 # 注释会被忽略",
    )
    parser.add_argument(
        "--save-category",
        help="强制指定 PDF 保存类别目录，例如 gui",
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="强制重新处理（即使论文已存在有总结）",
    )
    parser.add_argument(
        "--skip-summary",
        action="store_true",
        help="跳过 LLM 总结，仅下载 PDF 并入库",
    )
    args = parser.parse_args()
    raw_inputs = load_inputs(args.inputs, args.from_file)
    if not raw_inputs:
        parser.error("请提供至少一个输入，或使用 --from-file 指定输入文件")

    # 初始化数据库
    db.init_db()
    config = load_config()

    # 解析所有输入
    parsed = []
    for raw in raw_inputs:
        kind, url, arxiv_id = parse_input(raw)
        parsed.append((kind, url, arxiv_id))
        logger.info(f"识别: {raw[:80]} → {kind} {arxiv_id or ''}")

    logger.info(f"=" * 60)
    logger.info(f"准备处理 {len(parsed)} 篇论文")
    logger.info(f"=" * 60)

    stats = {"new": 0, "skipped": 0, "already": 0, "failed": 0}

    for i, (kind, url, arxiv_id) in enumerate(parsed, 1):
        logger.info("")
        logger.info(f"[{i}/{len(parsed)}] 处理: {url[:80]}")

        try:
            # --- 拉取元数据 ---
            if kind == InputKind.ARXIV:
                logger.info(f"🔍 从 arXiv 获取元数据 (id={arxiv_id})...")
                paper = fetch_arxiv_paper(arxiv_id)
            else:
                logger.info(f"🔍 从 PDF URL 解析元数据...")
                paper = fetch_metadata_from_pdf(url, config, save_category=args.save_category)

            logger.info(f"   标题: {paper['title'][:80]}")
            logger.info(f"   作者: {paper['authors'][:80]}")

            # --- 跳过检查 ---
            pid = paper["paper_id"]
            if not args.force and db.paper_exists(pid):
                existing = db.get_paper_by_id(pid)
                if existing and existing.get("summary", "").strip():
                    logger.info(f"⏭️  已存在且有总结，直接跳过（用 --force 强制重处理）")
                    stats["already"] += 1
                    continue

            # --- 处理论文 ---
            saved = process_paper(
                paper,
                config,
                force=args.force,
                skip_summary=args.skip_summary,
                save_category=args.save_category,
            )
            if saved:
                stats["new"] += 1
            else:
                stats["skipped"] += 1

        except Exception as e:
            logger.error(f"❌ 处理失败: {url[:80]} | {e}")
            stats["failed"] += 1

    # --- 完成汇总 ---
    logger.info("")
    logger.info(f"=" * 60)
    logger.info(f"处理完成！")
    logger.info(f"  新增/覆盖: {stats['new']} 篇")
    logger.info(f"  跳过（已有）: {stats['skipped']} 篇")
    logger.info(f"  跳过（已有总结）: {stats['already']} 篇")
    logger.info(f"  失败: {stats['failed']} 篇")
    logger.info(f"  数据库现有: {db.count_papers()} 篇")
    logger.info(f"=" * 60)

    if stats["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
