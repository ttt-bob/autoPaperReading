#!/usr/bin/env python3
"""
Regenerate docs/gui-taxonomy.html taxonomy data from docs/papers.json.

Existing GUI taxonomy assignments are treated as manual overrides. New papers
whose tags explicitly contain "gui" are assigned by deterministic keyword rules.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"
PAPERS_JSON = DOCS_DIR / "papers.json"
GUI_HTML = DOCS_DIR / "gui-taxonomy.html"

STAGES = [
    {
        "code": "survey_taxonomy",
        "title": "00 综述 / 路线图",
        "question": "领域综述、技术路线、架构拆解、未来挑战",
        "artifact": "Survey / Roadmap",
    },
    {
        "code": "data_benchmark_eval",
        "title": "01 数据 / 基准 / 评测",
        "question": "数据从哪里来，测试集怎么定义，评价指标是什么",
        "artifact": "Dataset / Benchmark / Metrics",
    },
    {
        "code": "observation_representation",
        "title": "02 输入表示 / 屏幕表征",
        "question": "把屏幕、网页、系统状态表示成什么输入",
        "artifact": "Screenshot / DOM / A11y / OCR / SoM",
    },
    {
        "code": "screen_perception_parsing",
        "title": "03 屏幕感知 / 解析",
        "question": "屏幕里有哪些块、文本、图标、控件、区域",
        "artifact": "Element list / Layout blocks / Screen parse",
    },
    {
        "code": "ui_semantic_understanding",
        "title": "04 UI 语义理解",
        "question": "这些块、按钮、区域分别代表什么功能和含义",
        "artifact": "Caption / Role / Function / VQA",
    },
    {
        "code": "grounding_localization",
        "title": "05 定位 / Grounding",
        "question": "给定指令或目标，应该定位到哪个元素、坐标或区域",
        "artifact": "Point / BBox / Element ID / Region crop",
    },
    {
        "code": "action_control_execution",
        "title": "06 动作 / 控制 / 执行",
        "question": "如何把意图变成鼠标、键盘、API、脚本或下一步动作",
        "artifact": "Action JSON / PyAutoGUI / Selenium / ADB / API",
    },
    {
        "code": "planning_memory_exploration",
        "title": "07 规划 / 记忆 / 探索",
        "question": "如何拆任务、探索界面、记忆状态、恢复错误",
        "artifact": "Planner / Memory / Reflection / Skill",
    },
    {
        "code": "training_rl_adaptation",
        "title": "08 训练 / RL / 适配",
        "question": "模型怎么训练、微调、强化学习、测试时优化",
        "artifact": "SFT / RL / RFT / Data synthesis / Test-time scaling",
    },
    {
        "code": "verification_safety",
        "title": "09 验证 / 安全 / 可信",
        "question": "如何判断真的完成、避免误操作、处理隐私和安全",
        "artifact": "Verifier / Success checker / Guardrail",
    },
    {
        "code": "systems_deployment_tools",
        "title": "10 系统 / 工具 / 部署",
        "question": "工程系统、工具链、框架和部署形态是什么",
        "artifact": "Framework / Runtime / Tool / Deployment",
    },
]

MODEL_GROUPS = [
    {
        "code": "screen_parser",
        "title": "屏幕表示、解析与 OCR",
        "desc": "从 screenshot/DOM/OCR/SoM 得到元素、文本、布局块，是“看见屏幕”的基础。",
    },
    {
        "code": "semantic_vlm",
        "title": "UI 语义理解 / VLM 基座",
        "desc": "理解按钮、图标、区域功能和界面语义，常见形式是 UI VLM、caption、VQA。",
    },
    {
        "code": "grounding",
        "title": "定位 / Grounding",
        "desc": "把自然语言目标映射到点、框、元素 ID 或局部 crop，是 GUI agent 的执行接口。",
    },
    {
        "code": "action_vla",
        "title": "动作模型 / 控制执行",
        "desc": "输出 click/type/drag/API/PyAutoGUI/Selenium/ADB，或端到端 vision-language-action。",
    },
    {
        "code": "planning_memory",
        "title": "规划、记忆与反思",
        "desc": "处理长程任务、工作流、经验库、反思、错误恢复和多 agent 协同。",
    },
    {
        "code": "training_rl",
        "title": "训练、RL 与测试时优化",
        "desc": "SFT、RL/RFT、奖励模型、测试时缩放、数据合成、蒸馏。",
    },
    {
        "code": "verification_safety",
        "title": "验证、安全与可靠性",
        "desc": "任务成功检查、停止/恢复、攻击、防护、隐私和可信评测。",
    },
    {
        "code": "tools_systems",
        "title": "工具增强、系统与部署",
        "desc": "把模型接成可用 agent 框架、运行时、工具编排或端侧部署。",
    },
]

STAGE_KEYWORDS = {
    "survey_taxonomy": [
        "survey",
        "review",
        "taxonomy",
        "roadmap",
        "foundation models",
    ],
    "data_benchmark_eval": [
        "benchmark",
        "bench",
        "dataset",
        "evaluation",
        "evaluating",
        "metric",
        "testbed",
        "uncertainty quantification",
    ],
    "observation_representation": [
        "observation",
        "representation",
        "state",
        "accessibility",
        "a11y",
        "dom",
        "html",
        "screenshot",
        "set-of-mark",
        "som",
        "ui tree",
    ],
    "screen_perception_parsing": [
        "parse",
        "parsing",
        "layout",
        "ocr",
        "document",
        "region",
        "block",
        "segmentation",
        "reading order",
        "screen perception",
    ],
    "ui_semantic_understanding": [
        "understanding",
        "semantic",
        "caption",
        "vqa",
        "summarization",
        "screen2words",
        "icon",
        "role",
        "meaning",
    ],
    "grounding_localization": [
        "grounding",
        "localization",
        "locating",
        "coordinate",
        "bbox",
        "bounding box",
        "point",
        "target",
        "screenspot",
    ],
    "action_control_execution": [
        "action",
        "control",
        "execute",
        "execution",
        "automation",
        "click",
        "type",
        "drag",
        "trajectory",
        "computer use",
        "browser use",
    ],
    "planning_memory_exploration": [
        "planning",
        "planner",
        "memory",
        "reflection",
        "exploration",
        "workflow",
        "long-horizon",
        "tutorial",
        "demonstration",
    ],
    "training_rl_adaptation": [
        "training",
        "train",
        "reinforcement",
        "rl",
        "reward",
        "fine-tun",
        "sft",
        "distill",
        "post-training",
        "pretraining",
        "adaptation",
    ],
    "verification_safety": [
        "verification",
        "verifier",
        "safety",
        "security",
        "privacy",
        "trust",
        "guard",
        "audit",
        "risk",
        "robustness",
        "robust",
        "attack",
        "attacks",
        "adversarial",
        "injection",
    ],
    "systems_deployment_tools": [
        "framework",
        "system",
        "tool",
        "deployment",
        "runtime",
        "orchestration",
        "mcp",
        "infrastructure",
    ],
}

MODEL_KEYWORDS = {
    "screen_parser": [
        "ocr",
        "document",
        "parse",
        "parsing",
        "layout",
        "screen parser",
        "segmentation",
        "ui tree",
        "dom",
        "screenshot",
    ],
    "semantic_vlm": [
        "vlm",
        "mllm",
        "multimodal",
        "understanding",
        "semantic",
        "caption",
        "vqa",
        "vision-language",
    ],
    "grounding": [
        "grounding",
        "localization",
        "coordinate",
        "bbox",
        "bounding box",
        "point",
        "target",
        "screenspot",
    ],
    "action_vla": [
        "action",
        "control",
        "automation",
        "execute",
        "click",
        "type",
        "drag",
        "computer use",
        "browser use",
    ],
    "planning_memory": [
        "planning",
        "planner",
        "memory",
        "reflection",
        "workflow",
        "exploration",
        "long-horizon",
        "tutorial",
    ],
    "training_rl": [
        "training",
        "reinforcement",
        "rl",
        "reward",
        "distill",
        "fine-tun",
        "post-training",
        "sft",
        "pretraining",
    ],
    "verification_safety": [
        "safety",
        "security",
        "privacy",
        "verification",
        "verifier",
        "uncertainty",
        "trust",
        "audit",
        "guard",
        "robustness",
        "robust",
        "attack",
        "attacks",
        "adversarial",
        "injection",
    ],
    "tools_systems": [
        "framework",
        "system",
        "tool",
        "deployment",
        "runtime",
        "mcp",
        "orchestration",
    ],
}

FOCUS_KEYWORDS = [
    ("Mobile / Android", ["android", "mobile", "phone", "smartphone", "app"]),
    ("Web / Browser", ["web", "browser", "website", "html", "dom", "webpage"]),
    (
        "Element grounding",
        ["grounding", "coordinate", "bbox", "bounding box", "point", "target", "locat", "element"],
    ),
    (
        "PC / Desktop",
        ["desktop", "computer use", "computer-use", "operating system", "ubuntu", "windows", "macos"],
    ),
    ("RL / Feedback", ["reinforcement", "rl", "reward", "feedback", "preference", "post-training"]),
    ("Layout / Blocks", ["layout", "document", "block", "region", "parse", "parsing", "reading order"]),
    ("Human demos", ["demo", "demonstration", "trajectory", "human", "workflow", "tutorial"]),
    ("OCR / Text-rich", ["ocr", "text", "document", "reading", "table", "chart"]),
    ("Action schema", ["click", "type", "drag", "action", "execution", "coordinate-free"]),
    ("High-resolution", ["high-resolution", "high resolution", "dense", "zoom", "large screenshot"]),
    (
        "Safety / Privacy",
        [
            "safety",
            "privacy",
            "security",
            "trust",
            "guard",
            "audit",
            "risk",
            "robustness",
            "robust",
            "attack",
            "attacks",
            "adversarial",
            "injection",
        ],
    ),
    ("Cross-platform", ["cross-platform", "multi-platform", "hybrid interface", "computer, phone, browser"]),
]

PAPER_OVERRIDES = {
    "2502.13053v3": {
        "stage": "verification_safety",
        "stageTags": [
            "verification_safety",
            "data_benchmark_eval",
            "action_control_execution",
            "observation_representation",
            "training_rl_adaptation",
            "systems_deployment_tools",
        ],
        "modelGroup": "verification_safety",
        "focus": [
            "Safety / Privacy",
            "Mobile / Android",
            "Element grounding",
            "PC / Desktop",
            "RL / Feedback",
            "OCR / Text-rich",
            "Action schema",
        ],
    },
}


def normalize_title(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().lower()


def tags_contain_gui(tags: str) -> bool:
    return any(tag.strip().lower() == "gui" for tag in (tags or "").split(","))


def compact_text(value: str, limit: int = 360) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    return text[:limit]


def paper_text(paper: dict[str, Any]) -> str:
    return " ".join(
        str(paper.get(key) or "")
        for key in ("title", "abstract", "summary", "tags", "affiliations")
    ).lower()


def score_keywords(text: str, rules: dict[str, list[str]]) -> Counter[str]:
    scores: Counter[str] = Counter()
    for code, keywords in rules.items():
        for keyword in keywords:
            if keyword in text:
                scores[code] += 1
    return scores


def infer_stage(text: str) -> tuple[str, list[str]]:
    scores = score_keywords(text, STAGE_KEYWORDS)
    tags = [code for code, _ in scores.most_common() if scores[code] > 0]
    if not tags:
        return "other", ["other"]
    return tags[0], tags


def infer_model_group(text: str) -> str:
    scores = score_keywords(text, MODEL_KEYWORDS)
    if not scores:
        return ""
    return scores.most_common(1)[0][0]


def infer_focus(text: str) -> list[str]:
    focus = []
    for label, keywords in FOCUS_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            focus.append(label)
    return focus


def load_existing_taxonomy() -> dict[str, Any]:
    if not GUI_HTML.exists():
        return {}
    html = GUI_HTML.read_text(encoding="utf-8")
    match = re.search(
        r'<script id="taxonomy-data" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not match:
        return {}
    return json.loads(match.group(1))


def build_existing_indexes(existing: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    by_id = {}
    by_title = {}
    for paper in existing.get("papers", []):
        by_id[paper.get("id")] = paper
        by_title[normalize_title(paper.get("title", ""))] = paper
    return by_id, by_title


def existing_assignment(
    paper: dict[str, Any], by_id: dict[str, Any], by_title: dict[str, Any]
) -> dict[str, Any]:
    return by_id.get(paper.get("paper_id")) or by_title.get(normalize_title(paper.get("title", ""))) or {}


def classify_paper(
    paper: dict[str, Any], by_id: dict[str, Any], by_title: dict[str, Any]
) -> dict[str, Any]:
    existing = existing_assignment(paper, by_id, by_title)
    text = paper_text(paper)
    inferred_stage, inferred_stage_tags = infer_stage(text)
    inferred_model_group = infer_model_group(text)
    override = PAPER_OVERRIDES.get(str(paper.get("paper_id") or ""))
    stage = (override or {}).get("stage") or existing.get("stage") or inferred_stage
    stage_tags = (override or {}).get("stageTags") or existing.get("stageTags") or inferred_stage_tags
    model_group = (override or {}).get("modelGroup") or existing.get("modelGroup") or inferred_model_group
    focus = (override or {}).get("focus") or existing.get("focus") or infer_focus(text)
    stage_titles = {stage["code"]: stage["title"] for stage in STAGES}
    model_titles = {group["code"]: group["title"] for group in MODEL_GROUPS}

    published = paper.get("published") or ""
    date = published[:10] if published else existing.get("date", "")
    return {
        "id": paper.get("paper_id"),
        "title": paper.get("title") or existing.get("title") or "",
        "date": date,
        "year": date[:4] if date else "",
        "url": paper.get("entry_url") or existing.get("url") or "",
        "pdf": paper.get("pdf_url") or existing.get("pdf") or "",
        "stage": stage,
        "stageTitle": stage_titles.get(stage, existing.get("stageTitle") or "其他 GUI 相关"),
        "stageTags": stage_tags,
        "focus": focus,
        "modelGroup": model_group,
        "modelGroupTitle": model_titles.get(model_group, existing.get("modelGroupTitle") or ""),
        "summary": compact_text(paper.get("summary") or existing.get("summary") or ""),
    }


def build_taxonomy() -> dict[str, Any]:
    payload = json.loads(PAPERS_JSON.read_text(encoding="utf-8"))
    papers = payload.get("papers", payload if isinstance(payload, list) else [])
    existing = load_existing_taxonomy()
    by_id, by_title = build_existing_indexes(existing)

    gui_papers = [paper for paper in papers if tags_contain_gui(paper.get("tags", ""))]
    taxonomy_papers = [classify_paper(paper, by_id, by_title) for paper in gui_papers]
    taxonomy_papers.sort(key=lambda paper: (paper.get("date") or "", paper.get("title") or ""))

    stage_counts = Counter(paper.get("stage") for paper in taxonomy_papers)
    model_counts = Counter(paper.get("modelGroup") for paper in taxonomy_papers)
    focus_counts = Counter(
        focus for paper in taxonomy_papers for focus in paper.get("focus", [])
    )
    dates = [paper["date"] for paper in taxonomy_papers if paper.get("date")]

    return {
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "count": len(taxonomy_papers),
        "oldest": min(dates) if dates else "",
        "newest": max(dates) if dates else "",
        "stages": [
            {
                **stage,
                "count": stage_counts.get(stage["code"], 0),
            }
            for stage in STAGES
        ],
        "modelGroups": [
            {
                **group,
                "count": model_counts.get(group["code"], 0),
            }
            for group in MODEL_GROUPS
        ],
        "focusCounts": [[label, count] for label, count in focus_counts.most_common()],
        "papers": taxonomy_papers,
    }


def write_taxonomy(data: dict[str, Any]) -> None:
    existing = load_existing_taxonomy()
    existing_content = {key: value for key, value in existing.items() if key != "generatedAt"}
    new_content = {key: value for key, value in data.items() if key != "generatedAt"}
    if existing_content == new_content:
        print(f"GUI taxonomy already up to date: {data['count']} papers")
        return

    html = GUI_HTML.read_text(encoding="utf-8")
    json_text = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    updated = re.sub(
        r'(<script id="taxonomy-data" type="application/json">)(.*?)(</script>)',
        rf"\g<1>{json_text}\g<3>",
        html,
        count=1,
        flags=re.DOTALL,
    )
    if updated == html:
        print("GUI taxonomy already up to date")
        return
    GUI_HTML.write_text(updated, encoding="utf-8")
    print(f"✅ GUI taxonomy updated: {data['count']} papers")


def main() -> None:
    write_taxonomy(build_taxonomy())


if __name__ == "__main__":
    main()
