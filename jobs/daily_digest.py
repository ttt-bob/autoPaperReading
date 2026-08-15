#!/usr/bin/env python3
"""
jobs/daily_digest.py - 生成每日论文摘要报告

Usage:
    uv run python jobs/daily_digest.py
    uv run python jobs/daily_digest.py --days 7    # 生成最近一周的摘要
    uv run python jobs/daily_digest.py --format html  # 输出 HTML 格式
    uv run python jobs/daily_digest.py --today-only  # 仅今日新增论文，一句话简介（默认）
"""
import sys
import os
import logging
import argparse
import re
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
from rag import db


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("daily_digest")


def load_config() -> dict:
    cfg_path = Path("config.yaml")
    if not cfg_path.exists():
        return {}
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def extract_brief_intro(summary: str, max_chars: int = 120) -> str:
    """
    从总结中提取一句话简介。
    优先取「三、一句话总结」小节内容；否则取第一段，去掉 markdown 标记。
    """
    if not summary:
        return ""

    # 尝试提取「一句话总结」小节
    lines = summary.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r"^##\s*[三3][.、]?\s*一?句话总", stripped):
            content_lines = []
            for j in range(i + 1, len(lines)):
                l = lines[j].strip()
                if l.startswith("##") or l.startswith("#"):
                    break
                if l:
                    content_lines.append(l)
            if content_lines:
                text = " ".join(content_lines)
                text = re.sub(r"[#*`_\[\]]", "", text).strip()
                if text:
                    return text[:max_chars] + ("…" if len(text) > max_chars else "")
            break

    # 回退：取第一段正文
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^#{1,3}\s", stripped):
            continue
        if re.match(r"^[-*]\s", stripped):
            continue
        if re.match(r"^\d+[.、)]", stripped):
            continue
        text = re.sub(r"[#*`_\[\]]", "", stripped).replace("\n", " ").strip()
        if text:
            return text[:max_chars] + ("…" if len(text) > max_chars else "")

    return ""


def generate_markdown_digest(papers: list[dict], days: int) -> str:
    """生成 Markdown 格式的摘要报告"""
    today = datetime.now().strftime("%Y-%m-%d")
    total = len(papers)

    # 按标签分组
    by_tag = defaultdict(list)
    no_tag_papers = []
    for p in papers:
        tags = p.get("tags", "") or ""
        if tags.strip():
            for tag in tags.split(","):
                tag = tag.strip()
                if tag:
                    by_tag[tag].append(p)
        else:
            no_tag_papers.append(p)

    lines = [
        f"# CV Paper Daily Digest",
        f"",
        f"**生成时间**: {today}",
        f"**论文数量**: {total} 篇",
        f"**覆盖时间**: 最近 {days} 天",
        f"",
    ]

    # 统计信息
    if by_tag:
        top_tags = sorted(by_tag.items(), key=lambda x: len(x[1]), reverse=True)[:10]
        lines.append("## 📊 热门方向 Top 10")
        lines.append("")
        tag_counts = [f"- **{tag}**: {len(papers)} 篇" for tag, papers in top_tags]
        lines.extend(tag_counts)
        lines.append("")

    # 最新论文
    lines.append("## 📄 最新论文列表")
    lines.append("")

    if not papers:
        lines.append("*今日无新论文入库。*")
    else:
        for i, paper in enumerate(papers, 1):
            lines.append(f"### {i}. {paper.get('title', 'N/A')}")
            lines.append("")
            lines.append(f"**作者**: {paper.get('authors', 'N/A')}")
            lines.append("")
            lines.append(f"**发布日期**: {paper.get('published', 'N/A')[:10]}")
            lines.append(f"**arXiv**: [{paper.get('paper_id', '')}]({paper.get('entry_url', '')})")
            lines.append(f"**PDF**: [下载]({paper.get('pdf_url', '')})")

            tags = paper.get("tags", "") or ""
            if tags:
                lines.append(f"**标签**: {tags}")
            lines.append("")

            # 完整显示总结（总结已有完整内容，不再截断）
            summary = paper.get("summary", "") or paper.get("abstract", "")
            if summary:
                lines.append(summary.strip())
            lines.append("")
            lines.append("")
            lines.append("---")
            lines.append("")

    # 按方向分组的详细内容
    if by_tag:
        lines.append("## 🏷️ 按方向分类")
        lines.append("")
        for tag, tag_papers in sorted(by_tag.items(), key=lambda x: len(x[1]), reverse=True):
            if len(tag_papers) >= 2:  # 只显示有 2 篇以上的标签
                lines.append(f"### {tag} ({len(tag_papers)} 篇)")
                lines.append("")
                for p in tag_papers[:5]:  # 每个标签最多显示 5 篇
                    title = p.get("title", "N/A")
                    paper_id = p.get("paper_id", "")
                    url = p.get("entry_url", "")
                    lines.append(f"- [{title}]({url}) — {paper_id}")
                lines.append("")

    # 底部信息
    elapsed = datetime.now()
    lines.extend([
        "---",
        "",
        f"*报告生成于 {elapsed.strftime('%Y-%m-%d %H:%M:%S')}*",
        f"*由 CV Paper RAG 自动生成 — 基于 arXiv CS.CV 每日抓取*",
    ])

    return "\n".join(lines)


def generate_brief_today_digest(new_papers: list[dict]) -> str:
    """
    生成今日新增论文的一句话说报（默认每日通知格式）。
    只打印标题 + 一句话简介，不打印完整总结，简洁明了。
    """
    today = datetime.now().strftime("%Y-%m-%d")
    total = len(new_papers)

    header = [
        f"📚 CV Paper Daily — {today}",
        f"今日新增 {total} 篇论文",
        "=" * 50,
        "",
    ]

    if not new_papers:
        header.append("今日无新论文入库。")
        return "\n".join(header)

    rows = []
    for i, paper in enumerate(new_papers, 1):
        title = paper.get("title", "N/A")
        paper_id = paper.get("paper_id", "")
        brief = extract_brief_intro(paper.get("summary", "") or paper.get("abstract", ""))

        # 标题截断
        title_short = title[:70] + ("…" if len(title) > 70 else "")

        rows.append(f"  {i}. {title_short}")
        rows.append(f"     👤 {paper.get('authors', '未知')[:60]}")
        if brief:
            rows.append(f"     📖 {brief}")
        rows.append(f"     🔗 {paper.get('entry_url', '')}")
        rows.append("")

    return "\n".join(header + rows)


def generate_text_digest(papers: list[dict], days: int) -> str:
    """生成纯文本格式（方便 curl 或通知推送）"""
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"CV Paper Daily Digest - {today}",
        f"论文数量: {len(papers)} 篇 | 覆盖: 最近 {days} 天",
        "=" * 50,
        "",
    ]
    for i, p in enumerate(papers, 1):
        title = p.get("title", "N/A")
        authors = p.get("authors", "N/A")
        published = p.get("published", "N/A")[:10]
        url = p.get("entry_url", "")
        lines.append(f"{i}. {title}")
        lines.append(f"   作者: {authors[:60]}")
        lines.append(f"   日期: {published} | {url}")
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="生成每日论文摘要报告")
    parser.add_argument("--days", type=int, default=1, help="生成多少天内的摘要 (default: 1)")
    parser.add_argument("--format", choices=["md", "txt", "brief", "all"], default="brief",
                        help="输出格式: brief=一句话简介(默认), md=完整 Markdown, txt=纯文本, all=全部")
    parser.add_argument("--output-dir", type=str, default=None, help="输出目录 (default: data/digests)")
    parser.add_argument("--quiet", action="store_true", help="静默模式，不打印内容")
    parser.add_argument("--today-only", action="store_true",
                        help="仅今日新增论文，输出简短格式（默认）")
    parser.add_argument("--published-date", type=str, default=None,
                        help="按 arXiv 发布日期筛选论文，格式 YYYY-MM-DD")
    args = parser.parse_args()

    config = load_config()
    output_dir = Path(args.output_dir or config.get("digest", {}).get("output_dir", "data/digests"))
    output_dir.mkdir(parents=True, exist_ok=True)

    # 获取论文：优先按 --published-date 筛选，否则按入库时间
    if args.published_date:
        papers = db.get_papers_by_published_date(args.published_date)
        date_label = args.published_date
    elif args.today_only or args.format == "brief":
        # 只取今天创建的论文
        papers = db.get_papers(since_days=1, limit=500)
        date_label = datetime.now().strftime("%Y-%m-%d")
    else:
        papers = db.get_papers(since_days=args.days, limit=500)
        date_label = datetime.now().strftime("%Y-%m-%d")

    today_str = date_label
    days_str = f"last_{args.days}_days"

    # 默认输出简短的一句话说报告
    if args.format == "brief":
        brief_content = generate_brief_today_digest(papers)
        brief_path = output_dir / f"brief_{today_str}.txt"
        brief_path.write_text(brief_content, encoding="utf-8")
        logger.info(f"一句话报已保存: {brief_path}")

        if not args.quiet:
            print(brief_content)
        logger.info(f"今日新增 {len(papers)} 篇论文")
        return

    # 其他格式（md / txt / all）
    if args.format in ("md", "all"):
        md_content = generate_markdown_digest(papers, days=args.days)
        md_path = output_dir / f"digest_{days_str}_{today_str}.md"
        md_path.write_text(md_content, encoding="utf-8")
        logger.info(f"Markdown 报告已保存: {md_path}")

        if not args.quiet:
            print(md_content)

    if args.format in ("txt", "all"):
        txt_content = generate_text_digest(papers, days=args.days)
        txt_path = output_dir / f"digest_{days_str}_{today_str}.txt"
        txt_path.write_text(txt_content, encoding="utf-8")
        logger.info(f"纯文本报告已保存: {txt_path}")

    logger.info(f"共处理 {len(papers)} 篇论文")


if __name__ == "__main__":
    main()
