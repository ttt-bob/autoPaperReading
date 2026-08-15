"""
rag/tag_utils.py - 标签规范化工具

提供 normalize_tags() 函数，将任意标签列表映射到 allowed_tags 范围内。
同时被 scripts/normalize_tags.py（历史清洗）和 rag/summarizer.py（每日入库）使用。
"""
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

import yaml


# =====================================================================
# 人工映射表：处理 SequenceMatcher 无法正确判断的语义映射
# 键是规范化后的键（lowercase + hyphens），值是 allowed_tags 中正确的标签
# 值若为 None 表示该标签在 allowed_tags 中没有合适映射，保留原标签
# =====================================================================
MANUAL_MAP: dict[str, str | None] = {
    # 分割类
    "image-segmentation": "semantic segmentation",
    # 特征提取 → 没有直接对应，保留原样
    "image-feature-extraction": None,
    # Image-to-Text / 图转文
    "image-to-text": "image captioning",
    "image-text": "image captioning",
    # 视频分类 → 没有直接对应
    "video-classification": None,
    # 视频生成
    "text-to-video": "video generation",
    "text-video": "video generation",
    # 视频转视频 → 没有直接对应
    "video-to-video": None,
    # 图转3D
    "image-to-3d": "text-to-3d",
    "image-3d": "text-to-3d",
    # 无条件的图像生成
    "unconditional-image-generation": "image generation",
    # Zero-shot 类 → 归入基础标签
    "zero-shot-image-classification": "image classification",
    "zero-shot-object-detection": "object detection",
    # 掩码生成 → 没有直接对应
    "mask-generation": None,
}


def load_allowed_tags(config_path: str | Path = "config.yaml") -> list[str]:
    """从 config.yaml 加载 allowed_tags"""
    cfg_path = Path(config_path)
    if not cfg_path.exists():
        raise FileNotFoundError(f"{cfg_path} 不存在")
    with open(cfg_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    tags = config.get("allowed_tags", [])
    if not tags:
        raise ValueError("config.yaml 中未定义 allowed_tags")
    return tags


def normalize_key(tag: str) -> str:
    """将标签转为规范化比较键：小写、统一连字符"""
    return re.sub(r"[-_\s]+", "-", tag.strip().lower())


def build_tag_map(allowed_tags: list[str]) -> dict[str, str]:
    """
    构建模糊匹配映射表：规范化键 -> 原始标签

    对每个 allowed_tag，生成多种变体：
    - 原始形式
    - 小写
    - 连字符统一形式
    - 空格统一形式
    """
    tag_map = {}
    for tag in allowed_tags:
        nk = normalize_key(tag)
        tag_map[nk] = tag

        space_key = tag.lower().replace("-", " ").replace("_", " ")
        tag_map[space_key] = tag

        no_sep = tag.lower().replace("-", "").replace("_", "").replace(" ", "")
        tag_map[no_sep] = tag

    return tag_map


def fuzzy_match(tag: str, allowed_tags: list[str], threshold: float = 0.75) -> str | None:
    """模糊匹配：用 SequenceMatcher 找最接近的 allowed_tag"""
    tag_clean = tag.strip().lower()
    best_match = None
    best_ratio = 0
    for allowed in allowed_tags:
        ratio = SequenceMatcher(None, tag_clean, allowed.lower()).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = allowed
    return best_match if best_ratio >= threshold else None


def normalize_tags(
    tags_str: str,
    tag_map: dict[str, str],
    allowed_tags: list[str],
    verbose: bool = False,
) -> list[str]:
    """
    将逗号分隔的标签字符串规范化到 allowed_tags 范围内。

    匹配策略（依次）：
      1. 精确匹配
      2. 规范化键匹配
      3. 空格版本匹配
      4. 无分隔符匹配
      5. 人工映射表 MANUAL_MAP
      6. 首字母大写再匹配
      7. 模糊匹配（threshold=0.75）
      8. ↪ 全部失败则保留原始标签（不再丢弃）
    """
    if not tags_str or not tags_str.strip():
        return []

    raw_tags = [t.strip() for t in tags_str.split(",") if t.strip()]
    result = []
    for t in raw_tags:
        # 1. 精确匹配
        if t in allowed_tags:
            result.append(t)
            continue

        # 2. 规范化键匹配
        nk = normalize_key(t)
        if nk in tag_map:
            result.append(tag_map[nk])
            continue

        # 3. 空格版本匹配
        space_key = t.lower().replace("-", " ").replace("_", " ")
        if space_key in tag_map:
            result.append(tag_map[space_key])
            continue

        # 4. 无分隔符匹配（"3d" → "3D"）
        no_sep = t.lower().replace("-", "").replace("_", "").replace(" ", "")
        if no_sep in tag_map:
            result.append(tag_map[no_sep])
            continue

        # 5. 人工映射表
        if nk in MANUAL_MAP:
            mapped = MANUAL_MAP[nk]
            if mapped is not None:
                result.append(mapped)
                continue
            if verbose:
                print(f"  ℹ️  保留（MANUAL_MAP 未映射）: '{t}'")
            result.append(t)
            continue

        # 6. 首字母大写再匹配
        title_key = t.strip().title()
        if title_key in allowed_tags:
            result.append(title_key)
            continue

        # 7. 模糊匹配（阈值更高，避免错配）
        matched = fuzzy_match(t, allowed_tags)
        if matched:
            result.append(matched)
            continue

        # 8. 全部失败 → 保留原标签
        if verbose:
            print(f"  ⚠️  无法匹配，保留原标签: '{t}'（考虑加入 config.yaml allowed_tags）")
        result.append(t)

    # 去重（保持顺序）
    seen = set()
    deduped = []
    for t in result:
        if t not in seen:
            seen.add(t)
            deduped.append(t)

    return deduped


def normalize_tags_str(tags_str: str, allowed_tags: list[str] | None = None, verbose: bool = False) -> str:
    """简便包装：直接传入 tags 字符串和 allowed_tags，返回规范化后的逗号分隔字符串"""
    if allowed_tags is None:
        allowed_tags = load_allowed_tags()
    tag_map = build_tag_map(allowed_tags)
    normalized = normalize_tags(tags_str, tag_map, allowed_tags, verbose=verbose)
    return ", ".join(normalized)