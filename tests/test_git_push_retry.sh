#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=../scripts/git_push_with_retry.sh
source "$REPO_ROOT/scripts/git_push_with_retry.sh"

test_eventual_success() (
    local attempts=0
    local delays=""
    local observed_transports=""
    git_push_transport() {
        observed_transports="${observed_transports} $1"
        attempts=$((attempts + 1))
        ((attempts >= 4))
    }
    sleep() { delays="${delays} $1"; }

    GIT_PUSH_PROXY_URL=http://127.0.0.1:7890 \
        GIT_PUSH_MAX_ATTEMPTS=6 \
        GIT_PUSH_INITIAL_DELAY_SECONDS=2 \
        GIT_PUSH_MAX_DELAY_SECONDS=8 \
        git_push_with_retry origin HEAD

    [[ "$attempts" == "4" ]]
    [[ "$delays" == " 2 4 8" ]]
    [[ "$observed_transports" == " default direct-http1 proxy-http1 default" ]]
)

test_persistent_failure() (
    local attempts=0
    local delays=""
    local observed_transports=""
    git_push_transport() {
        observed_transports="${observed_transports} $1"
        attempts=$((attempts + 1))
        return 7
    }
    sleep() { delays="${delays} $1"; }

    if GIT_PUSH_MAX_ATTEMPTS=3 \
        GIT_PUSH_INITIAL_DELAY_SECONDS=1 \
        GIT_PUSH_MAX_DELAY_SECONDS=2 \
        git_push_with_retry origin master; then
        echo "expected persistent push failure" >&2
        return 1
    fi

    [[ "$attempts" == "3" ]]
    [[ "$delays" == " 1 2" ]]
    [[ "$observed_transports" == " default direct-http1 default" ]]
)

test_proxy_config() (
    local proxy
    proxy="$(git_push_proxy_from_config "$REPO_ROOT/config.yaml")"
    [[ "$proxy" == "http://127.0.0.1:7890" ]]
)

test_eventual_success
test_persistent_failure
test_proxy_config
echo "git push retry tests: OK"
