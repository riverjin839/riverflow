#!/bin/bash
set -euo pipefail

# K3d 클러스터 생성 스크립트
# Traefik Ingress + 로컬 레지스트리 포함

CLUSTER_NAME="trading"
REGISTRY_NAME="trading-registry"
REGISTRY_PORT=5111

echo "=== K3d 클러스터 생성: $CLUSTER_NAME ==="

# 기존 클러스터가 있으면 경고
if k3d cluster list | grep -q "$CLUSTER_NAME"; then
    echo "경고: 클러스터 '$CLUSTER_NAME'가 이미 존재합니다."
    echo "삭제하려면: k3d cluster delete $CLUSTER_NAME"
    exit 1
fi

# 로컬 레지스트리 생성
k3d registry create "$REGISTRY_NAME" --port "$REGISTRY_PORT" 2>/dev/null || true

# 클러스터 생성
k3d cluster create "$CLUSTER_NAME" \
    --servers 1 \
    --agents 2 \
    --port "80:80@loadbalancer" \
    --port "443:443@loadbalancer" \
    --registry-use "k3d-$REGISTRY_NAME:$REGISTRY_PORT" \
    --k3s-arg "--disable=metrics-server@server:0"

echo ""
echo "=== 클러스터 생성 완료 ==="
echo "kubectl cluster-info"
kubectl cluster-info

echo ""
echo "=== /etc/hosts 에 다음을 추가하세요 ==="
echo "127.0.0.1  trading.local"
