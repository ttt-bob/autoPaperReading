#!/usr/bin/env python3
"""
jobs/retag_manual.py - 基于人工逐篇分析，为130篇论文手动设置准确的HuggingFace标签

Usage:
    python jobs/retag_manual.py
"""
import sqlite3
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

DB_PATH = Path("data/papers.db")

# 人工逐篇分析后的准确标签映射
MANUAL_TAGS = {
    # ===== 最新一批 (2025.05) =====
    "2605.06667v1": "Video Classification, 3D Reconstruction, Pose Estimation, Image-to-Video",
    "2605.06658v1": "Image Generation, 3D Reconstruction",
    "2605.06641v1": "Image Generation, Image-to-Text",
    "2605.06637v1": "Object Detection",
    "2605.06610v1": "Image Classification",
    "2605.06592v1": "Image Feature Extraction",
    "2605.06537v1": "Image-to-Text, Video Classification",
    "2605.06512v1": "Image Generation, Text-to-Video",
    "2605.06509v1": "Video Classification",
    "2605.06507v1": "Text-to-Image",
    "2605.06477v1": "Image-to-Text",
    "2605.06421v1": "Image Generation",
    "2605.06388v1": "Image Generation, Image-to-Text",
    "2605.06380v1": "Image Classification",
    "2605.06376v1": "Text-to-Image",
    "2605.06356v1": "Image-to-Video",
    "2605.06333v1": "Image Classification",
    "2605.06298v1": "3D Reconstruction",
    "2605.06280v1": "Image-to-Video",
    "2605.06274v1": "Image Classification",
    "2605.06270v1": "3D Reconstruction, Depth Estimation, Pose Estimation",
    "2605.06266v1": "Image Segmentation",
    "2605.06192v1": "Image Generation, Video Classification",
    "2605.06185v1": "Image-to-Text, Video Classification",
    "2605.06173v1": "Image-to-Text",
    "2605.06170v1": "Text-to-Image",
    "2605.06160v1": "Image Segmentation",
    "2605.06153v1": "Image Feature Extraction",
    "2605.06148v1": "Image Generation",
    "2605.06143v1": "Text-to-Image, Object Detection",
    "2605.06137v1": "Image Generation, Image Feature Extraction",
    "2605.06112v1": "Object Detection",
    "2605.06096v1": "Image-to-Text",
    "2605.06095v1": "Image Feature Extraction",
    "2605.06092v1": "Image Feature Extraction",
    "2605.06088v1": "Zero-Shot Object Detection, Image Segmentation",
    "2605.06084v1": "Object Detection, Image-to-Image",
    "2605.06083v1": "Image Classification",
    "2605.06080v1": "Image-to-Text",
    "2605.06070v1": "Text-to-Image",
    "2605.06064v1": "Image-to-Video",
    "2605.06058v1": "Image-to-Text",
    "2605.06051v1": "Video Classification, 3D Reconstruction",
    "2605.06049v1": "Image Segmentation, Image-to-Text",
    "2605.06043v1": "Image Classification, Image Feature Extraction",
    "2605.06021v1": "Image-to-Text",
    "2605.06012v1": "Text-to-Image",
    "2605.06010v1": "Object Detection",
    "2605.05997v1": "Image-to-Text",
    "2605.05979v1": "Image Segmentation",
    "2605.05945v1": "Video Classification, Pose Estimation",
    "2605.05941v1": "Object Detection",
    "2605.05928v1": "Object Detection",
    "2605.05910v1": "Zero-Shot Image Classification, Image-to-Text",
    "2605.05908v1": "Image Classification",
    "2605.05895v1": "Object Detection",
    "2605.05876v1": "3D Reconstruction",
    "2605.05848v1": "Image-to-Text",
    "2605.05831v1": "Image-to-Text",
    "2605.05820v1": "Zero-Shot Image Classification, Image Segmentation",
    "2605.05810v1": "Image-to-Text",
    "2605.05781v1": "Text-to-Image",
    "2605.05756v1": "Pose Estimation",
    "2605.05753v1": "Image Segmentation",
    "2605.05749v1": "3D Reconstruction",
    "2605.05722v1": "Image Segmentation, Depth Estimation",
    "2605.05712v1": "Pose Estimation",
    "2605.05694v1": "Image Classification",
    "2605.05688v1": "Image-to-Image",
    "2605.05674v1": "Image Feature Extraction",
    "2605.05668v1": "Image-to-Text",
    "2605.05664v1": "3D Reconstruction",
    "2605.05640v1": "Image-to-Text",
    "2605.05627v1": "Image Segmentation, Image-to-Text",
    "2605.05616v1": "Image Segmentation",
    "2605.05572v1": "Text-to-3D, Image-to-Text",
    "2605.05510v1": "Image-to-Image",
    "2605.05405v1": "Image-to-Text",
    "2605.05390v1": "Pose Estimation, Object Detection",
    "2605.05372v1": "3D Reconstruction",
    "2605.05344v1": "Object Detection, Image-to-Text",
    "2605.05331v1": "Image Generation",
    "2605.05328v1": "Object Detection",
    "2605.05207v1": "3D Reconstruction, Depth Estimation, Pose Estimation",
    "2605.05206v1": "Text-to-Image",
    "2605.05204v1": "Text-to-Image, Image-to-Text",
    "2605.05187v1": "Image-to-Text",
    "2605.05185v1": "Image-to-Text",
    "2605.05163v1": "Text-to-3D, Image-to-Text",
    "2605.05161v1": "Zero-Shot Image Classification",
    "2605.05095v1": "3D Reconstruction",
    "2605.05079v1": "Image-to-Image",
    "2605.05077v1": "Image Segmentation, Text-to-Image",
    "2605.05072v1": "3D Reconstruction",
    "2605.05071v1": "Object Detection",
    "2605.05054v1": "Image Feature Extraction",
    "2605.05045v1": "Image-to-Image",
    "2605.05031v1": "Image Generation",
    "2605.05027v1": "Image Feature Extraction",
    "2605.05026v1": "Image Generation",
    "2605.04044v1": "3D Reconstruction",
    "2605.04040v1": "Text-to-Image, Text-to-Video",
    "2605.03999v1": "Image Segmentation",
    "2605.03968v1": "Image Segmentation, Object Detection",
    "2605.03950v1": "Image-to-Text",
    "2605.03941v1": "Video Classification",
    "2605.03927v1": "Image-to-Text, Object Detection",
    "2605.03909v1": "Image Feature Extraction",
    "2605.03885v1": "Image Classification",
    "2605.03877v1": "Image Generation",
    # ===== YOLO 系列 (按版本从新到旧) =====
    "2601.12882v2": "Object Detection",
    "2510.09653v3": "Object Detection",
    "2509.25164v5": "Object Detection",
    "2506.17733v2": "Object Detection",
    "2502.12524v1": "Object Detection",
    "2410.17725v1": "Object Detection",
    "2405.14458v2": "Object Detection",
    "2402.13616v2": "Object Detection",
    "2301.05586v1": "Object Detection",
    "2209.02976v1": "Object Detection",
    "2207.02696v1": "Object Detection",
    "2004.10934v1": "Object Detection",
    "1804.02767v1": "Object Detection",
    "1612.08242v1": "Object Detection",
    "1512.03385v1": "Image Classification",
    "1506.02640v5": "Object Detection",
    "1706.03762v7": "Image Classification",
    # ===== 经典论文 =====
    "pdf_c838af9838929c0a": "Image Classification",
    "2605.06263v1": "Object Detection",
    "2605.06189v1": "Object Detection",
    "2602.14582v1": "Image Generation",
}


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 验证所有 paper_id 都存在
    cur.execute("SELECT paper_id FROM papers")
    all_ids = set(r[0] for r in cur.fetchall())
    mapping_ids = set(MANUAL_TAGS.keys())

    missing = mapping_ids - all_ids
    extra = all_ids - mapping_ids

    if missing:
        print(f"⚠️  映射表中存在但数据库中不存在的 paper_id: {missing}")
    if extra:
        print(f"⚠️  数据库中存在但映射表中未覆盖的 paper_id ({len(extra)} 个): {list(extra)[:5]}...")

    print(f"数据库论文数: {len(all_ids)}, 映射表条目: {len(mapping_ids)}")

    # 更新
    updates = []
    for paper_id, tags in MANUAL_TAGS.items():
        if paper_id in all_ids:
            updates.append((tags, paper_id))

    cur.executemany("UPDATE papers SET tags = ? WHERE paper_id = ?", updates)
    conn.commit()
    print(f"✅ 更新了 {cur.rowcount} 篇论文")

    # 导出 papers.json
    cur.execute("""
        SELECT paper_id, title, authors, abstract, published,
               pdf_url, entry_url, summary, tags, created_at
        FROM papers ORDER BY published DESC
    """)
    rows = cur.fetchall()
    conn.close()

    papers_out = []
    for row in rows:
        papers_out.append({
            "paper_id": row[0],
            "title": row[1],
            "authors": row[2],
            "abstract": row[3],
            "published": row[4],
            "pdf_url": row[5],
            "entry_url": row[6],
            "summary": row[7],
            "tags": row[8],
            "created_at": row[9],
        })

    all_tags = set()
    for p in papers_out:
        for t in (p["tags"] or "").split(","):
            t = t.strip()
            if t:
                all_tags.add(t)

    docs_path = Path("docs")
    with open(docs_path / "papers.json", "w", encoding="utf-8") as f:
        json.dump({"papers": papers_out, "stats": {
            "total": len(papers_out),
            "topics": len(all_tags),
            "lastUpdated": papers_out[0]["published"][:10] if papers_out else None,
        }}, f, ensure_ascii=False, indent=2)

    print(f"\n✅ papers.json 更新完成")
    print(f"   论文数量: {len(papers_out)}")
    print(f"   标签类别数: {len(all_tags)}")
    print(f"\n--- 标签分布 ---")
    for tag in sorted(all_tags):
        count = sum(1 for p in papers_out if tag in (p["tags"] or ""))
        print(f"  {tag}: {count} 篇")


if __name__ == "__main__":
    main()
