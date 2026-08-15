#!/usr/bin/env bash
# Shared Git push retry helper for scheduled publishing scripts.

git_push_proxy_from_config() {
    local config_path="$1"
    [[ -f "$config_path" ]] || return 0

    awk '
        /^[[:space:]]*proxy:[[:space:]]*(#.*)?$/ { in_proxy = 1; next }
        in_proxy && /^[^[:space:]#]/ { in_proxy = 0 }
        !in_proxy { next }
        /^[[:space:]]*enabled:[[:space:]]*/ {
            value = $0
            sub(/^[[:space:]]*enabled:[[:space:]]*/, "", value)
            sub(/[[:space:]]*#.*/, "", value)
            gsub(/[[:space:]"\047]/, "", value)
            enabled = value
        }
        /^[[:space:]]*mode:[[:space:]]*/ {
            value = $0
            sub(/^[[:space:]]*mode:[[:space:]]*/, "", value)
            sub(/[[:space:]]*#.*/, "", value)
            gsub(/[[:space:]"\047]/, "", value)
            mode = value
        }
        /^[[:space:]]*single_proxy:[[:space:]]*/ {
            value = $0
            sub(/^[[:space:]]*single_proxy:[[:space:]]*/, "", value)
            sub(/[[:space:]]*#.*/, "", value)
            gsub(/[[:space:]"\047]/, "", value)
            proxy = value
        }
        END {
            if (enabled == "true" && mode != "direct" && proxy ~ /^https?:\/\/(127\.0\.0\.1|localhost):[0-9]+\/?$/) {
                print proxy
            }
        }
    ' "$config_path"
}

git_push_transport() {
    local transport="$1"
    shift

    case "$transport" in
        default)
            git push "$@"
            ;;
        direct-http1)
            env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
                -u http_proxy -u https_proxy -u all_proxy \
                git -c http.proxy= -c http.version=HTTP/1.1 push "$@"
            ;;
        proxy-http1)
            git -c "http.proxy=${GIT_PUSH_PROXY_URL}" \
                -c http.version=HTTP/1.1 push "$@"
            ;;
        *)
            echo "git_push_transport: unknown transport: $transport" >&2
            return 2
            ;;
    esac
}

git_push_with_retry() {
    if [[ "$#" -lt 1 ]]; then
        echo "git_push_with_retry: missing git push arguments" >&2
        return 2
    fi

    local max_attempts="${GIT_PUSH_MAX_ATTEMPTS:-6}"
    local delay_seconds="${GIT_PUSH_INITIAL_DELAY_SECONDS:-10}"
    local max_delay_seconds="${GIT_PUSH_MAX_DELAY_SECONDS:-60}"

    case "$max_attempts:$delay_seconds:$max_delay_seconds" in
        *[!0-9:]*|:*|*::*|*:)
            echo "git_push_with_retry: retry settings must be non-negative integers" >&2
            return 2
            ;;
    esac
    if ((max_attempts < 1)); then
        echo "git_push_with_retry: GIT_PUSH_MAX_ATTEMPTS must be at least 1" >&2
        return 2
    fi

    local transports=(default direct-http1)
    if [[ -n "${GIT_PUSH_PROXY_URL:-}" ]]; then
        transports+=(proxy-http1)
    fi

    local attempt=1
    local push_status=0
    local transport=""
    local transport_index=0
    while ((attempt <= max_attempts)); do
        transport_index=$(((attempt - 1) % ${#transports[@]}))
        transport="${transports[$transport_index]}"
        echo "[git-push] Attempt ${attempt}/${max_attempts} via ${transport}: git push $*"
        if git_push_transport "$transport" "$@"; then
            echo "[git-push] Push succeeded."
            return 0
        else
            push_status=$?
        fi

        if ((attempt == max_attempts)); then
            echo "[git-push] Push failed after ${max_attempts} attempts." >&2
            return "$push_status"
        fi

        echo "[git-push] Push failed (exit ${push_status}); retrying in ${delay_seconds}s..." >&2
        sleep "$delay_seconds"
        delay_seconds=$((delay_seconds * 2))
        if ((delay_seconds > max_delay_seconds)); then
            delay_seconds="$max_delay_seconds"
        fi
        attempt=$((attempt + 1))
    done
}
