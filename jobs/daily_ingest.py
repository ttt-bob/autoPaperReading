#!/usr/bin/env python3
"""
jobs/daily_ingest.py - 每日论文抓取与入库任务

Usage:
    uv run python jobs/daily_ingest.py

功能：
  1. 从 arXiv 抓取 CV 方向最新论文（每批 5 篇）
  2. 下载 PDF 并解析文本
  3. 调用 LLM 生成中文结构化总结
  4. 论文元数据存入 SQLite
  5. 每篇论文独立日志，完成后汇总

建议配合 cron 每天自动运行：
    0 8 * * * cd /path/to/cv-paper-rag && uv run python jobs/daily_ingest.py >> logs/daily_ingest.log 2>&1
"""
import sys
import os
import logging

# 代理配置现在由 rag/arxiv_fetcher.py 和 rag/pdf_parser.py 从 config.yaml 读取
# 如需禁用代理，可以在 config.yaml 中设置 proxy.enabled: false
# 如果需要使用系统代理，取消下面注释：
# os.environ["http_proxy"] = "http://127.0.0.1:7890"
# os.environ["https_proxy"] = "http://127.0.0.1:7890"

import argparse
import shutil
import json
import time
import random
from datetime import datetime
from pathlib import Path
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
from rag import db, arxiv_fetcher, pdf_parser, summarizer, tag_utils

PAPER_BATCH_SIZE = 5
LOGS_DIR = Path("logs")
PAPER_LOGS_DIR = LOGS_DIR / "papers"
PAPER_LOGS_DIR.mkdir(parents=True, exist_ok=True)


def setup_run_logger(run_id: str) -> logging.Logger:
    """为本轮运行创建独立的汇总日志（stdout + 文件）"""
    logger = logging.getLogger(f"run_{run_id}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    fh = logging.FileHandler(LOGS_DIR / f"run_{run_id}.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return logger


def setup_paper_logger(run_id: str, paper_id: str, title: str) -> logging.Logger:
    """为单篇论文创建独立日志文件"""
    paper_log_file = PAPER_LOGS_DIR / f"{paper_id}.log"
    logger = logging.getLogger(f"paper_{paper_id}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh = logging.FileHandler(paper_log_file, encoding="utf-8", mode="w")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # 流式处理器（引用父 logger，避免 tqdm 干扰）
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    logger.addHandler(stream)

    logger.info(f"=== 开始处理论文: {title[:80]} ===")
    return logger


def load_config() -> dict:
    cfg_path = Path("config.yaml")
    if not cfg_path.exists():
        raise FileNotFoundError("config.yaml not found. 请先创建配置文件。")
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def clear_previous_papers() -> None:
    """清空已有的论文数据（数据库 + PDF）"""
    db_path = Path("data/papers.db")
    pdfs_dir = Path("data/pdfs")

    if db_path.exists():
        db_path.unlink()
        print(f"已删除: {db_path}")

    if pdfs_dir.exists():
        shutil.rmtree(pdfs_dir)
        pdfs_dir.mkdir(parents=True, exist_ok=True)
        print(f"已清空: {pdfs_dir}")

    db.init_db()
    print("数据库已重新初始化")


def main():
    parser = argparse.ArgumentParser(description="每日论文抓取与入库")
    parser.add_argument("--max-results", type=int, default=None, help="最多抓取多少条论文")
    parser.add_argument("--days-back", type=int, default=7, help="向前追溯多少天的论文")
    parser.add_argument("--date", type=str, default=None,
                        help="指定日期 YYYY-MM-DD，精确抓取该天的论文（会覆盖 --days-back）")
    parser.add_argument("--skip-summary", action="store_true", help="跳过 LLM 总结（仅抓取入库）")
    parser.add_argument("--category", type=str, default="cs.CV", help="arXiv 分类")
    parser.add_argument("--clear", action="store_true", help="先清空已有论文数据再抓取")
    parser.add_argument("--batch-size", type=int, default=PAPER_BATCH_SIZE, help=f"每批处理篇数（默认 {PAPER_BATCH_SIZE}）")
    parser.add_argument(
        "--reprocess",
        action="store_true",
        help="强制重新处理所有论文（覆盖已有总结），默认跳过已有总结的论文",
    )
    parser.add_argument(
        "--reprocess-missing",
        action="store_true",
        help="只补全缺机构信息的论文（从已有总结中提取，不重新调用 LLM）",
    )
    args = parser.parse_args()

    # 如果需要清空数据
    if args.clear:
        print("正在清空已有数据...")
        clear_previous_papers()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    start_time = datetime.now()

    # 主日志
    main_logger = setup_run_logger(run_id)
    main_logger.info("=" * 60)
    main_logger.info("CV Paper RAG - 每日论文入库任务启动")
    main_logger.info(f"运行 ID: {run_id}")
    main_logger.info(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    main_logger.info(f"每批处理: {args.batch_size} 篇")
    main_logger.info("=" * 60)

    # 初始化数据库
    db.init_db()
    main_logger.info(f"数据库已有论文: {db.count_papers()} 篇")

    # 加载配置
    config = load_config()
    topics = config.get("topics", [])
    llm_cfg = config.get("llm", {})
    sources_cfg = config.get("sources", {})

    max_results = args.max_results or sources_cfg.get("arxiv", {}).get("max_results_per_day", 50)
    summary_model = llm_cfg.get("model", "deepseek-v4-flash")
    max_text_chars = llm_cfg.get("max_text_chars", 20000)
    summary_language = config.get("summary_language", "zh")
    allowed_tags = config.get("allowed_tags", [])

    # ========== 抓取论文（reprocess-missing 模式跳过） ==========
    if args.reprocess_missing:
        # 只补全缺机构信息的论文，不抓新论文
        main_logger.info("reprocess-missing 模式：只补全缺机构信息的论文...")
        all_papers = []
    else:
        main_logger.info(f"开始抓取 arXiv 论文...")
        main_logger.info(f"关键词: {topics[:5]}{'...' if len(topics) > 5 else ''} (共 {len(topics)} 个)")
        if args.date:
            main_logger.info(f"分类: {args.category}, 最多 {max_results} 条, 指定日期: {args.date}")
        else:
            main_logger.info(f"分类: {args.category}, 最多 {max_results} 条, 追溯 {args.days_back} 天")

        try:
            all_papers = arxiv_fetcher.fetch_papers(
                topics=topics,
                category=args.category,
                max_results=max_results,
                days_back=0 if args.date else args.days_back,
                date=args.date,
            )
        except Exception as e:
            main_logger.error(f"arXiv 抓取失败: {e}")
            sys.exit(1)

        main_logger.info(f"共抓取 {len(all_papers)} 篇论文")

    # ========== 过滤已存在的论文 ==========
    papers_to_process = []
    skipped = 0
    skipped_already_done = 0  # 有总结直接跳过的
    if args.reprocess_missing:
        # 从数据库中找出缺机构信息的论文
        all_missing = db.get_papers_missing_affiliations()
        main_logger.info(f"数据库中缺机构信息的论文: {len(all_missing)} 篇")
        papers_to_process = [{"paper_id": p["paper_id"], **p} for p in all_missing]
    else:
        for paper in all_papers:
            if db.paper_exists(paper["paper_id"]):
                if args.reprocess:
                    # --reprocess 时视为需要重新处理（PDF 也会重新下载）
                    papers_to_process.append(paper)
                    skipped -= 1 if skipped > 0 else 0  # 不计入已跳过
                else:
                    # 默认：已有总结则跳过，无总结则补全
                    existing = db.get_paper_by_id(paper["paper_id"])
                    if existing and summarizer.has_valid_summary(existing.get("summary", "")):
                        skipped_already_done += 1
                        main_logger.debug(f"⏭️  已存在有总结，跳过: {paper['paper_id']}")
                    else:
                        main_logger.debug(f"🔄  已存在但无总结，补全: {paper['paper_id']}")
                        papers_to_process.append(paper)
            else:
                papers_to_process.append(paper)

    main_logger.info(
        f"去重后需处理: {len(papers_to_process)} 篇 "
        f"(已跳过(有总结): {skipped_already_done} | 已有待补全: {len(papers_to_process) - (len(all_papers) - skipped_already_done - skipped)})"
    )

    if not papers_to_process:
        main_logger.info("没有新论文，任务结束。")
        db.log_ingest(
            run_date=start_time.strftime("%Y-%m-%d"),
            found=len(all_papers),
            new=0,
            skipped=skipped + skipped_already_done,
            failed=0,
        )
        return

    # ========== 分批处理 ==========
    total_batches = (len(papers_to_process) + args.batch_size - 1) // args.batch_size
    stats = {"new": 0, "skipped": 0, "failed": 0}
    paper_results = []

    for batch_idx in range(total_batches):
        batch_start = batch_idx * args.batch_size
        batch_papers = papers_to_process[batch_start:batch_start + args.batch_size]
        main_logger.info("")
        main_logger.info(f"========== 批次 {batch_idx + 1}/{total_batches} ({len(batch_papers)} 篇) ==========")

        for paper in tqdm(batch_papers, desc=f"批次 {batch_idx + 1}/{total_batches}", unit="篇"):
            paper_id = paper["paper_id"]
            title_short = paper["title"][:60]
            paper_logger = setup_paper_logger(run_id, paper_id, paper["title"])

            try:
                # PDF 下载前随机延时，避免触发 arXiv 429 限流
                time.sleep(random.uniform(1, 3))

                # 1. 下载 PDF（按任务分类目录保存）
                pdf_path, category = pdf_parser.download_pdf(
                    paper_id=paper_id,
                    pdf_url=paper["pdf_url"],
                    title=paper["title"],
                    abstract=paper["abstract"],
                )
                if not pdf_path:
                    raise RuntimeError("PDF 下载失败")
                paper_logger.info(f"分类: {category} | 路径: {pdf_path}")

                # 2. 解析 PDF 文本
                full_text = pdf_parser.parse_pdf_text(pdf_path)
                if not full_text.strip():
                    raise RuntimeError("PDF 解析文本为空")

                paper["full_text"] = full_text

                # 3. 生成总结
                if not args.skip_summary:
                    try:
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
                        # 从总结中提取机构信息
                        paper["affiliations"] = summarizer.extract_affiliations_from_summary(summary)
                        tags = summarizer.infer_tags_from_summary(
                            summary,
                            model=summary_model,
                            allowed_tags=allowed_tags,
                        )
                        paper["tags"] = tags
                        paper_logger.info("总结生成成功")
                    except Exception as e:
                        paper_logger.warning(f"总结生成失败: {e}")
                        paper["summary"] = ""
                        paper["tags"] = ""
                        paper["affiliations"] = ""
                else:
                    paper["summary"] = ""
                    paper["tags"] = ""
                    paper["affiliations"] = ""

                # 4. 存 SQLite
                db.save_paper(paper)

                # 5. 标签规范化（确保标签在 allowed_tags 范围内）
                if paper.get("tags"):
                    normalized_tags = tag_utils.normalize_tags_str(paper["tags"], allowed_tags)
                    if normalized_tags != paper["tags"]:
                        conn = db.get_conn()
                        cur = conn.cursor()
                        cur.execute(
                            "UPDATE papers SET tags = ?, updated_at = CURRENT_TIMESTAMP WHERE paper_id = ?",
                            (normalized_tags, paper_id),
                        )
                        conn.commit()
                        conn.close()
                        paper["tags"] = normalized_tags
                        paper_logger.info(f"标签已规范化: {normalized_tags}")

                stats["new"] += 1
                paper_logger.info(f"✅ 入库成功: {title_short}")
                paper_results.append({
                    "paper_id": paper_id,
                    "title": paper["title"],
                    "status": "success",
                })

            except Exception as e:
                stats["failed"] += 1
                paper_logger.error(f"❌ 处理失败: {paper_id} | {title_short} | {e}")
                paper_results.append({
                    "paper_id": paper_id,
                    "title": paper["title"],
                    "status": "failed",
                    "error": str(e),
                })

    # ========== 完成汇总 ==========
    elapsed = datetime.now() - start_time
    main_logger.info("")
    main_logger.info("=" * 60)
    main_logger.info("任务完成！")
    main_logger.info(f"处理: {stats['new']} 篇 | 跳过: {stats['skipped']} 篇 | 失败: {stats['failed']} 篇")
    main_logger.info(f"总耗时: {elapsed.total_seconds():.1f} 秒")
    main_logger.info(f"数据库现有论文: {db.count_papers()} 篇")
    main_logger.info("=" * 60)

    # 保存汇总报告
    summary_file = LOGS_DIR / f"summary_{run_id}.json"
    summary_data = {
        "run_id": run_id,
        "start_time": start_time.isoformat(),
        "end_time": datetime.now().isoformat(),
        "elapsed_seconds": elapsed.total_seconds(),
        "stats": stats,
        "papers": paper_results,
        "skipped": skipped,
        "total_found": len(all_papers),
    }
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, ensure_ascii=False, indent=2)
    main_logger.info(f"汇总报告已保存: {summary_file}")

    db.log_ingest(
        run_date=start_time.strftime("%Y-%m-%d"),
        found=len(all_papers),
        new=stats["new"],
        skipped=stats["skipped"] + skipped,
        failed=stats["failed"],
    )

    # 只要存在处理失败，就通知调用方本轮没有完整完成。这样自动任务不会
    # 写入当天完成标记，后续调度可以在网络或代理恢复后补齐失败项。
    if stats["failed"] > 0:
        main_logger.error("存在处理失败；任务以失败状态退出，等待下次重试。")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
