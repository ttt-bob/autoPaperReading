"""
rag/arxiv_fetcher.py - 从 arXiv 抓取 CV 方向论文
"""
import logging
import os
import random
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import arxiv
import yaml

logger = logging.getLogger(__name__)

RETRYABLE_HTTP_STATUSES = {429, 500, 502, 503, 504}
DEFAULT_API_RETRIES = 4
DEFAULT_PAGE_SIZE = 25
DEFAULT_TOPIC_CHUNK_SIZE = 8

# ===== 代理配置 =====
_proxy_config: dict = {}


def load_proxy_config() -> dict:
    """从 config.yaml 加载代理配置"""
    global _proxy_config
    if _proxy_config:
        return _proxy_config

    config_path = Path("config.yaml")
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            _proxy_config = config.get("proxy", {})
    else:
        _proxy_config = {}
    return _proxy_config


def setup_proxy_env() -> bool:
    """
    根据配置设置代理环境变量（供 arxiv 库使用）。

    Returns:
        True 表示已设置代理，False 表示直接连接
    """
    config = load_proxy_config()

    if not config.get("enabled", False):
        clear_proxy_env()
        return False

    mode = config.get("mode", "single")

    if mode == "direct":
        clear_proxy_env()
        return False

    proxy = None
    if mode == "single":
        proxy = config.get("single_proxy")
    elif mode == "pool":
        pool = config.get("proxy_pool", [])
        if pool:
            proxy = random.choice(pool)

    if proxy:
        os.environ["http_proxy"] = proxy
        os.environ["https_proxy"] = proxy
        os.environ["all_proxy"] = proxy
        os.environ["HTTP_PROXY"] = proxy
        os.environ["HTTPS_PROXY"] = proxy
        os.environ["ALL_PROXY"] = proxy
        logger.info(f"已设置代理: {proxy}")
        return True

    return False


def clear_proxy_env() -> None:
    """清除代理环境变量"""
    for k in (
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
    ):
        os.environ.pop(k, None)


def build_query(
    topics: list[str],
    category: str = "cs.CV",
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """
    构建 arXiv 查询语句

    策略：组合关键词 + 按时间排序
    支持通过 submittedDate 语法指定日期范围，精确到天。
    示例: cat:cs.CV AND ("object detection" OR "segmentation") AND submittedDate:[20260520 TO 20260520]
    """
    parts = []
    if category:
        parts.append(f"cat:{category}")
    if topics:
        topic_clauses = " OR ".join(f'"{t}"' for t in topics)
        parts.append(f"({topic_clauses})")
    if date_from or date_to:
        d_from = date_from.replace("-", "") if date_from else "00000101"
        d_to = date_to.replace("-", "") if date_to else "99991231"
        parts.append(f"submittedDate:[{d_from} TO {d_to}]")

    return " AND ".join(parts) if parts else ""


def fetch_papers(
    topics: list[str],
    category: str = "cs.CV",
    max_results: int = 50,
    days_back: int = 7,
    sort_by: arxiv.SortCriterion = arxiv.SortCriterion.SubmittedDate,
    date: str | None = None,
) -> list[dict]:
    """
    从 arXiv 抓取论文

    Args:
        topics: 关键词列表
        category: arXiv 分类
        max_results: 最多返回多少条
        days_back: 向前追溯多少天（客户端过滤，date 参数设置时自动禁用）
        sort_by: 排序方式
        date: 指定日期 YYYY-MM-DD，精确抓取该天的论文（使用 API 端 submittedDate 过滤）

    Returns:
        论文列表，每条包含 paper_id, title, authors, abstract, published, pdf_url, entry_url
    """
    query = build_query(topics, category, date_from=date, date_to=date)
    logger.info(f"arXiv 查询: {query}")

    # 设置代理环境变量
    setup_proxy_env()

    # 获取请求延迟配置
    config = load_proxy_config()
    min_delay = config.get("min_delay", 3.0)
    max_delay = config.get("max_delay", 8.0)
    page_size = _bounded_page_size(max_results)

    try:
        papers = _fetch_papers_for_query(
            query=query,
            max_results=max_results,
            days_back=days_back,
            sort_by=sort_by,
            date=date,
            min_delay=min_delay,
            max_delay=max_delay,
            page_size=page_size,
            config=config,
        )
        logger.info(f"共抓取 {len(papers)} 篇论文")
        return papers
    except Exception as e:
        if not topics or len(topics) <= DEFAULT_TOPIC_CHUNK_SIZE or not _is_retryable_api_error(e):
            raise

        logger.warning(
            "arXiv 大查询多次失败，尝试按关键词拆分为小查询后合并结果: %s",
            e,
        )
        papers = _fetch_papers_by_topic_chunks(
            topics=topics,
            category=category,
            max_results=max_results,
            days_back=days_back,
            sort_by=sort_by,
            date=date,
            min_delay=min_delay,
            max_delay=max_delay,
            page_size=page_size,
            config=config,
        )
        logger.info(f"共抓取 {len(papers)} 篇论文")
        return papers


def _fetch_papers_for_query(
    query: str,
    max_results: int,
    days_back: int,
    sort_by: arxiv.SortCriterion,
    date: str | None,
    min_delay: float,
    max_delay: float,
    page_size: int,
    config: dict,
) -> list[dict]:
    """执行一次 arXiv 查询，并对官方 API 的临时错误做指数退避重试。"""
    last_error: Exception | None = None

    for attempt in range(DEFAULT_API_RETRIES + 1):
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=sort_by,
            sort_order=arxiv.SortOrder.Descending,
        )
        client = arxiv.Client(
            page_size=page_size,
            delay_seconds=random.uniform(min_delay, max_delay),
            num_retries=1,
        )

        try:
            papers = []
            for result in client.results(search):
                # 指定 date 时禁用客户端 days_back 过滤（API 端已过滤）
                if date is None and days_back > 0:
                    cutoff = datetime.now(result.published.tzinfo) - timedelta(days=days_back)
                    if result.published < cutoff:
                        continue

                papers.append(_paper_from_result(result))
                time.sleep(random.uniform(min_delay, max_delay))
            return papers

        except Exception as e:
            last_error = e
            if not _is_retryable_api_error(e) or attempt >= DEFAULT_API_RETRIES:
                raise

            wait = _retry_wait_seconds(attempt, min_delay, max_delay)
            status = _http_status(e)
            reason = f"HTTP {status}" if status else e.__class__.__name__
            logger.warning(
                "arXiv API 临时错误 (%s)，等待 %.1fs 后重试（第 %s/%s 次）: %s",
                reason,
                wait,
                attempt + 1,
                DEFAULT_API_RETRIES,
                e,
            )
            time.sleep(wait)

            # 限流/临时错误时切换代理池（如果有）
            if config.get("mode") == "pool":
                setup_proxy_env()

    if last_error:
        raise last_error
    return []


def _fetch_papers_by_topic_chunks(
    topics: list[str],
    category: str,
    max_results: int,
    days_back: int,
    sort_by: arxiv.SortCriterion,
    date: str | None,
    min_delay: float,
    max_delay: float,
    page_size: int,
    config: dict,
) -> list[dict]:
    combined: dict[str, dict] = {}
    failed_chunks = 0
    last_error: Exception | None = None

    for start in range(0, len(topics), DEFAULT_TOPIC_CHUNK_SIZE):
        chunk = topics[start:start + DEFAULT_TOPIC_CHUNK_SIZE]
        query = build_query(chunk, category, date_from=date, date_to=date)
        logger.info(
            "arXiv 分片查询 %s-%s/%s: %s",
            start + 1,
            min(start + len(chunk), len(topics)),
            len(topics),
            query,
        )

        try:
            papers = _fetch_papers_for_query(
                query=query,
                max_results=max_results,
                days_back=days_back,
                sort_by=sort_by,
                date=date,
                min_delay=min_delay,
                max_delay=max_delay,
                page_size=page_size,
                config=config,
            )
        except Exception as e:
            failed_chunks += 1
            last_error = e
            logger.warning("arXiv 分片查询失败，跳过该分片: %s", e)
            continue

        for paper in papers:
            combined.setdefault(paper["paper_id"], paper)

        time.sleep(random.uniform(min_delay, max_delay))

    if not combined and failed_chunks:
        raise RuntimeError("所有 arXiv 分片查询均失败") from last_error

    return sorted(
        combined.values(),
        key=lambda p: p.get("published", ""),
        reverse=True,
    )[:max_results]


def _paper_from_result(result: arxiv.Result) -> dict:
    return {
        "paper_id": result.get_short_id(),
        "title": _clean_text(result.title),
        "authors": ", ".join(a.name for a in result.authors),
        "abstract": _clean_text(result.summary),
        "published": result.published.isoformat(),
        "updated": (
            result.updated.isoformat()
            if hasattr(result, "updated")
            else result.published.isoformat()
        ),
        "pdf_url": result.pdf_url,
        "entry_url": result.entry_id,
        "comment": getattr(result, "comment", "") or "",
        "doi": getattr(result, "doi", "") or "",
        "journal_ref": getattr(result, "journal_ref", "") or "",
        "primary_category": result.primary_category,
        "categories": ", ".join(result.categories),
    }


def _bounded_page_size(max_results: int) -> int:
    if max_results <= 0:
        return DEFAULT_PAGE_SIZE
    return max(1, min(max_results, DEFAULT_PAGE_SIZE))


def _http_status(error: Exception) -> int | None:
    status = getattr(error, "status", None)
    if isinstance(status, int):
        return status

    match = re.search(r"HTTP\s+(\d{3})", str(error))
    return int(match.group(1)) if match else None


def _is_retryable_api_error(error: Exception) -> bool:
    status = _http_status(error)
    if status in RETRYABLE_HTTP_STATUSES:
        return True

    text = str(error).lower()
    return any(
        marker in text
        for marker in (
            "too many requests",
            "temporarily unavailable",
            "timeout",
            "timed out",
            "connectionerror",
            "connection aborted",
            "max retries",
        )
    )


def _retry_wait_seconds(attempt: int, min_delay: float, max_delay: float) -> float:
    base = max(5.0, min_delay) * (2 ** attempt)
    jitter = random.uniform(0, max(1.0, max_delay))
    return min(120.0, base + jitter)


def fetch_latest_papers(
    category: str = "cs.CV",
    max_results: int = 30,
) -> list[dict]:
    """
    抓取某分类下最新的论文（不按关键词过滤，适合广撒网）
    """
    search = arxiv.Search(
        query=f"cat:{category}",
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )
    client = arxiv.Client(page_size=50, delay_seconds=3.0, num_retries=3)

    papers = []
    for result in client.results(search):
        papers.append({
            "paper_id": result.get_short_id(),
            "title": _clean_text(result.title),
            "authors": ", ".join(a.name for a in result.authors),
            "abstract": _clean_text(result.summary),
            "published": result.published.isoformat(),
            "pdf_url": result.pdf_url,
            "entry_url": result.entry_id,
        })
        time.sleep(0.5)

    return papers


def _clean_text(text: str) -> str:
    """清理文本中的多余空白字符"""
    import re
    text = re.sub(r'\s+', ' ', text)
    return text.strip()
