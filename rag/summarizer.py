"""
rag/summarizer.py - 论文中文结构化详细总结
"""
import logging
import re

from dotenv import load_dotenv

from rag.llm_client import chat
from rag.tag_utils import normalize_tags_str

load_dotenv()

logger = logging.getLogger(__name__)

FAILED_SUMMARY_PREFIXES = (
    "[总结生成失败:",
    "总结生成失败:",
)


def has_valid_summary(summary: str | None) -> bool:
    """判断 summary 是否可发布：非空，且不是失败占位内容。"""
    if not summary or not summary.strip():
        return False

    text = summary.strip()
    return not any(text.startswith(prefix) for prefix in FAILED_SUMMARY_PREFIXES)


def clean_summary(summary: str) -> str:
    """
    清理总结文本，移除：
    - prompt 指令混入的文字（如"不要翻译"、"不要缩写"等提示词）
    - 纯提示词行（如"数据集（全称，不要缩写）："这种）
    - 多余的引导语（如"好的，以下是详细总结："）
    - 没有 section header 的原始文本块（强制加上缺失的 header）
    """
    if not summary:
        return summary

    lines = summary.split('\n')
    cleaned = []
    skip_patterns = [
        r'^以下是论文信息',
        r'^【论文',
        r'^好的[,，]',
        r'^我将严格',
        r'^按照要求',
        r'^请对以下',
        r'^严格按',
        r'^以下是一篇',
        r'^这是一篇',
        r'^请提取',
        r'^首先提取',
        r'^接下来提取',
    ]
    leak_phrases = [
        '不要翻译',
        '不要缩写',
        '不要省略',
        '不要使用',
        '请严格按',
        '全称，不要缩写',
        '全称不要缩写',
        '原文姓名，不要翻译',
        '不要写省略号',
        '请提取：',
        '（如果',
        '（如',
        '（如果论文',
        '只输出标签列表',
    ]

    for line in lines:
        # 跳过明显是 prompt 残留的引导行
        if any(re.match(p, line.strip()) for p in skip_patterns):
            continue
        # 跳过纯提示词行（行尾是冒号且前面没有实际内容）
        stripped = line.strip()
        if re.match(r'^[-*]?\s*[\u4e00-\u9fa5（()（）]+[：:]\s*$', stripped):
            continue
        # 跳过行内含大量提示词的情况
        if stripped and not stripped.startswith('#'):
            leak_count = sum(1 for p in leak_phrases if p in stripped)
            if leak_count >= 2 and len(stripped) < 100:
                continue
        # 检测是否是 section header
        is_section = bool(re.match(r'^#{1,3}\s+[零一二三四五六七八九十\d]+[.、]', stripped))
        # 检测裸文本行（没有 # 但看起来像章节名的内容）
        is_bare_section = (
            not is_section
            and not stripped.startswith('#')
            and re.match(r'^[一二三四五六七八九十零\d]+[.、]', stripped)
        )
        if is_bare_section:
            # 加上 ## 前缀使其成为标准 Markdown
            cleaned.append('## ' + stripped)
            continue
        # 跳过连续的空 section header 行
        if is_section and len(stripped) < 5:
            continue
        cleaned.append(line)

    text = '\n'.join(cleaned)
    # 去掉开头的引导语
    text = re.sub(r'^好的[，,][\s\S]*?总结[。\.：:]\s*', '', text, count=1)
    text = re.sub(r'^作为[\s\S]*?总结[。\.：:]\s*', '', text, count=1)
    return text.strip()


def summarize_paper(
    title: str,
    abstract: str,
    authors: str = "",
    full_text: str = "",
    model: str = "deepseek-v4-flash",
    max_chars: int = 20000,
    language: str = "zh",
) -> str:
    """
    使用 LLM 生成论文的详细结构化总结（中文）

    输出格式（详细版）：
    1. 论文基本信息
    2. 研究背景与动机
    3. 一句话总结
    4. 核心创新点
    5. 方法详解
    6. 实验设置
    7. 实验结果
    8. 局限性
    9. 未来研究方向
    10. 对工程/研究的启发
    11. 适合标签
    """
    text = full_text[:max_chars] if full_text else ""

    system_prompt = (
        "你是一个专业的计算机视觉和人工智能论文阅读助手。\n"
        "请严格按照下面的格式输出总结，每项都要有内容。\n"
        "输出时不要在回答中提及任何格式要求或提示词，只输出论文总结本身。"
    )

    user_prompt = f"""请对以下论文进行详细总结，严格按下面的格式逐项输出。

【格式要求】
- 每节用 ## 标题 的 Markdown 格式
- 一、论文基本信息 中的所有字段（标题、作者列表、所属机构、发表时间、开源代码地址、开源许可证）都要逐行写出，不得省略或合并
- 如果某字段无法确定，写"未明确"，但必须写出该字段行
- 不要把多个字段的内容写在同一行

【输出格式（示例）】
## 一、论文基本信息
标题：HEART: Hyperspherical Embedding Alignment via Kent-Representation Traversal in Diffusion Models
作者列表（原文）：Arani Roy, Shristi Das Biswas, Kaushik Roy
所属机构：Purdue University
发表时间：2026年5月8日（arXiv预印本，编号arXiv:2605.07973v1）
开源代码地址：未明确
开源许可证类型：未明确

## 二、研究背景与动机
- 该研究要解决什么问题：...
- 目前最好的方法存在哪些不足：...
- 为什么这个问题重要：...

## 三、一句话总结
用一到两句话概括论文最核心的内容。

## 四、核心创新点
列出 2-5 条核心创新点，每条说明：创新点是什么、解决了什么问题、为什么更好。

## 五、方法详解
描述论文提出的方法，包括整体架构、关键模块、损失函数、训练和推理流程。

## 六、实验设置
- 数据集（全称）：ImageNet、COCO 等
- 数据集规模
- Baseline 方法（全称）
- 评估指标

## 七、实验结果
给出具体数值结果和与 Baseline 的对比。

## 八、局限性
说明方法的适用场景限制、计算复杂度、数据和资源要求等。

## 九、未来研究方向
基于局限性提出 2-3 个有价值的未来研究方向。

## 十、对工程/研究的启发
从工程实践和学术研究两个角度说明启发。

## 十一、适合标签
从以下 22 个固定类别中挑选最相关的 3-5 个，用英文逗号分隔，严格只选这些类别，不要自创标签：
Depth Estimation, Image Classification, Object Detection, Image Segmentation, Text-to-Image, Image-to-Text, Image-to-Image, Image-to-Video, Unconditional Image Generation, Video Classification, Text-to-Video, Zero-Shot Image Classification, Mask Generation, Zero-Shot Object Detection, Text-to-3D, Image-to-3D, Image Feature Extraction, Keypoint Detection, Video-to-Video, Image Generation, Pose Estimation, 3D Reconstruction

## 十二、作者机构
请从论文正文第一页提取所有作者的机构信息，格式为：作者名 - 机构名，多个作者用换行分隔。如果无法确定某作者的机构，请注明"未明确"。

---
论文标题：{title}

论文作者：{authors or '(未提供)'}

论文摘要：
{abstract}

论文正文（部分）：
{text if text else '（正文未提供，仅基于摘要总结）'}
"""

    try:
        summary = chat(
            prompt=user_prompt,
            model=model,
            system=system_prompt,
            temperature=0.2,
            max_tokens=8192,
        )
        # 清理 prompt 残留文字
        summary = clean_summary(summary)
        logger.info(f"总结生成成功: {title[:50]}...")
        return summary

    except Exception as e:
        logger.error(f"总结生成失败: {title[:50]} - {e}")
        raise RuntimeError(f"总结生成失败: {e}") from e


def summarize_batch(
    papers: list[dict],
    model: str = "deepseek-v4-flash",
    max_chars: int = 20000,
) -> list[dict]:
    """
    批量总结论文（串行，逐篇调用 LLM）

    Returns:
        更新后的论文列表（每条包含 summary 字段）
    """
    results = []
    for i, paper in enumerate(papers, 1):
        logger.info(f"正在总结第 {i}/{len(papers)} 篇: {paper['title'][:60]}")
        summary = summarize_paper(
            title=paper["title"],
            abstract=paper["abstract"],
            authors=paper.get("authors", ""),
            full_text=paper.get("full_text", ""),
            model=model,
            max_chars=max_chars,
        )
        paper["summary"] = summary
        results.append(paper)
    return results


def infer_tags_from_summary(
    summary: str,
    model: str = "deepseek-v4-flash",
    allowed_tags: list[str] | None = None,
) -> str:
    """
    从总结中提取标签

    Args:
        summary: 论文总结文本
        model: LLM 模型
        allowed_tags: 允许的标签列表（规范化）。为 None 时使用内置 HuggingFace 标签。

    Returns:
        逗号分隔的标签字符串
    """
    tag_list = allowed_tags or [
        "Depth Estimation", "Image Classification", "Object Detection", "Image Segmentation",
        "Text-to-Image", "Image-to-Text", "Image-to-Image", "Image-to-Video",
        "Unconditional Image Generation", "Video Classification", "Text-to-Video",
        "Zero-Shot Image Classification", "Mask Generation", "Zero-Shot Object Detection",
        "Text-to-3D", "Image-to-3D", "Image Feature Extraction", "Keypoint Detection",
        "Video-to-Video", "Image Generation", "Pose Estimation", "3D Reconstruction",
    ]
    try:
        tags = chat(
            prompt=(
                "从以下论文总结中挑选最相关的 3-5 个标签，严格只能从以下列表中选择，不要自创：\n"
                + ", ".join(tag_list) + "\n\n"
                "只输出标签列表，用英文逗号分隔，必须使用列表中的精确字符串（包括大小写和标点），不要自创也不要修改。\n\n"
                + summary
            ),
            model=model,
            system="你是一个标签提取助手，只从给定列表中选择，不要自创。",
            temperature=0.1,
            max_tokens=256,
        )
        # 清理输出并过滤：只保留在 allowed_tags 中的标签
        raw_tags = tags.strip()
        raw_tags = raw_tags.replace("-", " ").replace("*", " ").replace("·", " ").strip()
        raw_tags = raw_tags.lstrip(":,，。")

        parsed = [t.strip() for t in raw_tags.split(",") if t.strip()]
        if allowed_tags:
            allowed_lower = {t.lower(): t for t in allowed_tags}
            filtered = []
            for t in parsed:
                if t in allowed_tags:
                    filtered.append(t)
                elif t.lower() in allowed_lower:
                    filtered.append(allowed_lower[t.lower()])
                else:
                    logger.debug(f"标签 '{t}' 不在允许列表中，已丢弃")
            parsed = filtered[:5]
            result = ", ".join(parsed)
            # 第二层防护：用 tag_utils.normalize_tags_str 做模糊+人工映射
            result = normalize_tags_str(result, allowed_tags)
            return result
    except Exception as e:
        logger.error(f"标签提取失败: {e}")
        return ""


def extract_affiliations_from_summary(summary: str) -> str:
    """
    从论文总结中提取作者机构信息。

    优先级：
    1. 一、论文基本信息 中的 所属机构：
    2. ## 十二、作者机构 / ## 作者机构 等章节
    3. 作者列表行中的括号机构（University, Institute 等关键词）
    4. affiliations 行中包含学校/研究机构名的行
    """
    if not summary:
        return ""

    import re as _re
    lines = summary.split('\n')

    # Strategy 1: 所属机构 in section 一、论文基本信息
    in_section_1 = False
    for line in lines:
        s = line.strip()
        if _re.search(r'^##\s*一[.、]', s):
            in_section_1 = True
            continue
        if in_section_1 and _re.match(r'^##\s*[零一二三四五六七八九十\d]+[.、]', s):
            in_section_1 = False
            break
        # 匹配 所属机构：xxx 或 机构：xxx 等变体
        if in_section_1:
            for kw in ['所属机构', '作者机构', '机构：', '机构:', 'Affiliations', 'Institute']:
                if kw in s:
                    # 跳过纯提示词行
                    if _re.match(r'^[-*]?\s*[\u4e00-\u9fa5（()（）]+[：:]\s*$', s.strip()):
                        continue
                    # 跳过明显是"未明确"等无意义内容
                    val_part = s.split('：', 1)[-1].split(':', 1)[-1].strip()
                    if val_part and len(val_part) > 2 and val_part not in ['未明确', '无', '暂无', '未知', 'None', 'null', '-']:
                        val = val_part
                        val = _re.sub(r'\[.*?\]', '', val).strip()
                        val = val.rstrip('.,;: \n')
                        if len(val) > 3:
                            return val
                    break

    # Strategy 2: dedicated affiliations section (## 十二、... or similar)
    capture = False
    parts = []
    skip_phrases = ['发表时间', 'arXiv', '开源代码', '开源许可证', '作者列表', '标题：', 'doi', '## ', '---', '作者：']
    for line in lines:
        s = line.strip()
        if not s:
            continue
        # Match any section header about affiliations/institutions
        if s.startswith('##') and any(kw in s for kw in ['机构', 'Affiliations', 'Institution', 'Author']):
            capture = True
            continue
        if capture and s.startswith('## '):
            capture = False
            break
        if capture and s:
            # Skip lines that are mostly prompt leftovers or "未明确"
            if s in ['未明确', '无', '暂无', '未知', '-', '*', '—']:
                continue
            if any(p in s for p in skip_phrases):
                continue
            # Clean and check if it looks like an institution name
            clean = _re.sub(r'^[-*•→→]\s*', '', s)
            clean = clean.strip()
            if clean and len(clean) > 4 and not clean.startswith('#'):
                # Must contain institution keywords or look like a name-affiliation pair
                has_institution_keyword = any(k in clean for k in [
                    'University', 'Institute', 'School', 'College', 'Lab', 'Center', 'Centre',
                    'Hospital', 'Research', 'Inc', 'Corp', 'Ltd', 'Tech', 'Science',
                    'Academy', 'Department', 'Dept', 'Group', 'Program', 'Company',
                    '大学', '学院', '研究所', '医院', '实验室', '研究', '公司', '研究院'
                ])
                if has_institution_keyword:
                    parts.append(clean)
    if parts:
        result = ' '.join(parts)
        result = _re.sub(r'(arXiv|arxiv|\d{4}[-/]\d{2}[-/]\d{2}|发表时间).*', '', result).strip()
        return result[:300]  # 防止过长

    # Strategy 3: author list parentheses (from affiliations section or 一、基本信息)
    for line in lines:
        s = line.strip()
        # Look for lines with author names and institution keywords
        if any(k in s for k in ['University', 'Institute', '大学', '学院', 'Lab', 'Research']):
            institutions = _re.findall(r'\(([^)]+)\)', s)
            filtered = []
            for inst in institutions:
                inst = inst.strip()
                if any(k in inst for k in [
                    'University', 'Institute', 'School', 'College', 'Lab', 'Center', 'Centre',
                    'Hospital', 'Research', 'Inc', 'Corp', 'Ltd', 'Technolog', 'Science',
                    'Academy', '大学', '学院', '研究所', '医院', '实验室', '研究', '公司'
                ]):
                    filtered.append(inst)
            if filtered:
                return ', '.join(filtered[:3])  # 最多3个机构

    return ""
