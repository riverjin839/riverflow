# Riverflow - K8s 기반 한국 증시 자동매매 시스템

## 프로젝트 구조

```
backend/         Python FastAPI 백엔드 (app/, Dockerfile, Dockerfile.worker)
frontend/        Next.js 15 TypeScript 프론트엔드
workers/         독립 실행 워커 스크립트 (K8s CronJob/Deployment)
kiwoom-bridge/   키움증권 Windows 브릿지 서버 (별도 머신)
k8s/             Kubernetes 매니페스트 (Kustomize: base + overlays/local)
scripts/         셸 스크립트 (setup-k3d, deploy, backup-db)
```

## 기술 스택

- **Backend**: Python 3.12, FastAPI, SQLAlchemy (async), asyncpg
- **Frontend**: Next.js 15, React 19, TypeScript 5
- **DB**: PostgreSQL 16 + pgvector (벡터 유사도 검색)
- **LLM**: Ollama (llama3 생성, bge-m3 임베딩)
- **Broker**: 한국투자증권(KIS) REST/WebSocket API
- **Infra**: k3d (K3s), Kustomize, Docker, Traefik Ingress

## 빌드 및 실행

```bash
# 로컬 개발 (Docker 없이)
make dev                    # uvicorn으로 백엔드만 실행

# k3d 클러스터 셋업
make setup                  # k3d 클러스터 + 레지스트리 생성

# Docker 빌드 + K8s 배포
make deploy                 # 빌드 -> 레지스트리 푸시 -> kubectl apply
make build                  # 빌드만

# 워커 이미지 빌드 (build-context 사용)
docker build -t worker -f backend/Dockerfile.worker --build-context workers=./workers ./backend
```

## 주요 코드 경로

| 용도 | 경로 |
|------|------|
| FastAPI 앱 진입점 | `backend/app/main.py` |
| API 라우터 | `backend/app/routers/*.py` |
| ORM 모델 | `backend/app/models/*.py` |
| 서비스 레이어 | `backend/app/services/*.py` |
| 증권사 추상화 | `backend/app/services/broker/base.py` |
| KIS API 구현 | `backend/app/services/broker/kis_broker.py` |
| 자동매매 엔진 | `backend/app/services/auto_trader.py` |
| DB 스키마 | `k8s/base/postgres/init-scripts/01-schema.sql` |
| 설정 | `backend/app/core/config.py`, `broker_config.py` |

## 아키텍처 핵심 포인트

- **인증**: JWT 기반 "스텔스 로그인" (비밀번호 또는 키 시퀀스)
- **증권사 추상화**: `BaseBroker` ABC를 KIS/키움이 구현. 모의투자가 기본값
- **자동매매 안전장치**: 일일 주문횟수/금액 한도, 최대 보유종목수, 손절/익절, 시간제한
- **벡터 검색**: 뉴스/문서를 bge-m3로 임베딩 후 pgvector HNSW 인덱스로 유사도 검색
- **워커 패턴**: 각 워커는 `backend.app` 모듈을 import하여 서비스/모델 공유

## 코드 컨벤션

- Python: 타입 힌트 사용 (`list[str]`, `dict | None`), async/await 기반
- SQL: SQLAlchemy ORM + `text()` 로우쿼리 혼용
- API: `/api/` prefix, Pydantic 모델로 request/response 정의
- 한국어 주석/docstring 사용

## 환경변수

`.env.example` 참조. 주요 변수:
- `DATABASE_URL`: PostgreSQL 연결 문자열
- `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_ACCOUNT_NO`: 한투 API 키
- `KIS_IS_VIRTUAL`: 모의투자 여부 (기본 true)
- `OLLAMA_BASE_URL`: Ollama 서버 주소
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`: 알림용
- `JWT_SECRET_KEY`, `STEALTH_PASSWORD`: 인증용

## DB 마이그레이션

현재 Alembic 미사용. `k8s/base/postgres/init-scripts/01-schema.sql`이 PostgreSQL 컨테이너 초기 기동 시 실행됨. 스키마 변경 시 해당 SQL 파일 수정 후 DB 재생성 필요.

## 테스트

`backend/tests/` 디렉토리 존재하나 아직 테스트 미작성.
```bash
cd backend && python -m pytest tests/
```
