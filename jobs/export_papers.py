#!/usr/bin/env python3
"""
jobs/export_papers.py - 导出论文数据为前端 JSON 文件

Usage:
    uv run python jobs/export_papers.py

输出：
    docs/papers.json   # 前端数据
    frontend/papers_count.json  # 统计信息
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rag import pdf_parser
from rag.db import DB_PATH
from rag.summarizer import has_valid_summary

# 云端缓存版本号（由 run_daily.sh 每次 push 时更新）
CACHE_VERSION = datetime.now().strftime("%Y%m%d%H%M%S")


def find_local_pdf_path(project_root: Path, category: str, paper_id: str) -> str:
    """Return the existing local PDF path, falling back across category folders."""
    safe_id = paper_id.replace("/", "_")
    inferred_path = Path("data") / "pdfs" / category / f"{safe_id}.pdf"
    if (project_root / inferred_path).exists():
        return inferred_path.as_posix()

    matches = sorted((project_root / "data" / "pdfs").glob(f"*/{safe_id}.pdf"))
    if matches:
        return matches[0].relative_to(project_root).as_posix()
    return ""


def extract_code_url_from_summary(summary: str) -> str:
    """
    从总结文本中提取 GitHub / 项目页面 URL
    """
    if not summary:
        return ""
    patterns = [
        r'https?://github\.com/[a-zA-Z0-9_\-]+/[a-zA-Z0-9_\-.\-]+',
        r'https?://[a-zA-Z0-9_\-]+\.github\.io/[a-zA-Z0-9_\-/\.]+',
        r'https?://project\.page/[^\s<>"\']+',
    ]
    for pattern in patterns:
        match = re.search(pattern, summary)
        if match:
            return match.group(0).rstrip('.,;')
    return ""


def export_papers(is_cloud: bool = False):
    """
    导出论文数据，local_pdf_path 始终导出，前端 isLocalHost() 控制显示。
    is_cloud=True 时额外更新 index.html 的 CSS 版本号。
    """
    import sqlite3

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT paper_id, title, authors, abstract, published,
               pdf_url, entry_url, summary, tags, affiliations, created_at
        FROM papers
        ORDER BY published DESC
    """)
    rows = cur.fetchall()

    papers = []
    skipped_incomplete = 0
    for row in rows:
        paper_id = row["paper_id"]
        category = pdf_parser.infer_category(row["title"] or "", row["abstract"] or "")
        project_root = Path(__file__).parent.parent
        local_pdf_rel_path = find_local_pdf_path(project_root, category, paper_id)

        summary = row["summary"] or ""
        if not has_valid_summary(summary):
            skipped_incomplete += 1
            continue

        code_url = extract_code_url_from_summary(summary)
        affiliations = row["affiliations"] or ""
        if affiliations:
            affiliations = re.sub(
                r'(arXiv|arxiv|\d{4}[-/]\d{2}[-/]\d{2}|发表时间).*',
                '', affiliations
            ).strip()

        paper_data = {
            "paper_id": paper_id,
            "title": row["title"],
            "authors": row["authors"],
            "abstract": row["abstract"],
            "published": row["published"],
            "pdf_url": row["pdf_url"],
            "entry_url": row["entry_url"],
            "code_url": code_url,
            "summary": summary,
            "tags": row["tags"],
            "affiliations": affiliations,
            "created_at": row["created_at"],
        }

        # 始终添加本地 PDF 路径，前端根据 isLocalHost() 决定是否显示
        if local_pdf_rel_path:
            paper_data["local_pdf_path"] = local_pdf_rel_path

        papers.append(paper_data)

    conn.close()

    out_dir = Path("docs")
    out_dir.mkdir(exist_ok=True)

    # 云端模式：更新 index.html 中 style.css 版本号，防止 CDN 缓存
    if is_cloud:
        index_html = out_dir / "index.html"
        if index_html.exists():
            content = index_html.read_text(encoding="utf-8")
            updated = re.sub(
                r'href="style\.css\?v=[^"]*"',
                f'href="style.css?v={CACHE_VERSION}"',
                content
            )
            if updated != content:
                index_html.write_text(updated, encoding="utf-8")
                print(f"   [云端] index.html 版本号更新: v={CACHE_VERSION}")

    all_tags = set()
    for p in papers:
        for t in (p["tags"] or "").split(","):
            t = t.strip()
            if t:
                all_tags.add(t)

    stats = {
        "total": len(papers),
        "topics": len(all_tags),
        "lastUpdated": papers[0]["published"][:10] if papers else None,
    }

    papers_out = out_dir / "papers.json"
    with open(papers_out, "w", encoding="utf-8") as f:
        json.dump({"papers": papers, "stats": stats}, f, ensure_ascii=False, indent=2)

    favorites_out = out_dir / "favorites.json"
    favorites_data = {
        "exported_at": datetime.now().isoformat(),
        "notes": "收藏数据，可导入到其他设备。点击前端设置按钮导入。"
    }
    with open(favorites_out, "w", encoding="utf-8") as f:
        json.dump(favorites_data, f, ensure_ascii=False, indent=2)

    print(f"✅ 导出完成: {papers_out}" + (" [云端模式]" if is_cloud else " [本地模式]"))
    print(f"   论文数量: {len(papers)}")
    if skipped_incomplete:
        print(f"   已跳过无有效总结: {skipped_incomplete}")
    print(f"   标签数量: {len(all_tags)}")
    print(f"   有代码链接: {sum(1 for p in papers if p.get('code_url'))}")
    if not is_cloud:
        print(f"   有本地 PDF: {sum(1 for p in papers if p.get('local_pdf_path'))}")
    if papers:
        print(f"   最新日期: {papers[0]['published'][:10]}")
    print(f"   收藏数据: {favorites_out} (可导入)")
    print("   运行前端: python -m http.server 8080 --directory docs")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--cloud", action="store_true", help="云端模式：更新 index.html CSS 版本号防止缓存")
    args = parser.parse_args()
    export_papers(is_cloud=args.cloud)
