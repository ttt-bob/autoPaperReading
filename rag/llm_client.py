"""
rag/llm_client.py - 统一 LLM 客户端

支持三种后端（按优先级）：
  1. DeepSeek API（推荐，便宜且中文强）
  2. Ollama（本地 Mac M1/M2）
  3. OpenAI API（云端）

通过环境变量自动选择后端：
  - DEEPSEEK_API_KEY 存在 → DeepSeek
  - Ollama 服务可达 → Ollama
  - OPENAI_API_KEY 存在 → OpenAI
"""
import logging
import os
import re

import requests
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

logger = logging.getLogger(__name__)

# ========== 配置检测 ==========
_DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
_DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
_DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# 优先级：DeepSeek > Ollama > OpenAI
_USE_DEEPSEEK = bool(_DEEPSEEK_API_KEY and _DEEPSEEK_API_KEY != "sk-your-openai-api-key-here")
_USE_OLLAMA = False
if not _USE_DEEPSEEK and _OLLAMA_BASE_URL:
    try:
        r = requests.get(f"{_OLLAMA_BASE_URL}/api/tags", timeout=3)
        _USE_OLLAMA = r.status_code == 200
    except Exception:
        _USE_OLLAMA = False

_BACKEND = "deepseek" if _USE_DEEPSEEK else ("ollama" if _USE_OLLAMA else "openai")
logger.info(f"LLM Client 后端: {_BACKEND.upper()}")


# ========== LLM 调用 ==========

def chat(
    prompt: str,
    model: str = "deepseek-v4-flash",
    system: str = "",
    temperature: float = 0.2,
    max_tokens: int = 2048,
) -> str:
    """
    统一的 chat 接口，自动选择后端

    Args:
        prompt: 用户 prompt
        model: 模型名（DeepSeek/OpenAI 格式）
        system: 系统提示词
        temperature: 采样温度
        max_tokens: 最大生成长度
    """
    if _USE_DEEPSEEK:
        return _deepseek_chat(
            prompt=prompt, model=model, system=system,
            temperature=temperature, max_tokens=max_tokens,
        )
    elif _USE_OLLAMA:
        return _ollama_chat(
            prompt=prompt, model=model, system=system,
            temperature=temperature, max_tokens=max_tokens,
        )
    else:
        return _openai_chat(
            prompt=prompt, model=model, system=system,
            temperature=temperature, max_tokens=max_tokens,
        )


# ---------- DeepSeek ----------
def _deepseek_chat(
    prompt: str,
    model: str,
    system: str = "",
    temperature: float = 0.2,
    max_tokens: int = 2048,
) -> str:
    """
    DeepSeek API 调用（OpenAI 兼容格式）

    model 参数：
      - deepseek-v4-flash：便宜快速，适合摘要（推荐）
      - deepseek-v4-pro：更强，支持思考模式
    """
    effective_model = _DEEPSEEK_MODEL if model == "deepseek-v4-flash" else model

    client = OpenAI(
        api_key=_DEEPSEEK_API_KEY,
        base_url=_DEEPSEEK_BASE_URL,
        timeout=120.0,
        max_retries=0,
    )

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        response = client.chat.completions.create(
            model=effective_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.error(f"DeepSeek API 失败 [{effective_model}]: {e}")
        raise


# ---------- Ollama ----------
def _ollama_chat(
    prompt: str,
    model: str,
    system: str = "",
    temperature: float = 0.2,
    max_tokens: int = 2048,
) -> str:
    """
    Ollama chat 接口

    支持两类模型：
    1. 普通模型（qwen2 等）：内容在 content 字段
    2. Thinking 模型（gemma4, deepseek-r1 等）：内容可能在 thinking 字段
    """
    import ollama

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    ollama_opts = {
        "temperature": temperature,
        "num_predict": max_tokens,
    }

    # qwen3 系列需要禁用 thinking
    extra_kwargs = {}
    if model.startswith("qwen3") or model.startswith("qwen2") or "qwen3" in model:
        extra_kwargs["think"] = False

    try:
        response = ollama.chat(
            model=model,
            messages=messages,
            options=ollama_opts,
            **extra_kwargs,
        )
        content = response["message"]["content"]
        thinking = response["message"].get("thinking", "")

        # gemma4/deepseek-r1 等模型 content 为空时从 thinking 提取
        if not content.strip() and thinking.strip():
            return extract_final_answer_from_thinking(thinking)

        return content.strip() if content.strip() else thinking.strip()

    except Exception as e:
        logger.error(f"Ollama chat 失败 [{model}]: {e}")
        raise


def extract_final_answer_from_thinking(thinking: str) -> str:
    """
    从 gemma4/deepseek-r1 的 thinking 字段中提取最终回答

    gemma4 thinking 格式示例：
    ```
    Here's a thinking process:
    1.  **Analyze:** ...
    2.  **Drafting:** ...
       *   *Draft 1:* 实际回答内容...
       *   *Sentence 1:* 简短说明...
    ```
    """
    thinking = thinking.strip()
    lines = thinking.split("\n")

    draft_answers = []
    sentence_answers = []

    for line in lines:
        if re.match(r'^\s*\d+\.\s+\*\*', line):
            continue

        # Draft 行
        m = re.search(r'\*Draft\s*\d*\s*(?:\([^)]*\))?\s*:\s*\*\s*(.+)', line, re.IGNORECASE)
        if m:
            content = m.group(1).strip()
            if content and len(content) > 10:
                content = re.sub(r'\s*\([^)]*\)\s*$', '', content).strip()
                draft_answers.append(content)
                continue

        # Sentence 行
        m2 = re.search(r'\*Sentence\s*\d+\s*(?:\([^)]*\))?\s*:\*\s*(.+)', line, re.IGNORECASE)
        if m2:
            content = m2.group(1).strip()
            if content and len(content) > 10:
                content = re.sub(r'\s*\([^)]*\)\s*$', '', content).strip()
                sentence_answers.append(content)

    if draft_answers:
        return draft_answers[-1]
    if sentence_answers:
        return sentence_answers[-1]

    for line in reversed(lines):
        line = line.strip()
        if not line or len(line) > 400:
            continue
        if "here's a " in line.lower() or line.lower().startswith("here is a "):
            continue
        if len(line) < 15:
            continue
        return line

    return thinking[:500]


# ---------- OpenAI ----------
def _openai_chat(
    prompt: str,
    model: str,
    system: str = "",
    temperature: float = 0.2,
    max_tokens: int = 2048,
) -> str:
    """OpenAI chat 接口"""
    client = OpenAI()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content


# ========== Embedding 调用 ==========

def embed_text(text: str, model: str = "nomic-embed-text") -> list[float]:
    """
    统一的 embedding 接口

    优先级：Ollama nomic-embed-text > DeepSeek > OpenAI
    """
    if _USE_OLLAMA:
        return _ollama_embed(text, model=model)
    elif _USE_DEEPSEEK:
        return _deepseek_embed(text, model=model)
    else:
        return _openai_embed(text, model=model)


def _ollama_embed(text: str, model: str = "nomic-embed-text") -> list[float]:
    """Ollama embedding 接口"""
    import ollama
    try:
        response = ollama.embed(model=model, input=text)
        return response["embeddings"][0]
    except Exception as e:
        logger.error(f"Ollama embedding 失败 [{model}]: {e}")
        raise
def _deepseek_embed(text: str, model: str = "deepseek-embedding") -> list[float]:
    """
    DeepSeek Embedding API
    """
    client = OpenAI(
        api_key=_DEEPSEEK_API_KEY,
        base_url=_DEEPSEEK_BASE_URL,
    )
    response = client.embeddings.create(
        model="deepseek-embedding",
        input=text,
    )
    return response.data[0].embedding


def _openai_embed(text: str, model: str = "text-embedding-3-small") -> list[float]:
    """OpenAI embedding 接口"""
    client = OpenAI()
    response = client.embeddings.create(model=model, input=text)
    return response.data[0].embedding


# ========== Embedding 维度映射 ==========
EMBEDDING_DIMENSIONS = {
    "nomic-embed-text": 768,
    "deepseek-embedding": 1024,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


def get_embedding_dimension(model: str) -> int:
    """获取 embedding 模型对应的向量维度"""
    return EMBEDDING_DIMENSIONS.get(model, 768)


def get_backend_info() -> dict:
    """获取当前后端信息"""
    return {
        "backend": _BACKEND,
        "deepseek_model": _DEEPSEEK_MODEL if _USE_DEEPSEEK else None,
        "ollama_url": _OLLAMA_BASE_URL if _USE_OLLAMA else None,
        "openai_configured": bool(_OPENAI_API_KEY and _OPENAI_API_KEY != "sk-your-openai-api-key-here"),
    }
