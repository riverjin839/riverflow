#!/bin/bash
set -euo pipefail

# 빌드 및 배포 스크립트
# 사용법: ./scripts/deploy.sh [local|build-only]

REGISTRY="k3d-trading-registry:5111"
OVERLAY="${1:-local}"

echo "=== Docker 이미지 빌드 ==="

# Backend
echo ">>> Backend 빌드"
docker build -t "$REGISTRY/trading-system/backend:latest" ./backend

# Frontend
echo ">>> Frontend 빌드"
docker build -t "$REGISTRY/trading-system/frontend:latest" ./frontend

# Worker (backend + workers 통합)
echo ">>> Worker 빌드"
docker build \
    -t "$REGISTRY/trading-system/worker:latest" \
    -f backend/Dockerfile.worker \
    --build-context workers=./workers \
    ./backend

echo ""
echo "=== 이미지 푸시 (로컬 레지스트리) ==="
docker push "$REGISTRY/trading-system/backend:latest"
docker push "$REGISTRY/trading-system/frontend:latest"
docker push "$REGISTRY/trading-system/worker:latest"

if [ "$OVERLAY" = "build-only" ]; then
    echo "빌드만 완료. 배포 스킵."
    exit 0
fi

echo ""
echo "=== Kustomize 배포 ($OVERLAY) ==="
kubectl apply -k "k8s/overlays/$OVERLAY"

echo ""
echo "=== 배포 상태 확인 ==="
kubectl -n trading-system rollout status deployment/backend --timeout=120s
kubectl -n trading-system rollout status deployment/postgres --timeout=120s

echo ""
echo "=== 완료. http://trading.local 에서 확인하세요 ==="
