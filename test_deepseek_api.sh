#!/usr/bin/env bash
# Minimal DeepSeek official API smoke test.
# Usage:
#   ./test_deepseek_api.sh
#   ./test_deepseek_api.sh "请用中文回答：1+1等于几？只回答数字。"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
PROMPT="${1:-请用中文回答：1+1等于几？只回答数字。}"

if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "Python not found: $PYTHON_BIN"
    echo "Run: uv sync"
    exit 1
fi

"$PYTHON_BIN" - "$PROMPT" <<'PY'
import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

prompt = sys.argv[1]

load_dotenv(".env")

base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
api_key = os.getenv("DEEPSEEK_API_KEY", "")

print(f"base_url={base_url}")
print(f"model={model}")
print(f"api_key_configured={bool(api_key and not api_key.startswith('sk-your'))}")

if not api_key or api_key.startswith("sk-your"):
    raise SystemExit("DEEPSEEK_API_KEY is not configured in .env")

client = OpenAI(api_key=api_key, base_url=base_url)

try:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=64,
    )
    choice = response.choices[0]
    message = choice.message

    print("chat_success=True")
    print(f"finish_reason={choice.finish_reason}")
    print("reply=" + repr(message.content or ""))

    reasoning = getattr(message, "reasoning_content", None)
    if reasoning:
        print("reasoning=" + repr(reasoning))

    if response.usage:
        print(f"prompt_tokens={response.usage.prompt_tokens}")
        print(f"completion_tokens={response.usage.completion_tokens}")
        print(f"total_tokens={response.usage.total_tokens}")

except Exception as exc:
    print("chat_success=False")
    print("error_type=" + exc.__class__.__name__)
    print("error=" + str(exc))
    raise SystemExit(1) from exc
PY
