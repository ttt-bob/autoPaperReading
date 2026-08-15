#!/bin/bash
# ============================================================
# CV Paper Reading - 每日任务启动脚本
# 用法:
#   ./run_daily.sh                    # 全新运行
#   ./run_daily.sh --resume           # 断点续传
#   ./run_daily.sh --date YYYY-MM-DD  # 按日期回填
#   ./run_daily.sh --auto             # 自动模式（配合定时任务，成功一次当天不再跑）
#   ./run_daily.sh --url URL --gui    # 补录论文，按 GUI 类别总结并同步页面
#   ./run_daily.sh --url FILE         # 从文本文件批量补录（每行一个 URL / arXiv ID）
#
# 支持断点续传: 中断后运行 ./run_daily.sh --resume
#   自动跳过已完成步骤，已入库的论文不会被重复处理。
#
# 支持按日期回填: ./run_daily.sh --date 2026-05-20
#   精确抓取指定日期的论文并生成摘要。
#
# --auto 自动模式:
#   配合 cron/launchd 每天定时执行，当日成功运行后自动跳过后续调度。
#   每天 10:00 开始，并保留两小时一次的重试窗口：
#   例如 crontab: 0 10,12,14,16,18 * * * cd ... && ./run_daily.sh --auto
#   10:00 失败 → 12:00 自动重试 → 14:00 继续 → 直到成功一次 → 后续跳过
#
# 环境变量（可覆盖默认值）:
#   MAX_RESULTS=100   每次最多抓取多少条
#   DAYS_BACK=30      追溯多少天内的论文
#   BATCH_SIZE=15     每批处理多少篇
#   CLASH_AUTO_START=1  自动模式下，使用本地 Clash 代理时先执行 clashctl on
#   CLASH_START_TIMEOUT=15  等待本地代理端口就绪的秒数
#   SYNC_OS_AGENT_SURVEY=1  同步 OS-Agent-Survey 新增论文到 GUI 总结页
#   OS_AGENT_SURVEY_MAX_NEW=3  限制每次最多补录多少篇新增外部清单论文（默认不限制）
#   GIT_PUSH_MAX_ATTEMPTS=6  Git 推送最多尝试次数
#   GIT_PUSH_INITIAL_DELAY_SECONDS=10  首次重试前等待秒数（之后指数退避）
#   GIT_PUSH_MAX_DELAY_SECONDS=60  单次重试等待上限
#   GIT_PUSH_PROXY_URL=http://127.0.0.1:7890  Git 推送备用代理（默认读取 proxy 配置）
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
# shellcheck source=scripts/git_push_with_retry.sh
source "$SCRIPT_DIR/scripts/git_push_with_retry.sh"

# A daily run may write the database, generated site files, and Git history.
# Refuse a second concurrent run instead of allowing two imports to race.
PIPELINE_LOCK_FILE="${PIPELINE_LOCK_FILE:-/tmp/auto-paper-reading-pipeline.lock}"
if command -v flock >/dev/null 2>&1; then
    exec 9>"$PIPELINE_LOCK_FILE"
    if ! flock -n 9; then
        echo "⚠️ 已有抓取/补录任务正在运行，当前任务未启动。请等待其完成后重试。"
        exit 1
    fi
fi

# launchd runs with a minimal PATH and often cannot find user-installed tools.
export PATH="${PATH}:${HOME}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# --- 配置 ---
MAX_RESULTS="${MAX_RESULTS:-10}"
DAYS_BACK="${DAYS_BACK:-7}"
BATCH_SIZE="${BATCH_SIZE:-5}"

# --- 状态文件 ---
# 格式: RUN_ID|STEP|TIMESTAMP
STATE_FILE="$SCRIPT_DIR/.run_state"
# 每日完成标记（--auto 模式用）
DONE_FILE="$SCRIPT_DIR/.daily_done"

get_run_id() {
    [[ -f "$STATE_FILE" ]] && cut -d'|' -f1 "$STATE_FILE" 2>/dev/null
}

get_step() {
    [[ -f "$STATE_FILE" ]] && cut -d'|' -f2 "$STATE_FILE" 2>/dev/null || echo "none"
}

mark_state() {
    local step="$1"
    local run_id
    run_id=$(get_run_id) || true
    [[ -z "$run_id" ]] && run_id="$(date '+%Y%m%d_%H%M%S')"
    echo "${run_id}|${step}|$(date '+%Y-%m-%d %H:%M:%S')" > "$STATE_FILE"
}

maybe_mark_state() {
    if [[ "${STATE_ENABLED:-1}" != "0" ]]; then
        mark_state "$1"
    fi
    return 0
}

get_local_proxy_endpoint() {
    # 仅在 config.yaml 显式启用了 single 模式的本机代理时，返回其地址。
    # 非本机代理和 direct 模式不应由本脚本管理。
    git_push_proxy_from_config "$SCRIPT_DIR/config.yaml"
}

local_proxy_is_ready() {
    local host="$1"
    local port="$2"

    if command -v nc >/dev/null 2>&1; then
        nc -z -w 1 "$host" "$port" >/dev/null 2>&1
        return $?
    fi

    # macOS 默认带 nc；这只是没有 nc 时的 Bash 兜底。
    (exec 3<>"/dev/tcp/$host/$port") >/dev/null 2>&1
}

ensure_local_proxy_ready() {
    [[ "${PROXY_PRECHECK_ENABLED:-1}" == "1" ]] || return 0

    local endpoint host port clashctl_bin attempt timeout
    endpoint="$(get_local_proxy_endpoint)"
    [[ -n "$endpoint" ]] || return 0

    if [[ "$endpoint" =~ ^https?://(127\.0\.0\.1|localhost):([0-9]+)/?$ ]]; then
        host="${BASH_REMATCH[1]}"
        port="${BASH_REMATCH[2]}"
    else
        return 0
    fi

    clashctl_bin="${CLASHCTL_BIN:-clashctl}"
    if [[ "${CLASH_AUTO_START:-1}" == "1" ]]; then
        # 本机的 clashctl 是由 ~/.bashrc source 进来的 Bash 函数，不是 PATH
        # 中的可执行文件。定时任务使用非交互 Shell，不会读取 ~/.bashrc；在
        # 默认安装位置直接加载函数定义，避免依赖交互式环境。
        if ! command -v "$clashctl_bin" >/dev/null 2>&1 && [[ "$clashctl_bin" == "clashctl" ]]; then
            local clashctl_home="${CLASHCTL_HOME:-$HOME/clashctl}"
            local clashctl_definition="$clashctl_home/scripts/cmd/clashctl.sh"
            if [[ -f "$clashctl_definition" ]]; then
                export CLASHCTL_HOME="$clashctl_home"
                # shellcheck source=/dev/null
                source "$clashctl_definition"
            fi
        fi

        if command -v "$clashctl_bin" >/dev/null 2>&1; then
            echo "[proxy] 启动 Clash: $clashctl_bin on"
            if ! "$clashctl_bin" on; then
                echo "[proxy] clashctl on 未成功；继续检查现有代理端口。" >&2
            fi
        else
            echo "[proxy] 未找到 $clashctl_bin；将仅检查代理端口。"
        fi
    fi

    timeout="${CLASH_START_TIMEOUT:-15}"
    for ((attempt = 0; attempt < timeout; attempt++)); do
        if local_proxy_is_ready "$host" "$port"; then
            echo "[proxy] 本地代理已就绪: $endpoint"
            return 0
        fi
        sleep 1
    done

    echo "[proxy] 本地代理未就绪: $endpoint。请启动 Clash，或将 config.yaml 改为 direct/禁用代理。" >&2
    return 1
}

# 判断步骤是否已完成（比当前步骤更后面的步骤都算已完成）
step_done() {
    local step="$1"
    local state
    state=$(get_step)
    # 步骤顺序: none -> ingest -> digest -> export -> commit -> push -> done
    case "$state" in
        done)  return 0 ;;
        commit) [[ "$step" != "push" ]] ;;
        push)   return 0 ;;
        export) [[ "$step" != "commit" && "$step" != "push" ]] ;;
        digest) [[ "$step" != "export" && "$step" != "commit" && "$step" != "push" ]] ;;
        ingest) [[ "$step" == "ingest" ]] && return 0 || return 1 ;;
        none)   return 1 ;;
        *)      return 1 ;;
    esac
}

# ============================================================
# 步骤函数
# ============================================================

step_ingest() {
    echo ""
    echo "[1/5] 抓取 arXiv 论文并生成中文总结..."
    echo "       (本步骤支持断点续传，已入库且有总结的论文会自动跳过)"
    if [[ -n "$DATE" ]]; then
        uv run python jobs/daily_ingest.py \
            --max-results "$MAX_RESULTS" \
            --date "$DATE" \
            --batch-size "$BATCH_SIZE"
    else
        uv run python jobs/daily_ingest.py \
            --max-results "$MAX_RESULTS" \
            --days-back "$DAYS_BACK" \
            --batch-size "$BATCH_SIZE"
    fi
    if [[ "${SYNC_OS_AGENT_SURVEY:-1}" != "0" ]]; then
        echo ""
        echo "[1b/5] 同步 OS-Agent-Survey 新增 GUI 论文..."
        if [[ -n "${OS_AGENT_SURVEY_MAX_NEW:-}" ]]; then
            if ! uv run python jobs/sync_os_agent_survey.py --max-new "$OS_AGENT_SURVEY_MAX_NEW"; then
                echo "⚠️  OS-Agent-Survey 同步失败，已跳过；主流程继续。"
            fi
        elif ! uv run python jobs/sync_os_agent_survey.py; then
            echo "⚠️  OS-Agent-Survey 同步失败，已跳过；主流程继续。"
        fi
    fi
    maybe_mark_state "ingest"
}

step_digest() {
    echo ""
    echo "[2/5] 生成每日摘要报告..."
    if [[ -n "$DATE" ]]; then
        echo "       (指定日期: $DATE)"
        uv run python jobs/daily_digest.py --published-date "$DATE"
    else
        echo "       (仅今日新增，一句话简介)"
        uv run python jobs/daily_digest.py --today-only
    fi
    maybe_mark_state "digest"
}

step_export() {
    echo ""
    echo "[3/5] 导出论文数据到 docs/papers.json 和 Obsidian vault..."
    uv run python jobs/tag_video_search.py
    uv run python jobs/export_papers.py --cloud
    uv run python jobs/export_gui_taxonomy.py
    uv run python jobs/build_video_search_page.py
    if ! uv run python jobs/export_obsidian_notes.py; then
        echo "⚠️  Obsidian vault 导出失败，已跳过；主流程继续。"
    fi
    maybe_mark_state "export"
}

step_commit() {
    echo ""
    echo "[4/5] 提交 Git 更新..."
    git add docs/papers.json docs/paper-data docs/index.html docs/gui-taxonomy.html \
        docs/video-search.html \
        data/os_agent_survey_papers.json
    local commit_msg
    commit_msg="${COMMIT_MESSAGE:-📚 Update papers $(date +%Y-%m-%d)}"
    git diff --cached --quiet || git commit -m "$commit_msg"
    maybe_mark_state "commit"
}

step_push() {
    local configured_proxy
    echo ""
    echo "[5/5] 推送到 GitHub..."
    configured_proxy="$(get_local_proxy_endpoint)"
    GIT_PUSH_PROXY_URL="${GIT_PUSH_PROXY_URL:-$configured_proxy}" \
        git_push_with_retry origin master
    if [[ "${STATE_ENABLED:-1}" != "0" ]]; then
        rm -f "$STATE_FILE"
    fi
}

sync_public_site() {
    if [[ "${PUBLIC_SYNC_ENABLED:-1}" != "1" ]]; then
        echo "[public-sync] Disabled by PUBLIC_SYNC_ENABLED=${PUBLIC_SYNC_ENABLED}."
        return 0
    fi

    echo ""
    echo "[public-sync] 同步公网论文页面..."
    "$SCRIPT_DIR/sync_public_site.sh"
}

print_skip() {
    echo "[$1] ✅ $1 - 已完成，跳过"
}

step_url_ingest() {
    echo ""
    echo "[1/4] 补录指定论文并生成中文总结..."
    local ingest_args input
    ingest_args=(jobs/ingest_url.py)
    for input in "${URLS[@]}"; do
        if [[ -f "$input" ]]; then
            ingest_args+=(--from-file "$input")
        else
            ingest_args+=("$input")
        fi
    done
    if [[ -n "$SAVE_CATEGORY" ]]; then
        ingest_args+=(--save-category "$SAVE_CATEGORY")
    fi
    uv run python "${ingest_args[@]}"
}

# ============================================================
# 主流程
# ============================================================

RESUME=false
AUTO=false
DATE=""
URLS=()
SAVE_CATEGORY=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --resume|-r)
            RESUME=true
            shift
            ;;
        --date|-d)
            DATE="$2"
            shift 2
            ;;
        --auto|-a)
            AUTO=true
            shift
            ;;
        --url|-u)
            URLS+=("$2")
            shift 2
            ;;
        --gui)
            SAVE_CATEGORY="gui"
            shift
            ;;
        --save-category|-c)
            SAVE_CATEGORY="$2"
            shift 2
            ;;
        *)
            echo "未知参数: $1"
            echo "用法: ./run_daily.sh [--resume] [--date YYYY-MM-DD] [--auto] [--url URL_OR_FILE --gui]"
            exit 1
            ;;
    esac
done

if [[ ${#URLS[@]} -gt 0 ]]; then
    if $AUTO || $RESUME || [[ -n "$DATE" ]]; then
        echo "--url 不能和 --auto、--resume 或 --date 混用"
        exit 1
    fi
    STATE_ENABLED=0
    COMMIT_MESSAGE="${COMMIT_MESSAGE:-📚 Add paper $(date +%Y-%m-%d)}"

    echo ""
    echo "========================================"
    echo "  CV Paper Reading - 单篇补录"
    if [[ -n "$SAVE_CATEGORY" ]]; then
        echo "  保存类别: $SAVE_CATEGORY"
    fi
    echo "  时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "========================================"

    step_url_ingest
    step_export
    step_commit
    step_push
    sync_public_site

    echo ""
    echo "========================================"
    echo "✅ 单篇补录完成！GitHub Pages 稍后自动更新"
    echo "结束时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "========================================"
    exit 0
fi

# ===== --auto 模式：当日已完成则跳过 =====
if $AUTO && ! $RESUME; then
    TODAY="$(date '+%Y-%m-%d')"
    if [[ -f "$DONE_FILE" && "$(cat "$DONE_FILE")" == "$TODAY" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] $(date '+%Y-%m-%d') 已成功运行过，跳过本次调度。"
        exit 0
    fi
fi

# 自动任务在抓取前确保配置中的本地 Clash 代理已启动并可连接。
# 失败时 set -e 会立即退出，因此不会写入 .daily_done，下一次调度仍可重试。
if $AUTO; then
    ensure_local_proxy_ready
fi

# 自动模式下，如果有中断状态则自动续跑
if $AUTO && [[ -f "$STATE_FILE" ]]; then
    if [[ "$(get_step)" == "done" ]]; then
        rm -f "$STATE_FILE"
    else
        RESUME=true
    fi
fi

echo ""
echo "========================================"
echo "  CV Paper Reading - 每日任务"
if [[ -n "$DATE" ]]; then
    echo "  回填日期: $DATE"
fi
echo "  时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"

if $AUTO; then
    echo ""
    echo "🤖 自动模式 - 当日成功运行后后续调度自动跳过"
fi
if $RESUME; then
    echo ""
    echo "🔄 断点续传模式 (run_id=$(get_run_id), step=$(get_step))"
    echo "   已入库的论文不会被重复处理"
elif ! $AUTO; then
    echo ""
    echo "🆕 全新运行（添加 --resume 可从上次中断处继续）"
    rm -f "$STATE_FILE"
fi

# 代理配置现在由 rag 模块从 config.yaml 读取
# run_daily.sh 保持不干预，让 Python 代码自己处理代理逻辑

# --- 步骤 1: ingest ---
step_done "ingest" && print_skip "1/5 ingest" || step_ingest

# --- 步骤 2: digest ---
step_done "digest" && print_skip "2/5 digest" || step_digest

# --- 步骤 3: export ---
step_done "export" && print_skip "3/5 export" || step_export

# --- 步骤 4: commit ---
step_done "commit" && print_skip "4/5 commit" || step_commit

# --- 步骤 5: push ---
step_done "push" && print_skip "5/5 push" || step_push

# --- 公网页面同步 ---
sync_public_site

# 自动模式：标记当日已完成
if $AUTO; then
    date '+%Y-%m-%d' > "$DONE_FILE"
fi

echo ""
echo "========================================"
echo "✅ 全部完成！GitHub Pages 稍后自动更新"
echo "结束时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"
