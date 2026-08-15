#!/usr/bin/env python3
"""
jobs/retag_papers.py - 将所有论文的标签重新映射到 22 个 HuggingFace 固定类别

Usage:
    uv run python jobs/retag_papers.py

映射逻辑：基于关键词匹配，将历史自由标签映射到固定类别。
"""
import re
import sqlite3
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

DB_PATH = Path("data/papers.db")

HF_TAGS = [
    "Depth Estimation", "Image Classification", "Object Detection", "Image Segmentation",
    "Text-to-Image", "Image-to-Text", "Image-to-Image", "Image-to-Video",
    "Unconditional Image Generation", "Video Classification", "Text-to-Video",
    "Zero-Shot Image Classification", "Mask Generation", "Zero-Shot Object Detection",
    "Text-to-3D", "Image-to-3D", "Image Feature Extraction", "Keypoint Detection",
    "Video-to-Video", "Image Generation", "Pose Estimation", "3D Reconstruction",
]

# 关键词 -> HuggingFace 标签 映射表
# 重要：按优先级排序，精确的复合关键词放前面，泛化词放后面
KEYWORD_MAP = [
    # ======= 零样本检测（最具体，优先匹配）=======
    ("zero-shot object detection", "Zero-Shot Object Detection"),
    ("open-vocabulary detection", "Zero-Shot Object Detection"),
    ("open vocabulary detection", "Zero-Shot Object Detection"),

    # ======= 零样本分类 ========
    ("zero-shot image classification", "Zero-Shot Image Classification"),
    ("zero-shot learning", "Zero-Shot Image Classification"),
    ("zero-shot classification", "Zero-Shot Image Classification"),

    # ======= 图像分割（具体 > 泛化）=======
    ("semantic segmentation", "Image Segmentation"),
    ("instance segmentation", "Image Segmentation"),
    ("panoptic segmentation", "Image Segmentation"),
    ("segment anything", "Image Segmentation"),
    ("maskrcnn", "Image Segmentation"),
    ("segmentation", "Image Segmentation"),

    # ======= 图像生成（具体 > 泛化 diffusion/gan）=======
    ("text-to-image", "Text-to-Image"),
    ("text to image", "Text-to-Image"),
    ("t2i ", "Text-to-Image"),
    ("stable diffusion", "Image Generation"),
    ("unconditional image generation", "Unconditional Image Generation"),
    ("gan", "Image Generation"),
    ("diffusion model", "Image Generation"),
    ("generative model", "Image Generation"),
    ("image generation", "Image Generation"),

    # ======= 3D（具体 > 泛化）=======
    ("text-to-3d", "Text-to-3D"),
    ("image-to-3d", "Image-to-3D"),
    ("3d reconstruction", "3D Reconstruction"),
    ("novel view synthesis", "3D Reconstruction"),
    ("point cloud", "3D Reconstruction"),
    ("nerf", "3D Reconstruction"),

    # ======= 深度估计 ========
    ("depth estimation", "Depth Estimation"),
    ("monocular depth", "Depth Estimation"),
    ("depth prediction", "Depth Estimation"),

    # ======= 姿态估计 ========
    ("pose estimation", "Pose Estimation"),
    ("human pose", "Pose Estimation"),

    # ======= 关键点检测 ========
    ("keypoint detection", "Keypoint Detection"),

    # ======= 目标检测（具体 > 泛化）=======
    ("faster r-cnn", "Object Detection"),
    ("yolo", "Object Detection"),
    ("ssd", "Object Detection"),
    ("detectron", "Object Detection"),
    ("bounding box", "Object Detection"),
    ("object detection", "Object Detection"),

    # ======= 视频生成/分类（video 在 diffusion 前，防止被 diffusion 抢）=======
    ("text-to-video", "Text-to-Video"),
    ("t2v ", "Text-to-Video"),
    ("text to video", "Text-to-Video"),
    ("video generation", "Video Classification"),
    ("video classification", "Video Classification"),
    ("action recognition", "Video Classification"),
    ("action detection", "Video Classification"),
    ("image-to-video", "Image-to-Video"),
    ("i2v generation", "Image-to-Video"),

    # ======= 视频处理 ========
    ("video-to-video", "Video-to-Video"),
    ("vid2vid", "Video-to-Video"),
    ("video editing", "Video-to-Video"),
    ("video translation", "Video-to-Video"),

    # ======= 图像编辑/增强（比 image generation 更具体）=======
    ("image-to-image", "Image-to-Image"),
    ("image translation", "Image-to-Image"),
    ("style transfer", "Image-to-Image"),
    ("image editing", "Image-to-Image"),
    ("image inpainting", "Image-to-Image"),
    ("image denoising", "Image-to-Image"),
    ("image restoration", "Image-to-Image"),
    ("image enhancement", "Image-to-Image"),
    ("super resolution", "Image-to-Image"),

    # ======= 掩码生成 ========
    ("mask generation", "Mask Generation"),

    # ======= 视觉-语言（具体 > 泛化）=======
    ("visual question answering", "Image-to-Text"),
    ("vqa", "Image-to-Text"),
    ("image caption", "Image-to-Text"),
    ("captioning", "Image-to-Text"),
    ("vision language model", "Image-to-Text"),
    ("multimodal large language model", "Image-to-Text"),
    ("large multimodal model", "Image-to-Text"),
    ("image-to-text", "Image-to-Text"),
    ("visual reasoning", "Image-to-Text"),

    # ======= 图像特征 / 表征学习 ========
    ("self-supervised learning", "Image Feature Extraction"),
    ("contrastive learning", "Image Feature Extraction"),
    ("representation learning", "Image Feature Extraction"),
    ("image feature", "Image Feature Extraction"),
    ("feature extraction", "Image Feature Extraction"),
    ("embedding", "Image Feature Extraction"),

    # ======= 图像分类（兜底，vit/resnet 等放前面）=======
    ("vision transformer", "Image Classification"),
    ("clip", "Image Classification"),
    ("efficientnet", "Image Classification"),
    ("mobilenet", "Image Classification"),
    ("resnet", "Image Classification"),
    ("fine-grained classification", "Image Classification"),
    ("image classification", "Image Classification"),

    # ======= 其他 ========
    ("skeleton", "Pose Estimation"),
    ("stereo", "Depth Estimation"),
    ("vlm", "Image-to-Text"),
    ("llava", "Image-to-Text"),
    ("ovd", "Zero-Shot Object Detection"),
]



def match_tags(text: str) -> list[str]:
    """基于关键词匹配返回对应的 HuggingFace 标签列表，使用单词边界精确匹配"""
    text_lower = text.lower()
    matched = []
    for keyword, hf_tag in KEYWORD_MAP:
        if re.search(r'\b' + re.escape(keyword) + r'\b', text_lower) and hf_tag not in matched:
            matched.append(hf_tag)
    return matched


def retag_all(force: bool = False):
    # 1. 读 DB
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT paper_id, title, abstract, summary, tags FROM papers")
    papers = cur.fetchall()

    updates = []
    for row in papers:
        # 综合 title + abstract + summary + 现有 tags 来匹配
        combined = " ".join([
            row["title"] or "",
            row["abstract"] or "",
            row["summary"] or "",
            row["tags"] or "",
        ])
        new_tags = match_tags(combined)

        if new_tags:
            new_tags_str = ", ".join(new_tags)
        else:
            new_tags_str = ""

        if force or row["tags"] != new_tags_str:
            updates.append((new_tags_str, row["paper_id"]))

    print(f"读取到 {len(papers)} 篇论文")
    print(f"需要更新标签的论文: {len(updates)} 篇")

    if not updates:
        print("没有需要更新的论文")
        conn.close()
        return

    # 2. 写 DB
    cur.executemany(
        "UPDATE papers SET tags = ? WHERE paper_id = ?",
        updates
    )
    conn.commit()
    print(f"DB 更新完成: {cur.rowcount} 行")

    # 3. 重新导出 papers.json
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
            "paper_id": row["paper_id"],
            "title": row["title"],
            "authors": row["authors"],
            "abstract": row["abstract"],
            "published": row["published"],
            "pdf_url": row["pdf_url"],
            "entry_url": row["entry_url"],
            "summary": row["summary"],
            "tags": row["tags"],
            "created_at": row["created_at"],
        })

    all_tags = set()
    for p in papers_out:
        for t in (p["tags"] or "").split(","):
            t = t.strip()
            if t:
                all_tags.add(t)

    docs_path = Path("docs")
    papers_file = docs_path / "papers.json"
    with open(papers_file, "w", encoding="utf-8") as f:
        json.dump({"papers": papers_out, "stats": {
            "total": len(papers_out),
            "topics": len(all_tags),
            "lastUpdated": papers_out[0]["published"][:10] if papers_out else None,
        }}, f, ensure_ascii=False, indent=2)

    print(f"✅ papers.json 更新完成")
    print(f"   论文数量: {len(papers_out)}")
    print(f"   标签类别数: {len(all_tags)}")
    print(f"   标签列表: {sorted(all_tags)}")

    # 打印标签分布
    print("\n--- 标签分布 ---")
    for tag in sorted(all_tags):
        count = sum(1 for p in papers_out if tag in (p["tags"] or ""))
        print(f"  {tag}: {count} 篇")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="重映射论文标签到 HuggingFace 固定类别")
    parser.add_argument("--force", action="store_true", help="强制重跑，不比较现有标签")
    args = parser.parse_args()
    retag_all(force=args.force)
