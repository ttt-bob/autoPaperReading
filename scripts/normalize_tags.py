#!/usr/bin/env python3
"""
scripts/normalize_tags.py - 标签规范化清洗脚本

将数据库中已有论文的标签映射到 config.yaml 中定义的 allowed_tags 范围内，
消除重复变体（如 "image to" vs "image-to-image" vs "image to image"）。

用法:
    uv run python scripts/normalize_tags.py           # 默认（打印变更，不写入）
    uv run python scripts/normalize_tags.py --apply   # 真正写入数据库
    uv run python scripts/normalize_tags.py --apply --dry-run  # 预览变更
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rag import db
from rag.tag_utils import load_allowed_tags, build_tag_map, normalize_tags


def main():
    import argparse
    parser = argparse.ArgumentParser(description="标签规范化清洗")
    parser.add_argument("--apply", action="store_true", help="将规范化结果写入数据库")
    parser.add_argument("--dry-run", action="store_true", help="预览变更（不写入）")
    args = parser.parse_args()

    allowed_tags = load_allowed_tags()
    tag_map = build_tag_map(allowed_tags)
    print(f"📋 允许标签 ({len(allowed_tags)} 个): {', '.join(allowed_tags)}")

    papers = db.get_papers(since_days=365, limit=99999)
    print(f"📄 数据库中共有 {len(papers)} 篇论文")

    changes = 0
    unchanged = 0
    tag_counts_before: dict[str, int] = {}
    tag_counts_after: dict[str, int] = {}

    for p in papers:
        old_tags_str = (p.get("tags") or "").strip()
        for t in old_tags_str.split(","):
            t = t.strip()
            if t:
                tag_counts_before[t] = tag_counts_before.get(t, 0) + 1

        new_tags = normalize_tags(old_tags_str, tag_map, allowed_tags, verbose=True)
        new_tags_str = ", ".join(new_tags)

        if old_tags_str == new_tags_str:
            unchanged += 1
        else:
            changes += 1
            print(f"\n  [{p['paper_id']}] {p['title'][:50]}")
            print(f"    🔴 旧: {old_tags_str or '(空)'}")
            print(f"    🟢 新: {new_tags_str or '(空)'}")

            if args.apply and not args.dry_run:
                conn = db.get_conn()
                cur = conn.cursor()
                cur.execute(
                    "UPDATE papers SET tags = ?, updated_at = CURRENT_TIMESTAMP WHERE paper_id = ?",
                    (new_tags_str, p["paper_id"]),
                )
                conn.commit()
                conn.close()

        for t in new_tags:
            tag_counts_after[t] = tag_counts_after.get(t, 0) + 1

    print(f"\n{'='*50}")
    print(f"📊 统计")
    print(f"  未变: {unchanged} 篇")
    print(f"  变更: {changes} 篇")
    print(f"")
    print(f"  标签数: {len(tag_counts_before)} → {len(tag_counts_after)}")
    print(f"")
    print(f"  🔴 旧标签分布 ({len(tag_counts_before)} 个):")
    for t, c in sorted(tag_counts_before.items(), key=lambda x: -x[1]):
        print(f"    {t}: {c}篇")
    print(f"")
    print(f"  🟢 新标签分布 ({len(tag_counts_after)} 个):")
    for t, c in sorted(tag_counts_after.items(), key=lambda x: -x[1]):
        print(f"    {t}: {c}篇")

    if not args.apply:
        print(f"\n💡 预览模式，未写入数据库。加上 --apply 确认写入。")

    if args.dry_run:
        print(f"\n💡 --dry-run 模式，未实际写入。去掉 --dry-run 确认写入。")


if __name__ == "__main__":
    main()