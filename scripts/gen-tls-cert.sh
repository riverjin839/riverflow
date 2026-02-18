#!/bin/bash
set -euo pipefail

# Self-signed TLS 인증서 생성 + K8s Secret 등록
# 사용법: ./scripts/gen-tls-cert.sh [도메인] [네임스페이스]

DOMAIN="${1:-trading.local}"
NAMESPACE="${2:-trading-system}"
SECRET_NAME="tls-secret"
CERT_DIR="/tmp/riverflow-tls"

mkdir -p "$CERT_DIR"

echo "=== Self-signed TLS 인증서 생성: $DOMAIN ==="

openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout "$CERT_DIR/tls.key" \
  -out "$CERT_DIR/tls.crt" \
  -subj "/CN=$DOMAIN/O=Riverflow" \
  -addext "subjectAltName=DNS:$DOMAIN,DNS:*.$DOMAIN"

echo "인증서 생성 완료: $CERT_DIR/tls.crt, $CERT_DIR/tls.key"

echo ""
echo "=== K8s TLS Secret 생성: $SECRET_NAME ==="

# 기존 Secret 삭제 (있으면)
kubectl delete secret "$SECRET_NAME" -n "$NAMESPACE" --ignore-not-found

kubectl create secret tls "$SECRET_NAME" \
  -n "$NAMESPACE" \
  --cert="$CERT_DIR/tls.crt" \
  --key="$CERT_DIR/tls.key"

echo "TLS Secret '$SECRET_NAME' 생성 완료 (namespace: $NAMESPACE)"

echo ""
echo "=== macOS에서 인증서 신뢰 등록 (선택) ==="
echo "sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain $CERT_DIR/tls.crt"
echo ""
echo "=== Linux에서 인증서 신뢰 등록 (선택) ==="
echo "sudo cp $CERT_DIR/tls.crt /usr/local/share/ca-certificates/$DOMAIN.crt && sudo update-ca-certificates"
