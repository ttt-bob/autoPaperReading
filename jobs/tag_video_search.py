#!/usr/bin/env python3
"""给视频搜索专题页收录的论文同步添加 ``video search`` 标签。

专题页的策展列表和批量候选过滤逻辑集中在
``jobs.build_video_search_page``；这里复用同一份结果，避免主界面和专题页
出现不同的论文集合。

用法:
    uv run python jobs/tag_video_search.py
"""

from __future__ import annotations

import sqlite3

from build_video_search_page import DB_PATH, build_data

VIDEO_SEARCH_TAG = "video search"


def add_tag(tags: str | None) -> str:
    """Append the stable专题标签 once while preserving existing tags/order."""
    existing = [tag.strip() for tag in (tags or "").split(",") if tag.strip()]
    if VIDEO_SEARCH_TAG.lower() not in {tag.lower() for tag in existing}:
        existing.append(VIDEO_SEARCH_TAG)
    return ", ".join(existing)


def main() -> None:
    data = build_data()
    paper_ids = [paper["id"] for paper in data["papers"]]
    conn = sqlite3.connect(DB_PATH)
    updated = 0
    try:
        for paper_id in paper_ids:
            row = conn.execute(
                "SELECT tags FROM papers WHERE paper_id = ?", (paper_id,)
            ).fetchone()
            if not row:
                continue
            tags = add_tag(row[0])
            if tags == (row[0] or ""):
                continue
            conn.execute(
                """
                UPDATE papers
                   SET tags = ?, updated_at = CURRENT_TIMESTAMP
                 WHERE paper_id = ?
                """,
                (tags, paper_id),
            )
            updated += 1
        conn.commit()
    finally:
        conn.close()

    print(f"视频搜索专题收录: {len(paper_ids)} 篇")
    print(f"新增标签: {updated} 篇")


if __name__ == "__main__":
    main()
