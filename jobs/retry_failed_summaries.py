#!/usr/bin/env python3
"""
jobs/retry_failed_summaries.py - 重新生成空摘要或失败摘要

Usage:
    uv run python jobs/retry_failed_summaries.py --date 2026-06-09 --date 2026-06-08
    uv run python jobs/retry_failed_summaries.py --paper-id 2606.11507v1
"""
import argparse
import logging
import random
import sqlite3
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from rag import pdf_parser, summarizer, tag_utils
from rag.db import DB_PATH

logger = logging.getLogger("retry_failed_summaries")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def load_config() -> dict:
    cfg_path = Path("config.yaml")
    if not cfg_path.exists():
        return {}
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_candidates(dates: list[str], paper_ids: list[str], limit: int | None) -> list[dict]:
    where = [
        "(summary IS NULL OR TRIM(summary) = '' "
        "OR summary LIKE '[总结生成失败:%' "
        "OR summary LIKE '总结生成失败:%')"
    ]
    params: list[str | int] = []

    if dates:
        placeholders = ",".join("?" for _ in dates)
        where.append(f"DATE(published) IN ({placeholders})")
        params.extend(dates)

    if paper_ids:
        placeholders = ",".join("?" for _ in paper_ids)
        where.append(f"paper_id IN ({placeholders})")
        params.extend(paper_ids)

    sql = f"""
        SELECT paper_id, title, authors, abstract, published,
               pdf_url, entry_url, summary, tags, affiliations, created_at
        FROM papers
        WHERE {" AND ".join(where)}
        ORDER BY published DESC
    """
    if limit:
        sql += " LIMIT ?"
        params.append(limit)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def update_summary(paper_id: str, summary: str, tags: str, affiliations: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            UPDATE papers
            SET summary = ?,
                tags = ?,
                affiliations = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE paper_id = ?
            """,
            (summary, tags, affiliations, paper_id),
        )
        conn.commit()
    finally:
        conn.close()


def ensure_pdf(paper: dict) -> Path:
    pdf_path, _category = pdf_parser.build_pdf_path(
        paper["paper_id"],
        paper.get("title", ""),
        paper.get("abstract", ""),
    )
    if pdf_path.exists() and pdf_path.stat().st_size > 1024:
        return pdf_path

    downloaded, _category = pdf_parser.download_pdf(
        paper_id=paper["paper_id"],
        pdf_url=paper.get("pdf_url", ""),
        title=paper.get("title", ""),
        abstract=paper.get("abstract", ""),
    )
    if not downloaded:
        raise RuntimeError("PDF 不存在且下载失败")
    return downloaded


def retry_one(paper: dict, config: dict) -> bool:
    llm_cfg = config.get("llm", {})
    model = llm_cfg.get("model", "deepseek-v4-flash")
    max_text_chars = llm_cfg.get("max_text_chars", 20000)
    language = config.get("summary_language", "zh")
    allowed_tags = config.get("allowed_tags", [])

    paper_id = paper["paper_id"]
    title = paper.get("title", "") or paper_id
    logger.info("重新总结: %s | %s", paper_id, title[:80])

    pdf_path = ensure_pdf(paper)
    full_text = pdf_parser.parse_pdf_text(pdf_path)
    if not full_text.strip():
        raise RuntimeError("PDF 解析文本为空")

    summary = summarizer.summarize_paper(
        title=title,
        abstract=paper.get("abstract", ""),
        authors=paper.get("authors", ""),
        full_text=full_text[:max_text_chars],
        model=model,
        language=language,
    )
    if not summarizer.has_valid_summary(summary):
        raise RuntimeError("总结为空或为失败占位内容")

    affiliations = summarizer.extract_affiliations_from_summary(summary)
    tags = summarizer.infer_tags_from_summary(
        summary,
        model=model,
        allowed_tags=allowed_tags,
    )
    if allowed_tags:
        tags = tag_utils.normalize_tags_str(tags, allowed_tags)

    update_summary(paper_id, summary, tags, affiliations)
    logger.info("总结已更新: %s | 标签: %s", paper_id, tags)
    return True


def main() -> int:
    setup_logging()

    parser = argparse.ArgumentParser(description="重新生成空摘要或失败摘要")
    parser.add_argument("--date", action="append", default=[], help="按 published 日期筛选，可重复")
    parser.add_argument("--paper-id", action="append", default=[], help="按 paper_id 筛选，可重复")
    parser.add_argument("--limit", type=int, default=None, help="最多处理多少篇")
    args = parser.parse_args()

    config = load_config()
    candidates = load_candidates(args.date, args.paper_id, args.limit)
    logger.info("待重试论文: %s 篇", len(candidates))

    ok = 0
    failed = 0
    for idx, paper in enumerate(candidates, 1):
        logger.info("进度: %s/%s", idx, len(candidates))
        try:
            if retry_one(paper, config):
                ok += 1
        except Exception as e:
            failed += 1
            logger.error("重试失败: %s | %s", paper.get("paper_id"), e)

        if idx < len(candidates):
            time.sleep(random.uniform(1.0, 3.0))

    logger.info("完成: 成功 %s 篇 | 失败 %s 篇", ok, failed)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
