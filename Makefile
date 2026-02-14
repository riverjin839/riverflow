.PHONY: setup deploy build backup clean dev

# K3d 클러스터 생성
setup:
	chmod +x scripts/*.sh
	./scripts/setup-k3d.sh

# 빌드 + 배포
deploy:
	./scripts/deploy.sh local

# 빌드만
build:
	./scripts/deploy.sh build-only

# DB 백업
backup:
	./scripts/backup-db.sh

# 로컬 개발 (Docker 없이)
dev:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 클러스터 삭제
clean:
	k3d cluster delete trading
