#!/bin/bash
set -euo pipefail

# 빌드 및 배포 스크립트
# 사용법: ./scripts/deploy.sh [local|kind|build-only]
#
# - local      : k3d 환경 (로컬 레지스트리에 push)
# - kind       : Kind 환경 (kind load docker-image 사용)
# - build-only : Docker 이미지 빌드만 수행

OVERLAY="${1:-local}"
K3D_REGISTRY="k3d-trading-registry:5111"
IMAGE_PREFIX="trading-system"

# 이미지 태그 결정
if [ "$OVERLAY" = "local" ]; then
    TAG="$K3D_REGISTRY/$IMAGE_PREFIX"
else
    TAG="$IMAGE_PREFIX"
fi

echo "=== Docker 이미지 빌드 (target: $OVERLAY) ==="

# Backend
echo ">>> Backend 빌드"
docker build -t "$TAG/backend:latest" ./backend

# Frontend
echo ">>> Frontend 빌드"
docker build -t "$TAG/frontend:latest" ./frontend

# Worker (backend + workers 통합)
echo ">>> Worker 빌드"
docker build \
    -t "$TAG/worker:latest" \
    -f backend/Dockerfile.worker \
    --build-context workers=./workers \
    ./backend

if [ "$OVERLAY" = "build-only" ]; then
    echo "빌드만 완료. 배포 스킵."
    exit 0
fi

echo ""
if [ "$OVERLAY" = "local" ]; then
    echo "=== 이미지 푸시 (k3d 로컬 레지스트리) ==="
    docker push "$TAG/backend:latest"
    docker push "$TAG/frontend:latest"
    docker push "$TAG/worker:latest"

elif [ "$OVERLAY" = "kind" ]; then
    echo "=== 이미지 로드 (Kind 클러스터) ==="
    kind load docker-image "$TAG/backend:latest"  --name trading
    kind load docker-image "$TAG/frontend:latest" --name trading
    kind load docker-image "$TAG/worker:latest"   --name trading
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
