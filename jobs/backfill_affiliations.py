#!/usr/bin/env python3
"""
补全历史论文的机构信息

逻辑：
1. 遍历所有论文的已有总结文本
2. 尝试从总结中提取机构信息（extract_affiliations_from_summary）
3. 如果提取失败，重新调用 LLM 生成总结并提取
4. 将结果写回数据库，然后重新导出 JSON

Usage:
    uv run python jobs/backfill_affiliations.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rag import db, summarizer

def backfill_affiliations():
    import argparse
    parser = argparse.ArgumentParser(description="补全论文机构信息")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写入数据库")
    parser.add_argument("--regenerate", action="store_true", help="强制重新生成总结（即使已有）")
    parser.add_argument("--limit", type=int, default=0, help="最多处理多少篇（0=全部）")
    args = parser.parse_args()

    conn = db.get_conn()
    cur = conn.cursor()

    # 获取所有论文
    if args.regenerate:
        cur.execute("SELECT paper_id, title, authors, abstract, summary FROM papers ORDER BY published DESC")
    else:
        cur.execute("""
            SELECT paper_id, title, authors, abstract, summary
            FROM papers
            WHERE affiliations IS NULL OR affiliations = '' OR affiliations = 'None'
            ORDER BY published DESC
        """)
    rows = cur.fetchall()
    conn.close()

    papers = [dict(r) for r in rows]
    if args.limit > 0:
        papers = papers[:args.limit]

    print(f"共 {len(papers)} 篇论文需要处理（regenerate={args.regenerate}）")

    updated = 0
    failed = 0
    skipped = 0

    for i, paper in enumerate(papers, 1):
        pid = paper["paper_id"]
        title_short = paper["title"][:60]

        # 先尝试从已有总结中提取
        existing_aff = summarizer.extract_affiliations_from_summary(paper.get("summary", ""))
        aff = existing_aff

        if not aff:
            print(f"[{i}/{len(papers)}] {pid} - {title_short}: 已有总结提取失败，重新生成...")
            try:
                from rag import pdf_parser
                category = pdf_parser.infer_category(paper["title"] or "", paper["abstract"] or "")
                safe_id = pid.replace("/", "_")
                pdf_path = Path(f"data/pdfs/{category}/{safe_id}.pdf")
                if not pdf_path.exists():
                    project_root = Path(__file__).parent.parent
                    pdf_path = project_root / f"data/pdfs/{category}/{safe_id}.pdf"

                if not pdf_path.exists():
                    print(f"  ⚠️  PDF 不存在，跳过: {pdf_path}")
                    failed += 1
                    continue

                full_text = pdf_parser.parse_pdf_text(pdf_path)
                if not full_text.strip():
                    print(f"  ⚠️  PDF 解析为空，跳过")
                    failed += 1
                    continue

                summary = summarizer.summarize_paper(
                    title=paper["title"],
                    abstract=paper["abstract"],
                    authors=paper.get("authors", ""),
                    full_text=full_text[:20000],
                )
                aff = summarizer.extract_affiliations_from_summary(summary)

                if args.dry_run:
                    print(f"  [DRY RUN] 新总结已生成，机构信息: {aff or '(未提取到)'}")
                else:
                    db.save_paper({
                        **paper,
                        "summary": summary,
                        "affiliations": aff,
                    })
                    print(f"  ✅ 总结已更新，机构: {aff or '(未提取到)'}")
            except Exception as e:
                print(f"  ❌ 失败: {e}")
                failed += 1
                continue
        else:
            skipped += 1

        if not args.dry_run and aff:
            conn2 = db.get_conn()
            cur2 = conn2.cursor()
            cur2.execute("UPDATE papers SET affiliations = ? WHERE paper_id = ?", (aff, pid))
            conn2.commit()
            conn2.close()
            print(f"[{i}/{len(papers)}] {pid} - {title_short}: ✅ 已更新机构")
            updated += 1
        elif args.dry_run and aff:
            print(f"[{i}/{len(papers)}] {pid} - {title_short}: [DRY RUN] 机构: {aff}")

    print(f"\n完成: 更新 {updated} 篇, 跳过(已有) {skipped} 篇, 失败 {failed} 篇")
    if args.dry_run:
        print("（以上为 dry-run 预览，未写入数据库）")


if __name__ == "__main__":
    backfill_affiliations()
