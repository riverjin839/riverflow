#!/bin/bash
set -euo pipefail

# Kind 클러스터 생성 스크립트
# Mac Mini 등 로컬 환경에서 Kind로 실행할 때 사용
# Kind는 docker push 대신 kind load docker-image 명령으로 이미지를 로드한다.

CLUSTER_NAME="trading"

echo "=== Kind 클러스터 생성: $CLUSTER_NAME ==="

# 기존 클러스터가 있으면 경고
if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    echo "경고: 클러스터 '$CLUSTER_NAME'가 이미 존재합니다."
    echo "삭제하려면: kind delete cluster --name $CLUSTER_NAME"
    exit 1
fi

# Kind 클러스터 설정 파일 생성
cat <<'KINDCONFIG' | kind create cluster --name "$CLUSTER_NAME" --config -
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    kubeadmConfigPatches:
      - |
        kind: InitConfiguration
        nodeRegistration:
          kubeletExtraArgs:
            node-labels: "ingress-ready=true"
    extraPortMappings:
      - containerPort: 80
        hostPort: 80
        protocol: TCP
      - containerPort: 443
        hostPort: 443
        protocol: TCP
  - role: worker
  - role: worker
KINDCONFIG

echo ""
echo "=== NGINX Ingress Controller 설치 ==="
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml

echo ""
echo "=== Ingress Controller 준비 대기 ==="
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=120s

echo ""
echo "=== 클러스터 생성 완료 ==="
kubectl cluster-info --context "kind-$CLUSTER_NAME"

echo ""
echo "=== /etc/hosts 에 다음을 추가하세요 ==="
echo "127.0.0.1  trading.local"
