#!/usr/bin/env python3
"""
app.py - CV 论文浏览界面

Usage:
    uv run streamlit run app.py
    浏览器打开: http://localhost:8501
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
import yaml
from datetime import datetime

from rag import db


# ========== 页面配置 ==========
st.set_page_config(
    page_title="CV Papers",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ========== 加载配置 ==========
@st.cache_data
def load_config() -> dict:
    cfg_path = Path("config.yaml")
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}


config = load_config()
llm_model = config.get("llm", {}).get("model", "deepseek-v4-flash")

# ========== 初始化数据库 ==========
db.init_db()

# ========== Session State ==========
if "selected_tags" not in st.session_state:
    st.session_state.selected_tags = []

# ========== Tag Toggle Callback ==========
def toggle_tag_callback(tag: str):
    """按钮点击时切换标签筛选状态"""
    if tag in st.session_state.selected_tags:
        st.session_state.selected_tags.remove(tag)
    else:
        st.session_state.selected_tags.append(tag)


# ========== 辅助函数 ==========
def get_paper_tag_list(tags_str: str) -> list[str]:
    if not tags_str:
        return []
    return [t.strip().lower() for t in tags_str.replace("\n", " ").split(",") if t.strip()]


def paper_matches(paper: dict, selected_tags: set[str], query: str) -> bool:
    if query:
        q = query.lower()
        haystack = " ".join([
            paper.get("title", ""),
            paper.get("authors", ""),
            paper.get("abstract", ""),
            paper.get("summary", ""),
        ]).lower()
        if q not in haystack:
            return False

    if not selected_tags:
        return True

    paper_tags = set(get_paper_tag_list(paper.get("tags", "") or ""))
    return bool(paper_tags & set(selected_tags))


# ========== 侧边栏 ==========
with st.sidebar:
    st.title("📚 CV Papers")
    st.caption("arXiv CS.CV · auto updated")

    st.divider()

    # ---- 统计 ----
    try:
        total_papers = db.count_papers()
        fav_count = db.count_favorites()
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Papers", total_papers)
        with col2:
            st.metric("Favorites", fav_count)
    except Exception as e:
        st.warning(f"DB error: {e}")

    st.divider()

    # ---- Top 20 Tags 导航 ----
    try:
        all_tags = db.get_all_tags()
        top_tags = all_tags[:20]
    except Exception:
        top_tags = []

    st.markdown("### Filter by Tag")

    if top_tags:
        cols = st.columns(2)
        for i, t_info in enumerate(top_tags):
            tag = t_info["tag"]
            count = t_info["count"]
            is_sel = tag in st.session_state.selected_tags
            label = f"{'✓ ' if is_sel else ''}{tag} ({count})"
            with cols[i % 2]:
                st.button(
                    label,
                    key=f"tag_{i}_{tag}",
                    use_container_width=True,
                    type="primary" if is_sel else "secondary",
                    on_click=toggle_tag_callback,
                    args=(tag,),
                )
    else:
        st.caption("No tags yet")

    st.divider()

    # 清除筛选
    if st.session_state.selected_tags:
        st.caption(f"Selected: {len(st.session_state.selected_tags)} tag(s)")
        if st.button("Clear filters", use_container_width=True):
            st.session_state.selected_tags = []
            st.rerun()

    st.divider()
    st.caption(f"LLM: {llm_model}")


# ========== 主页面 ==========
st.title("CV Papers")

# 搜索栏
search_query = st.text_input(
    "Search papers, authors, content...",
    placeholder="e.g. diffusion model, transformer...",
    label_visibility="collapsed",
    key="search_input",
)

# 时间范围 + 排序
col_days, col_sort = st.columns([1, 2])
with col_days:
    days = st.selectbox("Time range", [1, 7, 30, 90, 365], index=1, label_visibility="collapsed", key="days_main")
with col_sort:
    sort_by = st.selectbox(
        "Sort",
        ["Latest first", "Oldest first", "Title A-Z"],
        label_visibility="collapsed",
        key="sort_main",
    )

# 当前筛选状态
if st.session_state.selected_tags:
    tag_labels = ", ".join(sorted(st.session_state.selected_tags))
    st.info(f"Filtering by: {tag_labels}")

# 获取并筛选论文
try:
    papers = db.get_papers(since_days=days, limit=500)
except Exception as e:
    st.error(f"Load failed: {e}")
    papers = []

filtered = [
    p for p in papers
    if paper_matches(p, st.session_state.selected_tags, search_query)
]

# 排序
if sort_by == "Latest first":
    filtered.sort(key=lambda x: x.get("published", ""), reverse=True)
elif sort_by == "Oldest first":
    filtered.sort(key=lambda x: x.get("published", ""))
else:
    filtered.sort(key=lambda x: x.get("title", ""))

st.markdown(f"**{len(filtered)}** papers" + (f" (of {len(papers)} total)" if len(filtered) < len(papers) else ""))

# 渲染论文卡片
for paper in filtered:
    with st.container():
        col_info, col_action = st.columns([4, 1])

        with col_info:
            faved = db.is_favorited(paper["paper_id"])
            title_display = f"**{paper['title']}**"
            if faved:
                title_display += " · ❤️"
            st.markdown(title_display)

            st.caption(f"👥 {paper['authors'][:80]}")
            date_str = paper.get("published", "N/A")
            st.caption(f"📅 {date_str[:10]} · 🆔 {paper['paper_id']}")

            tags_str = paper.get("tags", "") or ""
            if tags_str:
                tags_list = get_paper_tag_list(tags_str)
                st.caption(f"🏷️ {' · '.join(tags_list[:6])}")

        with col_action:
            st.markdown(f"[arXiv]({paper['entry_url']})")
            st.markdown(f"[PDF]({paper['pdf_url']})")

            faved = db.is_favorited(paper["paper_id"])
            fav_label = "❤️ Saved" if faved else "🤍 Save"
            if st.button(fav_label, key=f"fav_{paper['paper_id']}", use_container_width=True):
                if faved:
                    db.remove_favorite(paper["paper_id"])
                else:
                    st.session_state[f"show_tag_{paper['paper_id']}"] = True
                st.rerun()

            if st.session_state.get(f"show_tag_{paper['paper_id']}", False):
                tag_input = st.text_input(
                    "Tags (comma separated)",
                    key=f"tag_input_{paper['paper_id']}",
                    placeholder="important, method improvement",
                )
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Confirm", key=f"confirm_{paper['paper_id']}"):
                        if tag_input:
                            tags_list = [t.strip() for t in tag_input.split(",") if t.strip()]
                            db.add_favorite(paper["paper_id"], tags_list)
                            st.session_state[f"show_tag_{paper['paper_id']}"] = False
                            st.rerun()
                with c2:
                    if st.button("Cancel", key=f"cancel_{paper['paper_id']}"):
                        st.session_state[f"show_tag_{paper['paper_id']}"] = False
                        st.rerun()

        # 总结全文
        summary = paper.get("summary", "") or ""
        if summary:
            with st.expander("📖 View Summary"):
                st.markdown(summary)

        st.divider()

if not filtered:
    st.info("No papers match the current filters. Try adjusting your search or tags.")

# ========== 页脚 ==========
st.markdown("---")
st.caption(
    "Disclaimer: Paper summaries are AI-generated and may not reflect the full paper content. "
    "Please refer to the original paper for judgment."
)
