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

# 빌드 함수: 실패 시 캐시 정리 후 1회 재시도
build_image() {
    local name="$1"; shift
    echo ">>> $name 빌드"
    if ! docker build "$@" 2>&1; then
        echo "!!! $name 빌드 실패 — 캐시 정리 후 재시도"
        docker builder prune -f 2>/dev/null || true
        docker build "$@"
    fi
}

# Backend
build_image "Backend" -t "$TAG/backend:latest" ./backend

# Frontend
build_image "Frontend" -t "$TAG/frontend:latest" ./frontend

# Worker (backend + workers 통합)
build_image "Worker" \
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

# 이미지가 항상 :latest이므로 강제 재시작
echo ""
echo "=== Pod 재시작 (rolling restart) ==="
kubectl -n trading-system rollout restart deployment/backend  2>/dev/null || true
kubectl -n trading-system rollout restart deployment/frontend 2>/dev/null || true

# Kind 배포 시 기존 실패한 CronJob Pod/Job 정리
if [ "$OVERLAY" = "kind" ]; then
    echo ""
    echo "=== 기존 실패 Job 정리 ==="
    kubectl delete jobs -n trading-system --field-selector status.successful=0 --ignore-not-found 2>/dev/null || true
fi

echo ""
echo "=== 배포 상태 확인 ==="
kubectl -n trading-system rollout status deployment/backend  --timeout=120s
kubectl -n trading-system rollout status deployment/frontend --timeout=120s

echo ""
if [ "$OVERLAY" = "kind" ]; then
    # TLS Secret 존재 여부 확인
    if kubectl get secret tls-secret -n trading-system &>/dev/null; then
        echo "=== 완료. https://trading.local 에서 확인하세요 ==="
    else
        echo "=== 완료. http://trading.local 에서 확인하세요 ==="
        echo "    HTTPS 활성화: ./scripts/gen-tls-cert.sh && kubectl apply -k k8s/overlays/kind"
    fi
else
    echo "=== 완료. http://trading.local 에서 확인하세요 ==="
fi
