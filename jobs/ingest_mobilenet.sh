#!/bin/bash
# jobs/ingest_mobilenet.sh - 抓取 MobileNet 系列论文并生成中文总结
# 用法: bash jobs/ingest_mobilenet.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

# 强制清除代理（arXiv 直连）
for _k in http_proxy https_proxy HTTP_PROXY HTTPS_PROXY; do
    unset $_k 2>/dev/null || true
done

echo "=========================================="
echo "  MobileNet 系列论文抓取"
echo "=========================================="

PYTHON="uv run python"

# MobileNet 系列论文 arXiv ID + 备注
declare -A PAPERS=(
    ["1704.04861"]="MobileNetv1 - Efficient Convolutional Neural Networks, Howard et al. 2017"
    ["1801.04381"]="MobileNetv2 - Inverted Residuals and Linear Bottlenecks, Sandler et al. 2018"
    ["1905.02244"]="MobileNetv3 - Searching for MobileNetV3, Howard et al. 2019"
    ["2404.10518"]="MobileNetv4 - Universal Models for the Mobile Ecosystem, Qin et al. 2024"
)

echo ""
echo "准备抓取 ${#PAPERS[@]} 篇 MobileNet 系列论文..."
echo ""

URLS=()
for id in "${!PAPERS[@]}"; do
    URLS+=("https://arxiv.org/abs/${id}")
done

echo "调用 ingest_url.py 处理所有论文..."
$PYTHON jobs/ingest_url.py "${URLS[@]}"
