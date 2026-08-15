"""生成 docs/video-search.html —— 视频搜索论文专题页。

从 data/papers.db 中按手工策展列表挑选与"视频搜索 / 时序定位 / 异常行为检测 /
文本行人搜索"相关的论文，复用 docs/gui-taxonomy.html 的样式与交互逻辑，
生成独立的专题页面。

用法: uv run python jobs/build_video_search_page.py
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "papers.db"
GUI_TEMPLATE = ROOT / "docs" / "gui-taxonomy.html"
OUTPUT = ROOT / "docs" / "video-search.html"
DETAILS_DIR = ROOT / "docs" / "paper-data" / "details"

SUMMARY_LIMIT = 360
CANDIDATES_FILE = ROOT / "data" / "search_candidates.json"
JS_FILE = ROOT / "jobs" / "video_search_page.js"


def detail_filename(paper_id: str) -> str:
    """Return a safe, stable filename for a public paper-detail record."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", paper_id) + ".json"


def extract_code_url_from_summary(summary: str) -> str:
    """从总结文本中提取 GitHub / 项目主页 URL（与 export_papers 同款逻辑）。"""
    if not summary:
        return ""
    patterns = [
        r"https?://github\.com/[a-zA-Z0-9_\-]+/[a-zA-Z0-9_\-.]+?",
        r"https?://[a-zA-Z0-9_\-]+\.github\.io/[a-zA-Z0-9_\-/.]+",
    ]
    for pattern in patterns:
        match = re.search(pattern, summary)
        if match:
            return match.group(0).rstrip(".,;)")
    return ""


def find_local_pdf_path(paper_id: str) -> str:
    """在 data/pdfs 下按论文 ID 查找本地 PDF。"""
    safe_id = paper_id.replace("/", "_")
    matches = sorted((ROOT / "data" / "pdfs").glob(f"*/{safe_id}.pdf"))
    if matches:
        return matches[0].relative_to(ROOT).as_posix()
    return ""


def clean_affiliations(value: str) -> str:
    """清理机构字段：去掉序号前缀、arXiv/发表时间等杂质（与 export_papers 同款）。"""
    if not value:
        return ""
    text = re.sub(r"(arXiv|arxiv|\d{4}[-/]\d{2}[-/]\d{2}|发表时间).*", "", value).strip()
    text = re.sub(r"(?m)^\s*\d+[.、]\s*", "", text).strip()
    return text

# 批量抓取的 category_hint -> 页面流程层 / 模型专题 映射
CATEGORY_STAGE_MAP = {
    "video retrieval": ("retrieval_person_search", "retrieval_embedding"),
    "video moment retrieval": ("temporal_grounding", "video_llm"),
    "video question answering": ("video_llm_reasoning", "video_llm"),
    "long video understanding": ("video_llm_reasoning", "video_llm"),
    "video anomaly detection": ("anomaly_detection", "anomaly_security"),
    "temporal action detection": ("human_action_pose", "pose_motion"),
    "video captioning": ("video_llm_reasoning", "video_llm"),
    "video grounding": ("temporal_grounding", "video_llm"),
    "person search": ("retrieval_person_search", "retrieval_embedding"),
    "pedestrian retrieval": ("retrieval_person_search", "retrieval_embedding"),
    "image retrieval": ("retrieval_person_search", "retrieval_embedding"),
    "cross-modal retrieval": ("retrieval_person_search", "retrieval_embedding"),
    "visual grounding": ("retrieval_person_search", "retrieval_embedding"),
    "vision-language embedding": ("retrieval_person_search", "retrieval_embedding"),
    "fall detection": ("anomaly_detection", "anomaly_security"),
    "video indexing": ("retrieval_person_search", "retrieval_embedding"),
}

# category_hint -> 焦点标签
CATEGORY_FOCUS = {
    "video retrieval": ["视频检索"],
    "video moment retrieval": ["时序定位", "时刻检索"],
    "video question answering": ["视频问答"],
    "long video understanding": ["长视频理解"],
    "video anomaly detection": ["视频异常检测"],
    "temporal action detection": ["动作识别"],
    "video captioning": ["视频描述"],
    "video grounding": ["视频接地"],
    "person search": ["行人搜索"],
    "pedestrian retrieval": ["行人检索"],
    "image retrieval": ["图像检索"],
    "cross-modal retrieval": ["跨模态检索"],
    "visual grounding": ["视觉接地"],
    "vision-language embedding": ["多模态嵌入"],
    "fall detection": ["异常检测", "安防"],
    "video indexing": ["视频索引"],
}

# 批量搜索会命中一些“检索/RAG/多模态”但并非视频检索的论文。它们仍保留在
# data/papers.db，便于以后复用；专题页只展示真正能帮助“以自然语言找视频帧/片段”
# 的候选，避免文档 RAG、法律检索、材料检索等内容稀释结果。
AUTO_EXCLUDE_TITLE_TERMS = (
    "private document",
    "long-term conversational memory",
    "personalized question answering",
    "personalized retrieval",
    "composed image retrieval",
    "composed image",
    "forensic image retrieval",
    "materials characterization",
    "scientific formula",
    "scientific document",
    "long document",
    "legal question answering",
    "repository-level issue",
    "sketch-based image retrieval",
    "chart understanding",
    "web intelligence",
    "knowledge-based visual question answering",
    "counter-commonsense",
    "multimodal rag",
    "neuro-symbolic rag",
    "retrieval-augmented generation",
)

VIDEO_OR_PERSON_TITLE_TERMS = (
    "video",
    "temporal",
    "moment",
    "action",
    "activity",
    "anomaly",
    "abnormal",
    "surveillance",
    "fall",
    "violence",
    "crime",
    "theft",
    "steal",
    "robbery",
    "burglary",
    "person",
    "pedestrian",
    "re-id",
    "reidentification",
    "human",
    "egocentric",
)


def is_video_search_candidate(title: str, category_hint: str) -> bool:
    """Keep auto-discovered papers that are useful for video/frame search."""
    title_lower = (title or "").lower()
    if any(term in title_lower for term in AUTO_EXCLUDE_TITLE_TERMS):
        return False
    if any(term in title_lower for term in VIDEO_OR_PERSON_TITLE_TERMS):
        return True
    # Keep generic video-search categories only when their title is explicitly
    # video-oriented. Generic image/CIR/document retrieval is intentionally out.
    return category_hint in {
        "video retrieval",
        "video moment retrieval",
        "video question answering",
        "long video understanding",
        "video anomaly detection",
        "temporal action detection",
        "video captioning",
        "video grounding",
        "video indexing",
    } and "video" in title_lower


# 页面内的“相关性优先”分数：手工策展论文另加 curated bonus，自动候选不会压过
# 已核验的核心论文；同分时前端再按日期倒序展示最新工作。
RELEVANCE_TERMS = (
    ("video moment retrieval", 30),
    ("temporal grounding", 30),
    ("video temporal grounding", 30),
    ("text-video retrieval", 28),
    ("video-text retrieval", 28),
    ("video retrieval", 26),
    ("video search", 24),
    ("natural language video", 24),
    ("video localization", 24),
    ("person search", 23),
    ("person retrieval", 23),
    ("pedestrian retrieval", 23),
    ("video anomaly", 23),
    ("anomaly detection", 20),
    ("fall detection", 24),
    ("surveillance", 18),
    ("action localization", 18),
    ("temporal action", 17),
    ("long video", 16),
    ("video-language", 14),
    ("video language", 14),
    ("video", 4),
)


def relevance_score(title: str, abstract: str = "") -> int:
    text = f"{title or ''} {abstract or ''}".lower()
    return sum(weight for term, weight in RELEVANCE_TERMS if term in text)

# ---------------------------------------------------------------------------
# 手工策展: paper_id -> (stage, modelGroup, focus[])
# 从 949 篇中挑出与"视频搜索 / 事件定位 / 行为异常检测 / 行人搜索"相关的论文
# ---------------------------------------------------------------------------
STAGES = [
    {
        "code": "data_benchmark_eval",
        "title": "01 数据 / 基准 / 评测",
        "question": "视频从哪来，测试集怎么定义，检索/异常/问答的指标是什么",
        "artifact": "Video dataset / Benchmark / Metrics",
    },
    {
        "code": "video_representation",
        "title": "02 视频表征 / 编码",
        "question": "如何把连续帧编码成可检索、可推理的时空表示",
        "artifact": "Token / Embedding / Dense map",
    },
    {
        "code": "retrieval_person_search",
        "title": "03 检索 / 行人 / 图像搜索",
        "question": "给定文本描述，如何找到对应的人、动作、图像或视频片段",
        "artifact": "Text-video match / Person Re-ID / Image retrieval",
    },
    {
        "code": "temporal_grounding",
        "title": "04 时序定位 / 事件定位",
        "question": "目标事件发生在视频的哪一段时间区间",
        "artifact": "Time segment / Moment / Evidence",
    },
    {
        "code": "human_action_pose",
        "title": "05 人体动作 / 姿态理解",
        "question": "如何理解人的姿态、动作与交互行为",
        "artifact": "Pose / Motion / Action label",
    },
    {
        "code": "anomaly_detection",
        "title": "06 异常检测 / 安防监控",
        "question": "摔倒、奔跑、偷盗、闯入等异常行为如何自动发现",
        "artifact": "Anomaly score / Alarm / Localization",
    },
    {
        "code": "video_llm_reasoning",
        "title": "07 视频问答 / 长视频推理",
        "question": "如何用大模型对长视频进行理解、问答与叙事",
        "artifact": "Video QA / Caption / Narrative",
    },
    {
        "code": "camera_edge_deploy",
        "title": "08 摄像头 / 边缘部署",
        "question": "如何在真实摄像头和边缘设备上实时运行",
        "artifact": "PTZ agent / Edge inference / Stream",
    },
]

MODEL_GROUPS = [
    {
        "code": "video_llm",
        "title": "视频-语言大模型",
        "desc": "以视频+文本为输入的多模态大模型，承担理解、问答、推理与叙事。",
    },
    {
        "code": "retrieval_embedding",
        "title": "检索 / 嵌入 / 行人搜索",
        "desc": "把文本与视频/行人映射到共同空间，实现以文搜人、以文搜片段。",
    },
    {
        "code": "detection_tracking",
        "title": "检测 / 跟踪 / 分割",
        "desc": "定位人、物体与其运动轨迹，输出框、掩膜与身份。",
    },
    {
        "code": "pose_motion",
        "title": "姿态 / 运动分析",
        "desc": "从姿态骨架与运动信号推断行为与生物力学属性。",
    },
    {
        "code": "anomaly_security",
        "title": "异常检测 / 安防",
        "desc": "识别摔倒、奔跑、偷盗等偏离常态的人体行为并告警。",
    },
    {
        "code": "agent_edge",
        "title": "智能体 / 边缘部署",
        "desc": "把检索与理解能力装进真实摄像头、边缘设备或推理引擎。",
    },
]

# (paper_id, stage, modelGroup, [focus...])
CURATED = [
    # ---- 01 数据 / 基准 / 评测 ----
    ("2607.08745v1", "data_benchmark_eval", "video_llm", ["行车记录仪", "事故理解", "VQA基准"]),
    ("2607.01117v1", "data_benchmark_eval", "video_llm", ["视频大模型", "运动幻觉", "评测基准"]),
    ("2606.14702v1", "data_benchmark_eval", "video_llm", ["音视频推理", "结构化脚本", "证据"]),
    ("2605.05945v1", "data_benchmark_eval", "video_llm", ["第一视角", "长时程数据", "开源基础设施"]),
    ("2605.21625v1", "data_benchmark_eval", "video_llm", ["时空理解", "VLM评测", "家具组装"]),
    # ---- 02 视频表征 / 编码 ----
    ("2607.21592v1", "video_representation", "detection_tracking", ["稠密预测", "分割", "深度"]),
    ("2605.30352v1", "video_representation", "detection_tracking", ["运动分割", "3D时空", "视频分割"]),
    ("2607.14088v1", "video_representation", "detection_tracking", ["表征自编码器", "视频基座模型"]),
    # ---- 03 检索 / 行人搜索 ----
    ("2608.09152v1", "retrieval_person_search", "retrieval_embedding", ["文本行人搜索", "异常行为", "动作反演"]),
    ("2605.06083v1", "retrieval_person_search", "retrieval_embedding", ["视频检索", "部分相关", "证据学习"]),
    ("2605.06637v1", "retrieval_person_search", "retrieval_embedding", ["行人重识别", "遮挡", "动态掩码"]),
    ("2605.05027v1", "retrieval_person_search", "retrieval_embedding", ["行人重识别", "终身学习", "提示蒸馏"]),
    ("2608.02598v1", "retrieval_person_search", "retrieval_embedding", ["行人重识别", "航拍-地面", "视角鲁棒"]),
    ("2608.06060v1", "retrieval_person_search", "retrieval_embedding", ["多模态检索", "失败学习", "推理"]),
    ("2606.12294v1", "retrieval_person_search", "retrieval_embedding", ["取证检索", "跨模态", "模态鸿沟"]),
    ("2607.28627v1", "retrieval_person_search", "retrieval_embedding", ["视觉检索", "单token", "VLM"]),
    # ---- 04 时序定位 / 事件定位 ----
    ("2607.11862v1", "temporal_grounding", "video_llm", ["视频问答", "证据片段", "时序定位"]),
    ("2607.28463v1", "temporal_grounding", "video_llm", ["长视频理解", "查询引导", "视觉采样"]),
    ("2605.05848v1", "temporal_grounding", "video_llm", ["长视频理解", "双路由", "查询自适应"]),
    ("2605.06185v1", "temporal_grounding", "video_llm", ["长视频推理", "事件因果", "RAG"]),
    ("2605.05640v1", "temporal_grounding", "video_llm", ["长视频", "模糊查询", "agentic"]),
    ("2607.11798v1", "temporal_grounding", "video_llm", ["音频描述", "叙事接地", "免训练"]),
    # ---- 05 人体动作 / 姿态理解 ----
    ("2605.22819v1", "human_action_pose", "pose_motion", ["姿态接地", "视频理解", "骨架"]),
    ("2605.05753v1", "human_action_pose", "pose_motion", ["运动分割", "人体行为", "时序切分"]),
    ("2607.08725v1", "human_action_pose", "pose_motion", ["姿态估计", "生物力学", "动作属性"]),
    ("2605.05390v1", "human_action_pose", "detection_tracking", ["多相机", "人员跟踪", "3D度量"]),
    # ---- 06 异常检测 / 安防监控 ----
    ("2608.05069v1", "anomaly_detection", "anomaly_security", ["视频异常检测", "人体行为", "向量量化表征"]),
    ("2607.18142v1", "anomaly_detection", "anomaly_security", ["视频异常检测", "物体中心", "跟踪推理"]),
    ("2607.01049v1", "anomaly_detection", "anomaly_security", ["工业异常", "语言接地", "VLM"]),
    ("2607.16181v1", "anomaly_detection", "anomaly_security", ["危险驾驶", "情绪反应", "VLA助手"]),
    ("2606.13625v1", "anomaly_detection", "anomaly_security", ["监控场景", "车辆颜色", "长尾"]),
    # ---- 07 视频问答 / 长视频推理 ----
    ("2607.14935v1", "video_llm_reasoning", "video_llm", ["视频MLLM", "全开源", "通用理解"]),
    ("2607.19339v1", "video_llm_reasoning", "video_llm", ["长音视频", "原生工具", "推理"]),
    ("2607.16107v1", "video_llm_reasoning", "video_llm", ["音视频大模型", "长视频", "开放智能"]),
    ("2607.12820v1", "video_llm_reasoning", "video_llm", ["视频描述", "音视频协同", "全模态"]),
    ("2607.28509v1", "video_llm_reasoning", "video_llm", ["视频描述", "多参考", "图像接地"]),
    # ---- 08 摄像头 / 边缘部署 ----
    ("2606.02951v1", "camera_edge_deploy", "agent_edge", ["自然语言相机", "PTZ", "边缘实时"]),
    ("2607.16154v1", "camera_edge_deploy", "agent_edge", ["路侧感知", "边缘部署", "相机-激光雷达"]),
    ("2606.23743v1", "camera_edge_deploy", "agent_edge", ["视频推理引擎", "全栈加速", "agent原生"]),
    # ---- 经典基础：文本-视频检索 / 时序定位 ----
    ("2104.00650v2", "retrieval_person_search", "retrieval_embedding", ["文本-视频检索", "联合嵌入", "WebVid"]),
    ("2104.08860v2", "retrieval_person_search", "retrieval_embedding", ["文本-视频检索", "CLIP", "视频片段"]),
    ("2207.07285v2", "retrieval_person_search", "retrieval_embedding", ["多粒度检索", "视频-文本", "关键帧"]),
    ("2109.08472v1", "video_representation", "retrieval_embedding", ["动作-文本", "零样本动作", "视频表征"]),
    ("2109.14084v2", "retrieval_person_search", "retrieval_embedding", ["零样本动作", "视频-文本", "动作定位"]),
    ("2212.03191v2", "video_representation", "retrieval_embedding", ["视频基座模型", "视频-语言", "动作理解"]),
    ("2403.15377v4", "video_representation", "retrieval_embedding", ["视频基座模型", "多模态视频", "长视频"]),
    ("1912.03590v3", "temporal_grounding", "retrieval_embedding", ["2D-TAN", "自然语言定位", "时序候选"]),
    ("2004.13931v2", "temporal_grounding", "retrieval_embedding", ["VSLNet", "自然语言定位", "长视频"]),
    ("2107.09609v2", "temporal_grounding", "retrieval_embedding", ["QVHighlights", "片段检索", "高光检测"]),
    ("2312.02051v2", "video_llm_reasoning", "video_llm", ["长视频", "时间感知", "时序定位"]),
    ("2407.15754v1", "data_benchmark_eval", "video_llm", ["长视频基准", "上下文检索", "指代推理"]),
    ("2406.18113v6", "temporal_grounding", "video_llm", ["Chrono", "时间表示", "时序定位"]),
    ("2410.03290v2", "temporal_grounding", "video_llm", ["细粒度定位", "时间 token", "Grounded-VideoLLM"]),
    ("2506.18883v2", "temporal_grounding", "video_llm", ["通用时序接地", "零样本", "长短视频"]),
    ("2501.02504v1", "temporal_grounding", "retrieval_embedding", ["关键词注意力", "片段检索", "高光检测"]),
    ("2507.12062v1", "temporal_grounding", "retrieval_embedding", ["运动-语义", "片段检索", "高光检测"]),
    ("2603.02363v1", "temporal_grounding", "retrieval_embedding", ["真实搜索词", "多片段检索", "查询泛化"]),
    # ---- 异常事件：摔倒 / 偷盗 / 抢劫 / 斗殴与空间局部性 ----
    ("1801.04264v3", "anomaly_detection", "anomaly_security", ["UCF-Crime", "偷盗", "抢劫", "斗殴"]),
    ("1901.10364v1", "anomaly_detection", "anomaly_security", ["异常局部性", "时空管道", "UCFCrime2Local"]),
    ("2310.02835v1", "anomaly_detection", "anomaly_security", ["AnomalyCLIP", "文本驱动", "异常分类"]),
    ("2308.11681v3", "anomaly_detection", "anomaly_security", ["VadCLIP", "弱监督", "细粒度异常"]),
    ("2412.01095v3", "anomaly_detection", "anomaly_security", ["VERA", "可解释异常", "视觉语言模型"]),
    # ---- 文本行人搜索：人物属性 / 部件级对齐 ----
    ("2306.02898v4", "retrieval_person_search", "retrieval_embedding", ["文本行人搜索", "多属性", "细粒度人物"]),
    ("2404.18106v1", "retrieval_person_search", "retrieval_embedding", ["文本行人搜索", "半监督", "伪文本"]),
    ("2412.20646v1", "retrieval_person_search", "retrieval_embedding", ["文本行人搜索", "视觉细节", "CLIP"]),
    ("2501.00318v1", "retrieval_person_search", "retrieval_embedding", ["文本行人搜索", "部件级对齐", "人物属性"]),
]


def fetch_paper(cur: sqlite3.Cursor, paper_id: str) -> dict | None:
    cur.execute(
        """SELECT paper_id, title, abstract, published, entry_url, pdf_url, summary, tags,
                  authors, affiliations
           FROM papers WHERE paper_id = ?""",
        (paper_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    (
        pid,
        title,
        abstract,
        published,
        entry_url,
        pdf_url,
        summary,
        tags,
        authors,
        affiliations,
    ) = row
    summary_full = (summary or "").strip()
    summary_show = summary_full
    if len(summary_show) > SUMMARY_LIMIT:
        summary_show = summary_show[:SUMMARY_LIMIT] + "…"
    code_url = extract_code_url_from_summary(summary_full)
    local_pdf_path = find_local_pdf_path(pid)
    return {
        "id": pid,
        "title": title,
        "date": (published or "")[:10],
        "year": (published or "")[:4],
        "url": entry_url,
        "pdf": pdf_url,
        "detailPath": f"paper-data/details/{detail_filename(pid)}",
        "summary": summary_show,
        "intro": summary_show[:220],
        "tagsText": tags or "",
        "authors": authors or "",
        "affiliations": clean_affiliations(affiliations or ""),
        "code_url": code_url,
        "local_pdf_path": local_pdf_path,
        # Keep the full record out of the inline page index. It is written to
        # paper-data/details and fetched only after a reader opens this paper.
        "_detail": {
            "paper_id": pid,
            "title": title or "",
            "authors": authors or "",
            "affiliations": clean_affiliations(affiliations or ""),
            "abstract": abstract or "",
            "published": published or "",
            "pdf_url": pdf_url or "",
            "entry_url": entry_url or "",
            "code_url": code_url,
            "summary": summary_full,
            "tags": tags or "",
            "local_pdf_path": local_pdf_path,
        },
    }


def build_data() -> dict:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    stage_counts = {s["code"]: 0 for s in STAGES}
    model_counts = {g["code"]: 0 for g in MODEL_GROUPS}
    focus_counts: dict[str, int] = {}
    papers = []
    dates = []
    seen_ids: set[str] = set()

    def add_paper(
        paper_id: str,
        stage: str,
        model_group: str,
        focus: list[str],
        curated: bool = False,
    ) -> None:
        if paper_id in seen_ids:
            return
        seen_ids.add(paper_id)
        rec = fetch_paper(cur, paper_id)
        if not rec:
            return
        rec["stage"] = stage
        rec["stageTitle"] = next(s["title"] for s in STAGES if s["code"] == stage)
        rec["stageTags"] = [stage]
        rec["focus"] = focus
        rec["modelGroup"] = model_group
        rec["modelGroupTitle"] = next(
            g["title"] for g in MODEL_GROUPS if g["code"] == model_group
        )
        rec["curated"] = curated
        rec["relevance"] = relevance_score(
            rec["title"], rec.get("_detail", {}).get("abstract", "")
        ) + (100 if curated else 0)
        papers.append(rec)
        stage_counts[stage] += 1
        model_counts[model_group] += 1
        for f in focus:
            focus_counts[f] = focus_counts.get(f, 0) + 1
        if rec["date"]:
            dates.append(rec["date"])

    # 1. 手工策展列表（保底）
    for paper_id, stage, model_group, focus in CURATED:
        add_paper(paper_id, stage, model_group, focus, curated=True)

    # 2. 批量抓取的候选（search_candidates.json，已有有效总结才收录）
    if CANDIDATES_FILE.exists():
        import json as _json

        candidates = _json.loads(CANDIDATES_FILE.read_text(encoding="utf-8"))
        for cand in candidates:
            pid = cand.get("paper_id", "")
            hint = cand.get("category_hint", "")
            mapping = CATEGORY_STAGE_MAP.get(hint)
            if not mapping:
                continue
            if not is_video_search_candidate(cand.get("title", ""), hint):
                continue
            # 没有有效总结的不收录
            row = cur.execute(
                "SELECT summary FROM papers WHERE paper_id = ?", (pid,)
            ).fetchone()
            if not row or not (row[0] or "").strip():
                continue
            stage, model_group = mapping
            focus = list(CATEGORY_FOCUS.get(hint, []))
            add_paper(pid, stage, model_group, focus)

    conn.close()

    stages = [dict(s, count=stage_counts[s["code"]]) for s in STAGES]
    model_groups = [
        dict(g, count=model_counts[g["code"]]) for g in MODEL_GROUPS
    ]
    papers.sort(key=lambda p: (-p.get("relevance", 0), p.get("date", "")), reverse=False)

    return {
        "generatedAt": date.today().isoformat(),
        "count": len(papers),
        "oldest": min(dates) if dates else "",
        "newest": max(dates) if dates else "",
        "stages": stages,
        "modelGroups": model_groups,
        "focusCounts": focus_counts,
        "papers": papers,
    }


def write_detail_files(data: dict) -> int:
    """Write the full summaries used by the page's on-demand modal."""
    DETAILS_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for paper in data["papers"]:
        detail = paper.get("_detail")
        if not detail:
            continue
        output = DETAILS_DIR / detail_filename(str(detail["paper_id"]))
        output.write_text(json.dumps(detail, ensure_ascii=False), encoding="utf-8")
        written += 1
    return written


def generate_html(data: dict) -> str:
    template = GUI_TEMPLATE.read_text(encoding="utf-8")

    def sub(old: str, new: str) -> None:
        nonlocal template
        assert old in template, f"模板中未找到: {old[:60]!r}"
        template = template.replace(old, new, 1)

    # 标题 / 页头
    sub("<title>GUI Agent Papers Landscape</title>",
        "<title>Video Search Papers Landscape</title>")
    sub("<h1>GUI Agent Papers Landscape</h1>",
        "<h1>Video Search Papers Landscape</h1>")

    # 页头统计：占位值直接用真实论文数，避免源码里出现 GUI 模板残留的 242
    sub('<div class="stat"><b id="stat-count">242</b><span>GUI papers</span></div>',
        f'<div class="stat"><b id="stat-count">{data["count"]}</b><span>video-search papers</span></div>')
    sub('<div class="stat"><b>11</b><span>pipeline layers</span></div>',
        '<div class="stat"><b>8</b><span>pipeline layers</span></div>')
    sub('<div class="stat"><b>8</b><span>model directions</span></div>',
        '<div class="stat"><b>6</b><span>model directions</span></div>')

    # 页头导航: 先移除模板中可能自带的指向 video-search 自身的链接（源模板
    # gui-taxonomy.html 已加入 Video Search 导航，需要避免新页面链接到自己），
    # 再插入指向 GUI 地图页的链接。
    template = re.sub(
        r'\n\s*<a class="header-action" href="video-search\.html">.*?Video Search\n\s*</a>',
        '',
        template,
        count=1,
        flags=re.S,
    )
    sub(
        """      <a class="header-action" href="index.html">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/>
        </svg>
        Daily CV Papers
      </a>""",
        """      <a class="header-action" href="index.html">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/>
        </svg>
        Daily CV Papers
      </a>
      <a class="header-action" href="gui-taxonomy.html">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
          <rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
        </svg>
        GUI 论文地图
      </a>""",
    )

    # 注入数据
    # Full summaries live in separate JSON files. Do not accidentally put the
    # private build-only `_detail` field back into the initial HTML payload.
    html_data = dict(data)
    html_data["papers"] = [
        {key: value for key, value in paper.items() if key != "_detail"}
        for paper in data["papers"]
    ]
    json_blob = json.dumps(html_data, ensure_ascii=False).replace("</", "<\\/")
    m = re.search(
        r'(<script id="taxonomy-data" type="application/json">).*?(</script>)',
        template,
        re.S,
    )
    assert m, "模板中未找到 taxonomy-data"
    template = template[: m.start(1)] + m.group(1) + json_blob + m.group(2) + template[m.end(2):]

    # 弹窗默认标签
    sub("p.stageTitle || 'GUI paper'", "p.stageTitle || 'video-search paper'")

    # 用新版按需加载 JS 整体替换模板脚本：不拉 papers.json，点开详情时
    # 才 fetch paper-data/details/*.json（与公网 GUI 页同款逻辑，避免 11MB 全量下载）
    js = JS_FILE.read_text(encoding="utf-8")
    template = re.sub(
        r'<script>.*?</script>',
        lambda m: f"<script>{js}</script>",
        template,
        count=1,
        flags=re.S,
    )

    # ---------- 正文静态区: 替换 GUI 专属内容为视频搜索专属 ----------

    # Section 0: 对齐框架
    sub(
        """    <h2>0. OS Agent Survey 对齐框架</h2>
    <div class=\"survey-panel\">
      <div class=\"survey-map\">
        <div class=\"survey-col components\">
          <h3>Key Components</h3>
          <div class=\"survey-stack\">
            <div class=\"survey-box\">
              <b>Environments</b>
              <p>Computer / Phone / Browser / Web / CLI / Sandbox，决定任务和可执行动作空间。</p>
            </div>
            <div class=\"survey-arrow\">↑</div>
            <div class=\"survey-box\">
              <b>Observations</b>
              <p>Screenshot、DOM/A11y、OCR、UI tree、OS state、HTML，形成可感知的状态。</p>
            </div>
            <div class=\"survey-arrow\">↑</div>
            <div class=\"survey-box\">
              <b>Actions</b>
              <p>Click、type、drag、hotkey、API、code、tool call，是模型对系统施加影响的接口。</p>
            </div>
          </div>
        </div>
        <div class=\"survey-center\">
          <div class=\"survey-agent\">OS<br>Agent</div>
          <div class=\"survey-platforms\">Cross-platform GUI / OS use</div>
        </div>
        <div class=\"survey-col capabilities\">
          <h3>Capabilities</h3>
          <div class=\"survey-stack\">
            <div class=\"survey-cap\">
              <b>Understanding</b>
              <p>识别屏幕结构、控件语义、文本/图标含义、状态变化和任务相关区域。</p>
            </div>
            <div class=\"survey-arrow\">↓</div>
            <div class=\"survey-cap\">
              <b>Planning</b>
              <p>把用户意图拆成可执行步骤，结合记忆、探索、反馈和约束进行长程决策。</p>
            </div>
            <div class=\"survey-arrow\">↓</div>
            <div class=\"survey-cap\">
              <b>Grounding / Execution</b>
              <p>把计划映射到元素、坐标、代码或工具调用，并用验证器判断是否完成。</p>
            </div>
          </div>
        </div>
      </div>
      <div class=\"survey-source\">
        <span class=\"small\">参考 OS Agent Survey 的组件/能力拆分，本页进一步展开为可点击的 11 个流程层和 8 个模型专题。</span>
        <a class=\"source-link\" href=\"https://os-agent-survey.github.io\" target=\"_blank\" rel=\"noreferrer\">打开 OS Agent Survey</a>
      </div>
    </div>
  </section>""",
        """    <h2>0. 视频搜索对齐框架</h2>
    <div class=\"survey-panel\">
      <div class=\"survey-map\">
        <div class=\"survey-col components\">
          <h3>Inputs</h3>
          <div class=\"survey-stack\">
            <div class=\"survey-box\">
              <b>Video Sources</b>
              <p>监控摄像头、行车记录仪、第一视角、长视频库，原始素材来自哪里。</p>
            </div>
            <div class=\"survey-arrow\">↑</div>
            <div class=\"survey-box\">
              <b>Text Queries</b>
              <p>自然语言描述：出现的人、摔倒/奔跑/偷盗行为、甚至“戴着黄帽子偷电瓶的人”这类复合条件。</p>
            </div>
            <div class=\"survey-arrow\">↑</div>
            <div class=\"survey-box\">
              <b>Index / Storage</b>
              <p>向量索引、特征库、片段清单，让长视频可被检索而不是逐帧重看。</p>
            </div>
          </div>
        </div>
        <div class=\"survey-center\">
          <div class=\"survey-agent\">Video<br>Search</div>
          <div class=\"survey-platforms\">Text → 视频片段 / 人 / 事件 / 异常</div>
        </div>
        <div class=\"survey-col capabilities\">
          <h3>Capabilities</h3>
          <div class=\"survey-stack\">
            <div class=\"survey-cap\">
              <b>Retrieve</b>
              <p>以文搜人、以文搜片段：文本-视频/行人匹配、重识别与部分相关检索。</p>
            </div>
            <div class=\"survey-arrow\">↓</div>
            <div class=\"survey-cap\">
              <b>Ground</b>
              <p>时序定位与事件切分：目标事件发生在哪一段时间区间，给出证据片段。</p>
            </div>
            <div class=\"survey-arrow\">↓</div>
            <div class=\"survey-cap\">
              <b>Judge / Reason</b>
              <p>行为判定与问答：姿态动作理解、异常打分、长视频推理与告警输出。</p>
            </div>
          </div>
        </div>
      </div>
      <div class=\"survey-source\">
        <span class=\"small\">按“输入 → 搜索 → 能力”拆分，本页进一步展开为可点击的 8 个流程层和 6 个模型专题。</span>
      </div>
    </div>
  </section>""",
    )

    # Section 1: 端到端流程关系图
    sub(
        """    <h2>1. 端到端流程关系图：GUI Agent 从任务到验证</h2>
    <div class=\"system-flow\">
      <div class=\"flow-grid\">
        <div class=\"flow-node data\">
          <b>Data / Benchmark</b>
          <p>截图、DOM/A11y、轨迹、人类演示、任务模板、成功检查器。定义训练和评测边界。</p>
        </div>
        <div class=\"flow-arrow\">→</div>
        <div class=\"flow-node main model\">
          <b>Observation</b>
          <p>把屏幕转成 screenshot tokens、OCR、UI tree、SoM 标记或结构化上下文。</p>
        </div>
        <div class=\"flow-node main model\">
          <b>Perception / Parsing</b>
          <p>检测文本、图标、控件、区域、布局块，形成可引用的屏幕状态。</p>
        </div>
        <div class=\"flow-node main model\">
          <b>Semantic Understanding</b>
          <p>理解每个区域/按钮的角色、功能、状态和用户意图相关性。</p>
        </div>
        <div class=\"flow-node main model\">
          <b>Grounding</b>
          <p>把自然语言目标映射到元素 ID、点、bbox 或局部高分辨率区域。</p>
        </div>
        <div class=\"flow-node exec\">
          <b>Action Interface</b>
          <p>输出 click/type/drag、API、PyAutoGUI、Selenium、ADB 或动作 JSON。</p>
        </div>
        <div class=\"flow-node data\" style=\"grid-column:1 / 3;\">
          <b>Task / User Intent</b>
          <p>用户目标、上下文、历史状态和约束条件进入 planner。</p>
        </div>
        <div class=\"flow-node model\" style=\"grid-column:3 / 5;\">
          <b>Planning / Memory / Exploration</b>
          <p>任务拆解、界面探索、技能记忆、反思恢复，持续调用 perception 与 grounding。</p>
        </div>
        <div class=\"flow-node safe\" style=\"grid-column:5 / 7;\">
          <b>Verification / Safety Gate</b>
          <p>执行前后检查权限、风险、不确定性、状态谓词和任务完成度。</p>
        </div>
        <div class=\"flow-node exec\">
          <b>Environment</b>
          <p>真实网页、桌面、移动端、虚拟机、软件沙箱或 MCP 工具环境。</p>
        </div>
        <div class=\"flow-feedback\">Feedback loop: 环境状态和验证结果返回给 planner；成功/失败轨迹进入 SFT、RL、RFT、reward model、test-time scaling 和数据再生成。</div>
      </div>
    </div>
    <h3>11 个流程层</h3>
    <div class=\"pipeline\" id=\"pipeline\"></div>
    <div class=\"flow-note\">
      <div class=\"note-card\"><b>读法</b><br><span class=\"small\">先看 01 数据/评测，再看 03/04/05 屏幕感知、语义理解和定位；只有这些稳定后，再深入 06/07 控制和规划。</span></div>""",
        """    <h2>1. 端到端流程关系图：从视频到答案 / 告警</h2>
    <div class=\"system-flow\">
      <div class=\"flow-grid\">
        <div class=\"flow-node data\">
          <b>Data / Benchmark</b>
          <p>视频数据集、异常/检索/问答基准、标注与指标。定义评测边界。</p>
        </div>
        <div class=\"flow-arrow\">→</div>
        <div class=\"flow-node main model\">
          <b>Video Encoding</b>
          <p>帧采样、视频 token、稠密预测、向量表征，把连续画面变成可计算表示。</p>
        </div>
        <div class=\"flow-node main model\">
          <b>Retrieval</b>
          <p>文本-视频/行人匹配、重识别、以文搜人、部分相关视频检索。</p>
        </div>
        <div class=\"flow-node main model\">
          <b>Temporal Grounding</b>
          <p>时序定位、事件切分、证据片段，回答“发生在哪一段”。</p>
        </div>
        <div class=\"flow-node main model\">
          <b>Human Understanding</b>
          <p>姿态估计、动作识别、运动分割，理解人“在做什么”。</p>
        </div>
        <div class=\"flow-node exec\">
          <b>Anomaly Judgment</b>
          <p>异常打分：摔倒、奔跑、偷盗、闯入等偏离常态行为的判定与定位。</p>
        </div>
        <div class=\"flow-node data\" style=\"grid-column:1 / 3;\">
          <b>Query / User Intent</b>
          <p>自然语言描述（人、动作、场景、组合条件）进入搜索意图解析。</p>
        </div>
        <div class=\"flow-node model\" style=\"grid-column:3 / 5;\">
          <b>Planning / Routing</b>
          <p>查询改写、路由到检索/定位/问答模块、长视频分段与稀疏采样。</p>
        </div>
        <div class=\"flow-node safe\" style=\"grid-column:5 / 7;\">
          <b>Verification / Safety</b>
          <p>结果可信度与证据核对、误报抑制、隐私与合规检查。</p>
        </div>
        <div class=\"flow-node exec\">
          <b>Environment</b>
          <p>监控摄像头、行车记录仪、视频库、边缘设备或 PTZ 相机。</p>
        </div>
        <div class=\"flow-feedback\">Feedback loop: 答案/告警与证据返回用户；误报/漏报轨迹回流到检索、异常与定位模块的重训练。</div>
      </div>
    </div>
    <h3>8 个流程层</h3>
    <div class=\"pipeline\" id=\"pipeline\"></div>
    <div class=\"flow-note\">
      <div class=\"note-card\"><b>读法</b><br><span class=\"small\">先看 01 数据/评测明确指标，再看 02/03/04 表征、检索与定位；行为判定依赖 05/06，长视频问答看 07，落地部署看 08。</span></div>""",
    )

    # Section 3: 模型层专题分组说明
    sub(
        "它和“流程层”不冲突：流程层回答论文处在系统哪一步，模型层专题回答论文的技术路线是什么。比如 ScreenSpot-Pro 的主流程层是数据/评测，但也会进入 grounding 方向；GUI-G1 的主流程层是训练/RL，也会进入 grounding 方向。",
        "它和“流程层”不冲突：流程层回答论文处在系统哪一步，模型层专题回答论文的技术路线是什么。比如 LightAIR 的主流程层是检索/行人搜索，也属于异常检测方向；Evidence-Backed Video QA 的主层是时序定位，也属于视频-语言大模型方向。",
    )

    # Section 4: 搜索占位提示
    sub(
        "placeholder=\"搜索标题、年份、层级、方向，例如 ScreenSpot / RL / desktop / grounding\"",
        "placeholder=\"搜索标题、年份、层级、方向，例如 person / anomaly / grounding / VLM\"",
    )

    # Section 5: 综述锚点
    sub(
        """      <p><b>GUI Agents: A Survey</b>、<b>A Survey on (M)LLM-Based GUI Agents</b>、<b>Towards Trustworthy GUI Agents</b> 是理解这个领域的三个综述入口。它们通常把 GUI agent 拆成 perception、exploration/planning、interaction、evaluation/safety；本页面把这些概念进一步拆成更适合读论文和做系统的 11 个工程层。</p>""",
        """      <p>视频搜索方向目前还没有统一综述，本页把收录论文按 8 层流程组织成一份可浏览地图（含图像检索与跨模态检索）。要实现“检测视频中出现的人、摔倒/奔跑/偷盗行为、乃至戴着黄帽子偷电瓶的人”这类复合查询，典型组合路径是：<b>03 检索（以文搜人/图像）</b> + <b>05 姿态/动作理解</b> + <b>06 异常检测</b> + <b>04 时序定位（输出片段）</b>，长视频场景再由 <b>07 视频 LLM</b> 兜底推理、<b>08 边缘部署</b> 落地。</p>""",
    )

    return template


def main() -> None:
    print("构建 video-search 数据…")
    data = build_data()
    print(f"  论文数: {data['count']}")
    print(f"  时间范围: {data['oldest']} ~ {data['newest']}")
    for s in data["stages"]:
        print(f"    {s['title']}: {s['count']}")
    detail_count = write_detail_files(data)
    print(f"  按需详情: {detail_count} 个 JSON 文件")
    print("生成 HTML…")
    html = generate_html(data)
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"✅ 已写入 {OUTPUT.relative_to(ROOT)} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
