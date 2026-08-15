#!/bin/bash
# jobs/ingest_yolo.sh - 抓取 YOLO 系列论文并生成中文总结
# 用法: uv run python jobs/ingest_url.py ARXIV_URL [ARXIV_URL...]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

# 强制清除代理（arXiv 直连）
for _k in http_proxy https_proxy HTTP_PROXY HTTPS_PROXY; do
    unset $_k 2>/dev/null || true
done

echo "=========================================="
echo "  YOLO 系列论文抓取"
echo "=========================================="

UV=uv
PYTHON="uv run python"

# YOLO 系列论文 arXiv ID + 备注
declare -A PAPERS=(
    ["1506.02640"]="YOLOv1 - You Only Look Once, Redmon et al. 2015"
    ["1612.08242"]="YOLOv2/YOLO9000 - Better Faster Stronger"
    ["1804.02767"]="YOLOv3 - An Incremental Improvement"
    ["2004.10934"]="YOLOv4 - Optimal Speed & Accuracy"
    ["2209.02976"]="YOLOv6 - 美团工业应用版"
    ["2301.05586"]="YOLOv6 v3.0"
    ["2207.02696"]="YOLOv7 - Trainable bag-of-freebies"
    ["2402.13616"]="YOLOv9 - Programmable Gradient Info"
    ["2405.14458"]="YOLOv10 - End-to-End NMS-free"
    ["2410.17725"]="YOLO11 - Ultralytics 架构解析"
    ["2502.12524"]="YOLOv12 - Attention-Centric"
    ["2506.17733"]="YOLOv13 - Hypergraph-Enhanced"
    ["2509.25164"]="YOLO26 - Key Architectural Enhancements"
    ["2510.09653"]="YOLO26 - Ultralytics Evolution 综述"
    ["2601.12882"]="YOLO26 - NMS-Free End-to-End Analysis"
    ["2602.14582"]="YOLO26 - Comprehensive Architecture Overview"
)

echo ""
echo "准备抓取 ${#PAPERS[@]} 篇 YOLO 系列论文..."
echo ""

URLS=()
for id in "${!PAPERS[@]}"; do
    URLS+=("https://arxiv.org/abs/${id}")
done

# 批量传入
echo "调用 ingest_url.py 处理所有论文..."
$PYTHON jobs/ingest_url.py "${URLS[@]}"
