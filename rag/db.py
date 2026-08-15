"""
rag/db.py - SQLite 论文元数据存储
"""
import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path("data/papers.db")


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
    except sqlite3.Error:
        pass  # 只读场景或旧版本下忽略
    return conn


def init_db() -> None:
    """初始化数据库表"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS papers (
            paper_id      TEXT PRIMARY KEY,
            title         TEXT,
            authors       TEXT,
            abstract      TEXT,
            published     TEXT,
            pdf_url       TEXT,
            entry_url     TEXT,
            summary       TEXT,
            tags          TEXT,
            affiliations  TEXT,
            is_read       INTEGER DEFAULT 0,
            is_favorite   INTEGER DEFAULT 0,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # 向后兼容：如果 affiliations 列不存在则添加
    try:
        cur.execute("ALTER TABLE papers ADD COLUMN affiliations TEXT")
    except sqlite3.OperationalError:
        pass  # 列已存在
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ingest_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date    TEXT,
            papers_found  INTEGER,
            papers_new    INTEGER,
            papers_skipped INTEGER,
            papers_failed  INTEGER,
            started_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            finished_at  TIMESTAMP
        )
    """)
    # 收藏标签表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS favorite_tags (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_id    TEXT NOT NULL,
            tag         TEXT NOT NULL,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(paper_id, tag)
        )
    """)
    # 常用标签表（用户自定义的常用标签）
    cur.execute("""
        CREATE TABLE IF NOT EXISTS custom_tags (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tag         TEXT UNIQUE NOT NULL,
            color       TEXT DEFAULT '#6366f1',
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def paper_exists(paper_id: str) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM papers WHERE paper_id = ?", (paper_id,))
    row = cur.fetchone()
    conn.close()
    return row is not None


def save_paper(paper: dict) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO papers
        (paper_id, title, authors, abstract, published,
         pdf_url, entry_url, summary, tags, affiliations,
         updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (
        paper["paper_id"],
        paper["title"],
        paper["authors"],
        paper["abstract"],
        paper["published"],
        paper["pdf_url"],
        paper["entry_url"],
        paper.get("summary", ""),
        paper.get("tags", ""),
        paper.get("affiliations", ""),
    ))
    conn.commit()
    conn.close()


def get_paper_by_id(paper_id: str) -> Optional[dict]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM papers WHERE paper_id = ?", (paper_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def get_papers(since_days: int = 30, limit: int = 200, tag: str = None) -> list[dict]:
    """获取论文，可按时间范围和标签筛选"""
    conn = get_conn()
    cur = conn.cursor()

    if tag:
        # 按标签筛选（从 papers.tags 或 favorite_tags 模糊匹配）
        cur.execute("""
            SELECT DISTINCT p.*
            FROM papers p
            LEFT JOIN favorite_tags ft ON p.paper_id = ft.paper_id
            WHERE p.created_at >= datetime('now', ? || ' days')
              AND (
                   p.tags LIKE ? OR ft.tag = ?
              )
            ORDER BY p.published DESC
            LIMIT ?
        """, (f"-{since_days}", f"%{tag}%", tag, limit))
    else:
        cur.execute("""
            SELECT * FROM papers
            WHERE created_at >= datetime('now', ? || ' days')
            ORDER BY published DESC
            LIMIT ?
        """, (f"-{since_days}", limit))

    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_tags() -> list[dict]:
    """从 papers.tags 和 favorite_tags 汇总所有标签，按使用次数排序"""
    conn = get_conn()
    cur = conn.cursor()

    # 从 papers.tags 列聚合（逗号分隔）
    tag_counts: dict[str, int] = {}

    cur.execute("SELECT tags FROM papers WHERE tags IS NOT NULL AND tags != ''")
    for row in cur.fetchall():
        tags_str = row[0] or ""
        for t in tags_str.replace("\n", " ").split(","):
            t = t.strip().lower()
            if t:
                tag_counts[t] = tag_counts.get(t, 0) + 1

    # 从 favorite_tags 聚合
    cur.execute("""
        SELECT tag, COUNT(*) as count
        FROM favorite_tags
        GROUP BY tag
    """)
    for row in cur.fetchall():
        t = (row[0] or "").strip().lower()
        if t:
            tag_counts[t] = tag_counts.get(t, 0) + row[1]

    conn.close()

    return sorted([{"tag": t, "count": c} for t, c in tag_counts.items()],
                  key=lambda x: -x["count"])


def get_papers_by_published_date(date: str) -> list[dict]:
    """按 arXiv 发布日期查询论文

    Args:
        date: 日期字符串 YYYY-MM-DD

    Returns:
        该日发布的论文列表
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM papers
        WHERE DATE(published) = ?
        ORDER BY published DESC
    """, (date,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_today_papers() -> list[dict]:
    """获取今天入库的论文"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM papers
        WHERE DATE(created_at) = DATE('now')
        ORDER BY published DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_as_read(paper_id: str) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE papers SET is_read = 1 WHERE paper_id = ?", (paper_id,))
    conn.commit()
    conn.close()


def mark_as_favorite(paper_id: str) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE papers SET is_favorite = 1 WHERE paper_id = ?", (paper_id,))
    conn.commit()
    conn.close()


def log_ingest(run_date: str, found: int, new: int, skipped: int, failed: int) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO ingest_log (run_date, papers_found, papers_new, papers_skipped, papers_failed, finished_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (run_date, found, new, skipped, failed))
    conn.commit()
    conn.close()


def get_ingest_stats() -> dict:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            COUNT(*) as total,
            SUM(papers_new) as total_new,
            SUM(papers_found) as total_found
        FROM ingest_log
    """)
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else {}


def count_papers() -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM papers")
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0


def get_papers_missing_affiliations() -> list[dict]:
    """获取缺机构信息的论文"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM papers
        WHERE (affiliations IS NULL OR affiliations = '' OR affiliations = 'None')
        ORDER BY published DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ========== 收藏功能 ==========

def add_favorite(paper_id: str, tags: list[str]) -> None:
    """收藏论文并添加标签"""
    conn = get_conn()
    cur = conn.cursor()
    # 标记为收藏
    cur.execute("UPDATE papers SET is_favorite = 1 WHERE paper_id = ?", (paper_id,))
    # 添加标签
    for tag in tags:
        tag = tag.strip()
        if tag:
            cur.execute(
                "INSERT OR IGNORE INTO favorite_tags (paper_id, tag) VALUES (?, ?)",
                (paper_id, tag)
            )
    conn.commit()
    conn.close()


def remove_favorite(paper_id: str) -> None:
    """取消收藏"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE papers SET is_favorite = 0 WHERE paper_id = ?", (paper_id,))
    cur.execute("DELETE FROM favorite_tags WHERE paper_id = ?", (paper_id,))
    conn.commit()
    conn.close()


def get_favorites(tag: str = None) -> list[dict]:
    """获取收藏列表，可按标签筛选"""
    conn = get_conn()
    cur = conn.cursor()

    if tag:
        # 按标签筛选
        cur.execute("""
            SELECT p.*, GROUP_CONCAT(ft.tag) as favorite_tags
            FROM papers p
            JOIN favorite_tags ft ON p.paper_id = ft.paper_id
            WHERE p.is_favorite = 1 AND ft.tag = ?
            GROUP BY p.paper_id
            ORDER BY p.published DESC
        """, (tag,))
    else:
        # 获取所有收藏
        cur.execute("""
            SELECT p.*, GROUP_CONCAT(ft.tag) as favorite_tags
            FROM papers p
            JOIN favorite_tags ft ON p.paper_id = ft.paper_id
            WHERE p.is_favorite = 1
            GROUP BY p.paper_id
            ORDER BY p.published DESC
        """)

    rows = cur.fetchall()
    conn.close()

    results = []
    for row in rows:
        d = dict(row)
        # 解析标签列表
        d["favorite_tags"] = (d.get("favorite_tags") or "").split(",") if d.get("favorite_tags") else []
        results.append(d)
    return results


def get_favorite_tags() -> list[dict]:
    """获取所有收藏标签及其使用次数"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT tag, COUNT(*) as count
        FROM favorite_tags
        GROUP BY tag
        ORDER BY count DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_custom_tag(tag: str, color: str = "#6366f1") -> None:
    """添加常用标签"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO custom_tags (tag, color) VALUES (?, ?)",
        (tag.strip(), color)
    )
    conn.commit()
    conn.close()


def get_custom_tags() -> list[dict]:
    """获取常用标签"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM custom_tags ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def is_favorited(paper_id: str) -> bool:
    """检查论文是否已收藏"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT is_favorite FROM papers WHERE paper_id = ?", (paper_id,))
    row = cur.fetchone()
    conn.close()
    return row is not None and row["is_favorite"] == 1


def get_paper_favorite_tags(paper_id: str) -> list[str]:
    """获取论文的收藏标签"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT tag FROM favorite_tags WHERE paper_id = ?", (paper_id,))
    rows = cur.fetchall()
    conn.close()
    return [r["tag"] for r in rows]


def update_paper_favorite_tags(paper_id: str, tags: list[str]) -> None:
    """更新论文的收藏标签"""
    conn = get_conn()
    cur = conn.cursor()
    # 删除旧标签
    cur.execute("DELETE FROM favorite_tags WHERE paper_id = ?", (paper_id,))
    # 添加新标签
    for tag in tags:
        tag = tag.strip()
        if tag:
            cur.execute(
                "INSERT INTO favorite_tags (paper_id, tag) VALUES (?, ?)",
                (paper_id, tag)
            )
    conn.commit()
    conn.close()


def count_favorites() -> int:
    """获取收藏总数"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM papers WHERE is_favorite = 1")
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0
