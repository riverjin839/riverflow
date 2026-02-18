# Riverflow

K8s 기반 한국 증시 자동매매 시스템.

KIS(한국투자증권) API를 연동하여 조건 검색, 자동매매, 손절/익절, 뉴스 분석, LLM 브리핑을 자동화한다.
로컬 Kubernetes(k3d 또는 Kind) 위에서 운영하며, 모의투자가 기본값이다.

## 아키텍처

```
┌──────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                         │
│                  (k3d 또는 Kind)                              │
│                                                              │
│  ┌──────────┐  ┌───────────┐  ┌───────────────────────────┐ │
│  │ Frontend │  │  Backend   │  │      Workers (CronJob)    │ │
│  │ Next.js  │──│  FastAPI   │  │                           │ │
│  │ :3000    │  │  :8000     │  │  condition_scanner  */5m  │ │
│  └──────────┘  └─────┬─────┘  │  stop_loss_checker  */1m  │ │
│                      │        │  morning_briefing   08:30  │ │
│                      │        │  daily_review       16:00  │ │
│                      │        │  news_crawler       */2h   │ │
│                      │        └───────────┬───────────────┘ │
│                      │                    │                  │
│              ┌───────▼────────┐          │                  │
│              │   PostgreSQL   │◄─────────┘                  │
│              │   + pgvector   │                              │
│              └────────────────┘                              │
│                                                              │
│  ┌────────────────────┐                                      │
│  │  realtime_feed     │  (Deployment, 상시 실행)              │
│  │  KIS WebSocket     │                                      │
│  └────────────────────┘                                      │
└──────────────────────────────────────────────────────────────┘
         │                    │                    │
    ┌────▼────┐       ┌──────▼──────┐     ┌──────▼──────┐
    │  Ollama  │       │  KIS API    │     │  Telegram   │
    │  LLM     │       │  REST/WS    │     │  Bot API    │
    └──────────┘       └─────────────┘     └─────────────┘
```

### 컴포넌트 요약

| 컴포넌트 | 역할 | 기술 |
|----------|------|------|
| **Backend** | REST API 서버. 인증, CRUD, 브로커 연동, AI 피드백 | Python 3.12, FastAPI, SQLAlchemy async |
| **Frontend** | 대시보드, 매매일지 UI | Next.js 15, React 19, TypeScript |
| **PostgreSQL** | 매매일지, 뉴스, 조건식, 주문 이력 저장 + 벡터 검색 | PostgreSQL 16 + pgvector |
| **Workers** | 장중 자동 스캔, 손절 체크, 브리핑 생성, 뉴스 크롤링 | Python (K8s CronJob/Deployment) |
| **Ollama** | LLM 추론 (llama3) + 텍스트 임베딩 (bge-m3) | 호스트 머신에서 실행 |
| **KIS API** | 잔고 조회, 현재가, 주문 실행, 실시간 시세 | REST + WebSocket |

## 사전 요구사항

- **Docker Desktop** (Mac/Windows) 또는 Docker Engine (Linux)
- **kubectl** (`brew install kubectl`)
- **Kubernetes 런타임** (아래 중 택 1):
  - [k3d](https://k3d.io) — k3s 기반, Traefik 내장 (`brew install k3d`)
  - [Kind](https://kind.sigs.k8s.io) — Docker-in-Docker 방식 (`brew install kind`)
- **Ollama** — 로컬 LLM 서버 (`brew install ollama`)
- **KIS API 키** — [한국투자증권 Open API](https://apiportal.koreainvestment.com) 에서 발급

```bash
# Ollama 모델 다운로드
ollama pull llama3
ollama pull bge-m3
```

## 빠른 시작

### Option A: k3d (기본)

```bash
# 1. 클러스터 생성
make setup

# 2. 시크릿 생성 (아래 "시크릿 설정" 섹션 참조)
kubectl apply -f k8s/base/secrets/kis-credentials.yaml

# 3. 빌드 + 배포
make deploy

# 4. /etc/hosts 추가
echo "127.0.0.1 trading.local" | sudo tee -a /etc/hosts

# 5. 접속
open http://trading.local
```

### Option B: Kind (Mac Mini 등)

```bash
# 1. 클러스터 생성 (NGINX Ingress 자동 설치)
make setup-kind

# 2. 시크릿 생성
kubectl apply -f k8s/base/secrets/kis-credentials.yaml

# 3. HTTPS 인증서 생성 (선택, 권장)
./scripts/gen-tls-cert.sh

# 4. 빌드 + 배포
make deploy-kind

# 5. /etc/hosts 추가
echo "127.0.0.1 trading.local" | sudo tee -a /etc/hosts

# 6. 접속
open https://trading.local
```

### k3d vs Kind 비교

| | k3d | Kind |
|---|---|---|
| 기반 | k3s (경량 K8s) | Docker-in-Docker |
| Ingress | Traefik 내장 | NGINX Ingress 별도 설치 |
| 이미지 로딩 | 로컬 레지스트리 (`docker push`) | `kind load docker-image` |
| 호스트 접근 | `host.k3d.internal` | `host.docker.internal` |
| 리소스 사용량 | 상대적으로 가벼움 | Docker 위에 Docker라 약간 무거움 |
| macOS 호환성 | Docker Desktop 필요 | Docker Desktop 필요 |
| 장점 | 프로덕션 K3s와 동일 환경 | 설정 단순, CNCF 공식 도구 |

## 접속 설정 (로컬 + 외부)

### 로컬 접속 (같은 머신)

K8s Ingress를 통해 `trading.local` 도메인으로 접속한다.

```bash
# /etc/hosts 에 추가
echo "127.0.0.1 trading.local" | sudo tee -a /etc/hosts

# 접속 확인
curl http://trading.local/api/health
open http://trading.local               # 프론트엔드
open http://trading.local/api/docs      # Swagger UI
```

### 외부 접속 (같은 네트워크 내 다른 기기)

같은 LAN에 있는 다른 PC/모바일에서 맥미니(또는 서버)의 트레이딩 시스템에 접속하려면 아래 설정이 필요하다.

#### 1단계: 서버 머신의 LAN IP 확인

```bash
# macOS
ipconfig getifaddr en0      # Wi-Fi
ipconfig getifaddr en1      # Ethernet

# Linux
hostname -I | awk '{print $1}'
```

예시: `192.168.0.100`

#### 2단계: Kind/k3d 포트 포워딩

**Kind 환경**에서는 Ingress Controller가 호스트 80/443 포트에 바인딩되어 있으므로 추가 설정 없이 접속 가능하다.
만약 80 포트가 사용 중이라면 `kubectl port-forward`를 사용한다:

```bash
# Kind: NGINX Ingress가 이미 hostPort 80/443을 사용 (setup-kind.sh에서 설정)
# → 추가 포트 포워딩 불필요

# k3d: Traefik이 기본적으로 호스트 80:80으로 매핑됨
# → 추가 포트 포워딩 불필요

# 포트가 사용중이거나 직접 포워딩이 필요한 경우:
kubectl port-forward -n trading-system svc/backend 8000:8000 --address=0.0.0.0 &
kubectl port-forward -n trading-system svc/frontend 3000:3000 --address=0.0.0.0 &
```

#### 3단계: 접속 기기에서 hosts 설정

접속하려는 기기(PC/Mac)의 `/etc/hosts`에 서버 IP를 등록한다:

```bash
# 접속하는 기기에서 실행 (서버 IP에 맞게 수정)
echo "192.168.0.100 trading.local" | sudo tee -a /etc/hosts
```

**모바일(iOS/Android)**: hosts 파일 수정이 어려우므로 IP로 직접 접속하거나 아래 방법 사용.

#### 4단계: IP 직접 접속 (hosts 수정 없이)

Ingress는 Host 헤더 기반으로 라우팅하므로, IP로 직접 접속하려면 curl에 Host 헤더를 추가하거나 `kubectl port-forward`를 사용한다:

```bash
# 방법 A: Host 헤더 지정
curl -H "Host: trading.local" http://192.168.0.100/api/health

# 방법 B: port-forward (Ingress 우회, 서비스에 직접 접속)
# 서버 머신에서 실행 (--address=0.0.0.0 으로 외부 접근 허용)
kubectl port-forward -n trading-system svc/backend 8000:8000 --address=0.0.0.0 &
kubectl port-forward -n trading-system svc/frontend 3000:3000 --address=0.0.0.0 &

# 다른 기기에서 접속
open http://192.168.0.100:3000    # 프론트엔드
open http://192.168.0.100:8000/api/docs  # API 문서
```

#### 5단계 (선택): macOS 방화벽 허용

macOS 방화벽이 활성화되어 있으면 외부 접속이 차단될 수 있다:

```bash
# 방화벽 상태 확인
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate

# 필요 시 Docker 허용 (시스템 설정 > 개인정보 보호 및 보안 > 방화벽에서 설정)
```

### 접속 요약

| 접속 위치 | URL | 비고 |
|-----------|-----|------|
| 로컬 HTTPS (Kind) | `https://trading.local` | TLS 인증서 설정 시 |
| 로컬 HTTP | `http://trading.local` | /etc/hosts 설정 필요 |
| 로컬 API 문서 | `https://trading.local/api/docs` | Swagger UI |
| 외부 (hosts 등록) | `https://trading.local` | 접속 기기 hosts에 서버IP 등록 |
| 외부 (port-forward) | `http://<서버IP>:3000` | `--address=0.0.0.0` 필요 |
| 외부 API (port-forward) | `http://<서버IP>:8000/api/docs` | `--address=0.0.0.0` 필요 |

## HTTPS 설정 (Kind 환경)

Kind 환경에서 self-signed TLS 인증서로 HTTPS를 활성화할 수 있다.

### 빠른 설정

```bash
# 인증서 생성 + K8s TLS Secret 등록 (한 줄로 완료)
./scripts/gen-tls-cert.sh

# Ingress 재적용 (TLS 설정 반영)
kubectl apply -k k8s/overlays/kind
```

이후 `https://trading.local` 로 접속한다. HTTP 요청은 자동으로 HTTPS로 리다이렉트된다.

### 브라우저 인증서 경고 해결

Self-signed 인증서이므로 브라우저에서 보안 경고가 뜬다. 아래 방법으로 신뢰 등록하면 경고가 사라진다.

**macOS:**
```bash
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain /tmp/riverflow-tls/tls.crt
```

**Linux (Ubuntu/Debian):**
```bash
sudo cp /tmp/riverflow-tls/tls.crt /usr/local/share/ca-certificates/trading-local.crt
sudo update-ca-certificates
```

**Chrome/Edge:** `chrome://flags/#allow-insecure-localhost` 를 Enabled 로 설정하면 `localhost`/로컬 도메인의 self-signed 인증서 경고를 무시할 수 있다.

### 커스텀 도메인

기본 도메인은 `trading.local`이다. 변경하려면:

```bash
# 1. 다른 도메인으로 인증서 생성
./scripts/gen-tls-cert.sh my-trading.local

# 2. Ingress의 host 값 수정
#    k8s/overlays/kind/patches/ingress-nginx.yaml 에서 trading.local → my-trading.local

# 3. /etc/hosts 업데이트
echo "127.0.0.1 my-trading.local" | sudo tee -a /etc/hosts
```

### 구조

```
Client (브라우저)
  │ HTTPS (port 443)
  ▼
NGINX Ingress Controller ──── TLS 종료 (tls-secret)
  │ HTTP
  ├──→ /api/*  → backend:8000
  └──→ /*      → frontend:3000
```

> **k3d 환경**: k3d는 Traefik을 사용하며, TLS 설정 방식이 다르다. k3d에서 HTTPS가 필요하면 Traefik의 `IngressRoute` CRD + `TLSStore`를 사용해야 한다.

## 시크릿 설정

K8s 배포 전에 시크릿을 생성해야 한다.

```bash
# k8s/base/secrets/kis-credentials.yaml (Git에 올리지 않는다)
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Secret
metadata:
  name: kis-credentials
  namespace: trading-system
type: Opaque
stringData:
  KIS_APP_KEY: "발급받은-앱키"
  KIS_APP_SECRET: "발급받은-앱시크릿"
  KIS_ACCOUNT_NO: "00000000-01"
  KIS_HTS_ID: "HTS-아이디"
  KIS_IS_VIRTUAL: "true"
---
apiVersion: v1
kind: Secret
metadata:
  name: trading-db-creds
  namespace: trading-system
type: Opaque
stringData:
  POSTGRES_PASSWORD: "your-secure-password"
EOF
```

> `trading-system` 네임스페이스가 없으면 먼저 `kubectl create namespace trading-system` 실행.

## 로컬 개발 (Docker 없이)

K8s 없이 백엔드만 빠르게 실행할 수 있다.

```bash
# 1. 환경변수 설정
cp .env.example .env.local

# 2. Python 의존성 설치
cd backend && pip install -r requirements.txt

# 3. 실행
make dev
# → http://localhost:8000/docs 에서 Swagger UI 확인
```

## 프로젝트 구조

```
riverflow/
├── backend/                    # FastAPI 백엔드
│   ├── app/
│   │   ├── main.py             # 앱 진입점, 라우터 등록
│   │   ├── core/               # 설정, DB, 인증
│   │   ├── models/             # SQLAlchemy ORM 모델
│   │   ├── routers/            # API 엔드포인트
│   │   └── services/           # 비즈니스 로직
│   │       └── broker/         # 증권사 추상화 (KIS, 키움)
│   ├── Dockerfile              # API 서버 이미지
│   └── Dockerfile.worker       # 워커 이미지
├── frontend/                   # Next.js 프론트엔드
│   ├── src/app/                # 페이지 (/login, /dashboard, /market, /journal)
│   └── Dockerfile
├── workers/                    # K8s CronJob/Deployment 워커
│   ├── condition_scanner.py    # 조건검색 스캔 (장중 5분마다)
│   ├── stop_loss_checker.py    # 손절/익절 체크 (장중 1분마다)
│   ├── realtime_feed.py        # KIS WebSocket 실시간 시세
│   ├── morning_briefing.py     # 장전 시황 브리핑 (08:30 KST)
│   ├── daily_review.py         # 장후 리뷰 (16:00 KST)
│   └── news_crawler.py         # 뉴스 크롤링 + 임베딩 (2시간마다)
├── kiwoom-bridge/              # 키움증권 Windows 브릿지 (별도 머신)
├── k8s/                        # Kubernetes 매니페스트
│   ├── base/                   # 공통 리소스
│   └── overlays/
│       ├── local/              # k3d 오버레이
│       └── kind/               # Kind 오버레이
├── scripts/
│   ├── setup-k3d.sh            # k3d 클러스터 생성
│   ├── setup-kind.sh           # Kind 클러스터 생성
│   ├── deploy.sh               # 빌드 + 배포 (k3d/kind 자동 분기)
│   ├── gen-tls-cert.sh         # HTTPS TLS 인증서 생성
│   └── backup-db.sh            # PostgreSQL 백업
└── Makefile                    # 개발 명령어 모음
```

## API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/api/auth/login` | 로그인 (JWT 발급) |
| `GET` | `/api/broker/balance` | 계좌 잔고 조회 |
| `GET` | `/api/broker/price/{ticker}` | 종목 현재가 |
| `GET` | `/api/broker/orders` | 주문 내역 |
| `GET/POST/PUT/DELETE` | `/api/journal` | 매매일지 CRUD |
| `GET` | `/api/briefing/latest` | 최신 시황 브리핑 |
| `GET` | `/api/news` | 뉴스 목록 |
| `GET` | `/api/news/search` | 뉴스 벡터 유사도 검색 |
| `POST` | `/api/ai/feedback` | LLM 매매 피드백 |
| `GET/PUT` | `/api/auto-trade/config` | 자동매매 설정 |
| `GET` | `/api/auto-trade/status` | 자동매매 상태 |
| `GET/POST/PUT/DELETE` | `/api/conditions` | 조건식 CRUD |
| `POST` | `/api/conditions/{id}/scan` | 조건 검색 실행 |
| `POST` | `/api/sectors/analyze` | 섹터 강세 분석 실행 |
| `GET` | `/api/sectors/latest` | 최근 섹터 분석 결과 |
| `POST` | `/api/alerts/overheat` | 단기 과열 종목 감지 |
| `GET` | `/api/supply/latest` | 최근 수급 스냅샷 |
| `GET` | `/api/supply/trend` | KOSPI/KOSDAQ 수급 추세 요약 |

## 자동매매 안전장치

자동매매는 다중 안전장치를 통과해야 실행된다:

1. **비활성 기본값** — `enabled=False`, 명시적으로 활성화해야 동작
2. **모의투자 기본값** — `is_virtual=True`, 실전 전환은 별도 설정
3. **시간 제한** — 장 시작 5분 후 ~ 15:15 사이에만 주문
4. **일일 주문 횟수** — 기본 10회/일
5. **일일 주문 금액** — 기본 200만원/일
6. **보유 종목 수** — 기본 최대 5종목
7. **주문당 금액** — 기본 최대 50만원
8. **손절/익절** — 기본 -3% 손절, +5% 익절 (트레일링 스탑 지원)

## DB 스키마

PostgreSQL + pgvector. 초기화 스크립트: `k8s/base/postgres/init-scripts/01-schema.sql`

| 테이블 | 용도 |
|--------|------|
| `trade_journal` | 매매일지 |
| `market_briefing` | 시황 브리핑 (장전/장후) |
| `news_articles` | 크롤링된 뉴스 + 벡터 임베딩 |
| `user_documents` | 사용자 투자 원칙 (RAG 소스) |
| `search_conditions` | 사용자 정의 조건식 |
| `search_results` | 조건 검색 결과 |
| `auto_trade_orders` | 자동매매 주문 이력 |
| `sector_analysis` | 섹터 강세 분석 결과 (주도섹터/대장주) |
| `supply_snapshots` | 투자자별 수급 스냅샷 (외인/기관/개인) |

> Alembic 미사용. 스키마 변경 시 `01-schema.sql` 수정 후 DB 재생성.

## Make 명령어 요약

```bash
# --- k3d ---
make setup          # k3d 클러스터 + 레지스트리 생성
make deploy         # 빌드 + k3d 배포
make build          # Docker 이미지 빌드만
make clean          # k3d 클러스터 삭제

# --- Kind ---
make setup-kind     # Kind 클러스터 + NGINX Ingress 설치
make deploy-kind    # 빌드 + Kind 배포
make clean-kind     # Kind 클러스터 삭제

# --- 공통 ---
make dev            # 로컬 개발 (uvicorn, Docker 없이)
make backup         # PostgreSQL DB 백업
```

## 환경변수

`.env.example` 참조. 주요 항목:

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `DATABASE_URL` | PostgreSQL 연결 | `postgresql+asyncpg://trading:trading@localhost:5432/trading` |
| `KIS_APP_KEY` | 한투 API 앱키 | - |
| `KIS_APP_SECRET` | 한투 API 시크릿 | - |
| `KIS_ACCOUNT_NO` | 계좌번호 (`XXXXXXXX-01`) | - |
| `KIS_IS_VIRTUAL` | 모의투자 여부 | `true` |
| `OLLAMA_BASE_URL` | Ollama 서버 주소 | `http://localhost:11434` |
| `TELEGRAM_BOT_TOKEN` | 텔레그램 봇 토큰 | - |
| `TELEGRAM_CHAT_ID` | 텔레그램 채팅 ID | - |
| `JWT_SECRET_KEY` | JWT 시크릿 | `change-me-in-production` |
| `STEALTH_PASSWORD` | 로그인 비밀번호 | `change-me` |

## 라이선스

Private repository.
