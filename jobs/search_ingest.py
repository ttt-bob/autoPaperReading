#!/usr/bin/env python3
"""
jobs/search_ingest.py - 视频/图像检索方向论文批量抓取与总结入库

按主题组从 arXiv 拉取"视频搜索 / 图像检索 / 时序定位 / 异常检测 / 行人搜索"
方向的论文，生成中文结构化总结并写入 data/papers.db，供 video-search 专题页使用。

用法:
    uv run python jobs/search_ingest.py --fetch-only      # 只抓候选列表(存 data/search_candidates.json)
    uv run python jobs/search_ingest.py --summarize-only  # 只总结候选(可断点续跑，跳过已有总结的)
    uv run python jobs/search_ingest.py                   # 完整流程
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import arxiv

from rag import db, pdf_parser, summarizer, tag_utils

logger = logging.getLogger("search_ingest")

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES_FILE = ROOT / "data" / "search_candidates.json"
VIDEO_SEARCH_TAG = "video search"

# 主题组：每个组一个 arXiv 查询（相关性排序）
TOPIC_GROUPS = [
    # 视频检索
    ["video retrieval", "text-video retrieval", "video-text retrieval", "video search"],
    ["video moment retrieval", "temporal grounding", "moment retrieval", "temporal action localization"],
    ["video question answering", "video understanding", "video large language model", "video mllm"],
    ["long video understanding", "video instruction tuning", "video reasoning"],
    ["video anomaly detection", "video anomaly", "human-centric anomaly detection"],
    ["temporal action detection", "temporal action localization", "action detection", "action recognition"],
    ["video captioning", "dense video captioning", "video summarization", "video highlight"],
    ["video grounding", "grounded video", "video-language grounding", "temporal grounding video"],
    # 行人搜索 / 重识别
    ["person search", "text-based person search", "person re-identification", "person re-id"],
    ["pedestrian retrieval", "person retrieval", "re-identification video", "occluded person"],
    # 图像检索 / 多模态检索
    ["image retrieval", "text-to-image retrieval", "composed image retrieval"],
    ["cross-modal retrieval", "multimodal retrieval", "image-text retrieval", "image-text matching"],
    ["visual grounding", "phrase grounding", "referring expression", "open-vocabulary grounding"],
    ["vision-language embedding", "multimodal embedding", "zero-shot retrieval", "retrieval augmented"],
    # 异常 / 安防
    ["fall detection", "violence detection", "surveillance", "abnormal event detection"],
    ["video indexing", "video database", "video search engine", "video organization"],
]

# 每组的 arXiv 查询页大小
RESULTS_PER_QUERY = 40
# 只保留该日期之后发表的论文（含）
MIN_PUBLISHED = "2025-01-01"
# 候选论文数量目标（达到后停止继续抓取）
TARGET_CANDIDATES = 99999

# 硬排除词（标题命中即剔除）：生成/重建/医疗/交通/3D 等明显偏离检索方向的
HARD_EXCLUDE = [
    "world model", "video generation", "text-to-video", "image generation", "text-to-image",
    "video diffusion", "image diffusion", "diffusion model", "diffusion", "video editing",
    "image editing", "video edit", "3d", "reconstruction", "rendering", "gaussian splatting",
    "nerf", "neural radiance", "medical", "clinical", "treatment", "diagnos", "mri",
    "radiology", "echocardi", "tumor", "disease", "brain", "drug", "protein", "molecule",
    "traffic", "driving", "autonomous", "vehicle", "lane", "crash", "accident detection",
    "sports", "football", "soccer", "basketball", "fishing", "face", "avatar", "audio",
    "speech", "music", "story", "narrative", "novel", "fiction", "dbms", "database",
    "robot", "manipulation", "grasp", "surgical", "satellite", "remote sensing",
    "agriculture", "crop", "marine", "ocean", "battery", "x-ray", "pathology", "health",
    "emotion", "affective", "gait", "dance", "animation", "gesture", "biometric",
    "adversarial", "attack", "privacy", "deepfake", "fake", "hallucination", "watermark",
    "gui", "computer use", "ui ", "screen", "web agent", "llm agent", "agent",
    "motion generation", "motion synthesis", "human-scene", "scene interaction",
    "forecast", "prediction", "future frame", "world action",
]

# 包含词（标题命中 +3，摘要命中 +1）
INCLUDE_TERMS = [
    "retrieval", "search", "grounding", "moment", "temporal", "anomaly", "abnormal",
    "re-identification", "re-id", "person", "pedestrian", "captioning", "summarization",
    "question answering", "understanding", "highlight", "matching", "embedding",
    "composed", "cross-modal", "multimodal", "video-language", "vision-language",
    "zero-shot", "open-vocabulary", "action detection", "action recognition",
    "action localization", "surveillance", "fall detection", "violence", "video analytics",
    "indexing", "referring", "localization", "video qa", "videoqa", "vqa", "video llm",
    "video mllm", "language-queried", "text-video", "video-text",
]

MIN_RELEVANCE_SCORE = 5


def relevance_score(paper: dict) -> int:
    title = paper["title"].lower()
    abstract = (paper.get("abstract") or "").lower()[:500]
    return sum(3 if k in title else (1 if k in abstract else 0) for k in INCLUDE_TERMS)


def is_relevant(paper: dict) -> bool:
    """精选过滤：标题不命中硬排除词，且相关度分数达标。"""
    title = paper["title"].lower()
    if any(kw in title for kw in HARD_EXCLUDE):
        return False
    return relevance_score(paper) >= MIN_RELEVANCE_SCORE

# 明显偏离“检索/搜索/理解”方向的标题关键词（命中则剔除）
OFF_TOPIC_KEYWORDS = [
    "world model", "video generation", "text-to-video", "image generation",
    "text-to-image", "video diffusion", "image diffusion", "diffusion model",
    "3d reconstruction", "neural rendering", "gaussian splatting", "novel view",
    "slam", "neural radiance", "gui", "computer use", "ui automation",
    "echocardi", "radiology", "mri", "medical", "clinical", "surgical",
    "autonomous driving", "self-driving", "dashcam", "lane detection",
    "surgical", "battery", "protein", "molecule", "drug",
]


def is_off_topic(paper: dict) -> bool:
    """标题命中偏题关键词则返回 True。"""
    title = paper["title"].lower()
    return any(kw in title for kw in OFF_TOPIC_KEYWORDS)


def ensure_video_search_tag(tags: str | None) -> str:
    """Keep the专题标签 on every paper ingested by this video-search job."""
    existing = [t.strip() for t in (tags or "").split(",") if t.strip()]
    if VIDEO_SEARCH_TAG.lower() not in {t.lower() for t in existing}:
        existing.append(VIDEO_SEARCH_TAG)
    return ", ".join(existing)


def _date_window() -> str:
    """返回 submittedDate 范围: [MIN_PUBLISHED TO 今天]"""
    today = datetime.now().strftime("%Y%m%d")
    return f"submittedDate:[{MIN_PUBLISHED.replace('-', '')} TO {today}]"


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def fetch_candidates() -> list[dict]:
    """按主题组抓取候选论文；若已有候选文件则先加载并在其基础上增量补充。"""
    seen: set[str] = set()
    candidates: list[dict] = []
    if CANDIDATES_FILE.exists():
        existing = json.loads(CANDIDATES_FILE.read_text(encoding="utf-8"))
        candidates = [p for p in existing if not is_off_topic(p)]
        seen = {p["paper_id"] for p in candidates}
        logger.info("已加载既有候选 %d 篇（剔除偏题 %d 篇）", len(candidates), len(existing) - len(candidates))
    client = arxiv.Client(page_size=RESULTS_PER_QUERY, delay_seconds=2.0, num_retries=2)
    for idx, topics in enumerate(TOPIC_GROUPS, 1):
        if len(candidates) >= TARGET_CANDIDATES:
            logger.info("已到目标候选数 %d，停止抓取", TARGET_CANDIDATES)
            break
        clause = " OR ".join(f'"{t}"' for t in topics)
        query = f'({clause}) AND {_date_window()}'
        logger.info("[%d/%d] 查询: %s", idx, len(TOPIC_GROUPS), clause[:100])
        search = arxiv.Search(
            query=query,
            max_results=RESULTS_PER_QUERY,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )
        try:
            results = list(client.results(search))
        except Exception as exc:  # 单个查询失败不中断整体
            logger.warning("查询失败(继续): %s", exc)
            continue

        added = 0
        for result in results:
            paper_id = result.get_short_id()
            if paper_id in seen:
                continue
            published = result.published.date().isoformat()
            if published < MIN_PUBLISHED:
                continue
            seen.add(paper_id)
            rec = {
                "paper_id": paper_id,
                "title": result.title,
                "authors": ", ".join(a.name for a in result.authors),
                "abstract": result.summary,
                "published": result.published.isoformat(),
                "pdf_url": result.pdf_url,
                "entry_url": result.entry_id,
                "category_hint": topics[0],
            }
            if is_off_topic(rec):
                continue
            candidates.append(rec)
            added += 1
        logger.info("  本组新增 %d 篇（累计 %d）", added, len(candidates))
        time.sleep(3.0)  # 组间小延时，避免触发限流

    return candidates


def dedupe_against_db(candidates: list[dict]) -> list[dict]:
    """过滤掉数据库里已有的论文。"""
    fresh = []
    for paper in candidates:
        if db.paper_exists(paper["paper_id"]):
            continue
        fresh.append(paper)
    logger.info("去重后新论文: %d（库中已有 %d）", len(fresh), len(candidates) - len(fresh))
    return fresh


def summarize_candidates(candidates: list[dict]) -> dict:
    """逐个下载 PDF -> 解析 -> LLM 总结 -> 入库，可断点续跑。"""
    config = _load_config()
    llm_cfg = config.get("llm", {})
    summary_model = llm_cfg.get("model", "deepseek-v4-flash")
    max_text_chars = llm_cfg.get("max_text_chars", 20000)
    summary_language = config.get("summary_language", "zh")
    allowed_tags = config.get("allowed_tags", [])

    stats = {"new": 0, "skipped": 0, "failed": 0}
    failed_ids: list[str] = []

    for i, paper in enumerate(candidates, 1):
        paper_id = paper["paper_id"]
        # 断点续跑：已有有效总结的直接跳过
        existing = db.get_paper_by_id(paper_id)
        if existing and summarizer.has_valid_summary(existing.get("summary", "")):
            tagged = ensure_video_search_tag(existing.get("tags", ""))
            if tagged != (existing.get("tags", "") or ""):
                conn = db.get_conn()
                conn.execute(
                    "UPDATE papers SET tags = ?, updated_at = CURRENT_TIMESTAMP WHERE paper_id = ?",
                    (tagged, paper_id),
                )
                conn.commit()
                conn.close()
            stats["skipped"] += 1
            continue

        print(f"\n[{i}/{len(candidates)}] {paper['title'][:80]} ({paper_id})", flush=True)
        try:
            time.sleep(random.uniform(1, 3))
            pdf_path, category = pdf_parser.download_pdf(
                paper_id=paper_id,
                pdf_url=paper["pdf_url"],
                title=paper["title"],
                abstract=paper["abstract"],
            )
            if not pdf_path:
                raise RuntimeError("PDF 下载失败")
            full_text = pdf_parser.parse_pdf_text(pdf_path)
            if not full_text.strip():
                raise RuntimeError("PDF 解析文本为空")

            paper["full_text"] = full_text
            summary = summarizer.summarize_paper(
                title=paper["title"],
                abstract=paper["abstract"],
                authors=paper.get("authors", ""),
                full_text=full_text[:max_text_chars],
                model=summary_model,
                language=summary_language,
            )
            if not summarizer.has_valid_summary(summary):
                raise RuntimeError("总结为空或为失败占位内容")
            paper["summary"] = summary
            paper["affiliations"] = summarizer.extract_affiliations_from_summary(summary)
            paper["tags"] = summarizer.infer_tags_from_summary(
                summary, model=summary_model, allowed_tags=allowed_tags
            )
            paper["tags"] = ensure_video_search_tag(paper["tags"])
            db.save_paper(paper)

            if paper.get("tags"):
                normalized = tag_utils.normalize_tags_str(paper["tags"], allowed_tags)
                if normalized != paper["tags"]:
                    conn = db.get_conn()
                    conn.execute(
                        "UPDATE papers SET tags = ?, updated_at = CURRENT_TIMESTAMP WHERE paper_id = ?",
                        (normalized, paper_id),
                    )
                    conn.commit()
                    conn.close()
            stats["new"] += 1
            print(f"  ✅ 入库成功 ({paper_id})", flush=True)
        except Exception as exc:
            stats["failed"] += 1
            failed_ids.append(paper_id)
            print(f"  ❌ 失败: {exc}", flush=True)
            # 失败也记录占位，避免下次重复下载
            try:
                db.save_paper({**paper, "summary": "", "tags": "", "affiliations": ""})
            except Exception:
                pass

    return stats


def _load_config() -> dict:
    import yaml

    cfg_path = ROOT / "config.yaml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="视频/图像检索方向论文批量抓取与总结")
    parser.add_argument("--fetch-only", action="store_true", help="只抓候选列表")
    parser.add_argument("--summarize-only", action="store_true", help="只总结候选")
    parser.add_argument("--candidates", type=str, default=None, help="候选 JSON 路径(默认 data/search_candidates.json)")
    args = parser.parse_args()

    candidates_file = Path(args.candidates) if args.candidates else CANDIDATES_FILE

    setup_logging()
    db.init_db()
    logger.info("数据库现有论文: %d", db.count_papers())

    if not args.summarize_only:
        logger.info("开始抓取候选论文…")
        candidates = fetch_candidates()
        # 精选过滤：去掉偏题/低相关论文（与当前页面收录口径一致）
        before = len(candidates)
        candidates = [c for c in candidates if is_relevant(c)]
        logger.info("精选过滤: %d -> %d 篇", before, len(candidates))
        candidates = dedupe_against_db(candidates)
        candidates_file.parent.mkdir(parents=True, exist_ok=True)
        candidates_file.write_text(
            json.dumps(candidates, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        logger.info("候选已保存: %s (%d 篇)", candidates_file, len(candidates))
        if args.fetch_only:
            return

    if not candidates_file.exists():
        logger.error("候选文件不存在: %s", candidates_file)
        sys.exit(1)

    candidates = json.loads(candidates_file.read_text(encoding="utf-8"))
    logger.info("开始总结 %d 篇候选论文…", len(candidates))
    stats = summarize_candidates(candidates)
    logger.info(
        "完成: 新增 %d | 已有跳过 %d | 失败 %d", stats["new"], stats["skipped"], stats["failed"]
    )
    logger.info("数据库现有论文: %d", db.count_papers())


if __name__ == "__main__":
    main()
