#!/bin/bash
set -euo pipefail

# PostgreSQL 백업 스크립트
# K8s Pod 내부에서 pg_dump 실행 후 로컬로 복사

NAMESPACE="trading-system"
BACKUP_DIR="./backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="trading_backup_${TIMESTAMP}.sql"

mkdir -p "$BACKUP_DIR"

echo "=== PostgreSQL 백업 시작 ==="

# PostgreSQL Pod 이름 조회
POD=$(kubectl -n "$NAMESPACE" get pods -l app=postgres -o jsonpath='{.items[0].metadata.name}')
echo "Pod: $POD"

# pg_dump 실행 후 로컬로 복사
kubectl -n "$NAMESPACE" exec "$POD" -- \
    pg_dump -U trading -d trading --no-owner --no-acl \
    > "$BACKUP_DIR/$BACKUP_FILE"

echo "백업 완료: $BACKUP_DIR/$BACKUP_FILE"
echo "크기: $(du -h "$BACKUP_DIR/$BACKUP_FILE" | cut -f1)"
