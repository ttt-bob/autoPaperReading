#!/usr/bin/env bash
# Synchronize the public Nginx-backed site from the master paper database.

set -euo pipefail

MASTER_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(cd "$MASTER_DIR/../.." && pwd)"
PERF_DIR="${PERF_WORKTREE_DIR:-$WORKSPACE_DIR/worktrees/autoPaperReading-perf}"
UV_BIN="${UV_BIN:-$HOME/.local/bin/uv}"
# shellcheck source=scripts/git_push_with_retry.sh
source "$MASTER_DIR/scripts/git_push_with_retry.sh"

if [[ ! -d "$PERF_DIR/.git" && ! -f "$PERF_DIR/.git" ]]; then
    echo "⚠️  Public-site worktree not found: $PERF_DIR; skip public sync."
    exit 0
fi

if [[ ! -e "$PERF_DIR/data/papers.db" ]]; then
    ln -s "$MASTER_DIR/data/papers.db" "$PERF_DIR/data/papers.db"
fi

if [[ ! -e "$PERF_DIR/data/pdfs" ]]; then
    ln -s "$MASTER_DIR/data/pdfs" "$PERF_DIR/data/pdfs"
fi

cd "$PERF_DIR"
export UV_NO_SYNC=1
export UV_PROJECT_ENVIRONMENT="$MASTER_DIR/.venv"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"

"$UV_BIN" run python jobs/export_papers.py --cloud
"$UV_BIN" run python jobs/export_gui_taxonomy.py
"$UV_BIN" run python jobs/build_video_search_page.py

git add docs/papers.json docs/paper-data docs/index.html docs/gui-taxonomy.html docs/video-search.html
git diff --cached --quiet || git commit -m "📚 Update performance page $(date +%Y-%m-%d)"
configured_proxy="$(git_push_proxy_from_config "$MASTER_DIR/config.yaml")"
GIT_PUSH_PROXY_URL="${GIT_PUSH_PROXY_URL:-$configured_proxy}" \
    git_push_with_retry origin HEAD
