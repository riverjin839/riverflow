.PHONY: setup deploy build backup clean dev setup-kind deploy-kind clean-kind

# =============================================
# k3d 환경 (기본)
# =============================================

# K3d 클러스터 생성
setup:
	chmod +x scripts/*.sh
	./scripts/setup-k3d.sh

# k3d 빌드 + 배포
deploy:
	./scripts/deploy.sh local

# 빌드만 (k3d 레지스트리용)
build:
	./scripts/deploy.sh build-only

# k3d 클러스터 삭제
clean:
	k3d cluster delete trading

# =============================================
# Kind 환경 (Mac Mini 등)
# =============================================

# Kind 클러스터 생성 (NGINX Ingress 포함)
setup-kind:
	chmod +x scripts/*.sh
	./scripts/setup-kind.sh

# Kind 빌드 + 배포
deploy-kind:
	./scripts/deploy.sh kind

# Kind 클러스터 삭제
clean-kind:
	kind delete cluster --name trading

# =============================================
# 공통
# =============================================

# DB 백업
backup:
	./scripts/backup-db.sh

# 로컬 개발 (Docker 없이)
dev:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
