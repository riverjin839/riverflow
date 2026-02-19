#!/bin/bash
set -euo pipefail

# K8s Secret 생성 + 배포 스크립트
# 사용법: ./scripts/setup-secrets.sh [네임스페이스]
#
# 각 시크릿 값을 차례로 입력받아 K8s Secret을 생성하고,
# 선택적으로 배포까지 수행한다.

NAMESPACE="${1:-trading-system}"
BOLD="\033[1m"
DIM="\033[2m"
CYAN="\033[36m"
GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
RESET="\033[0m"

echo -e "${BOLD}${CYAN}"
echo "╔══════════════════════════════════════════════════╗"
echo "║       Riverflow - K8s Secret 설정 마법사         ║"
echo "╚══════════════════════════════════════════════════╝"
echo -e "${RESET}"

# 네임스페이스 존재 확인
if ! kubectl get namespace "$NAMESPACE" &>/dev/null; then
    echo -e "${YELLOW}네임스페이스 '$NAMESPACE'가 없습니다. 생성합니다...${RESET}"
    kubectl create namespace "$NAMESPACE"
fi

# ──────────────────────────────────────────────
# 입력 헬퍼 함수
# ──────────────────────────────────────────────

# 일반 입력 (화면에 표시)
prompt_value() {
    local label="$1"
    local default="$2"
    local result

    if [ -n "$default" ]; then
        read -rp "  $label [${default}]: " result
        echo "${result:-$default}"
    else
        while true; do
            read -rp "  $label: " result
            if [ -n "$result" ]; then
                echo "$result"
                return
            fi
            echo -e "  ${RED}값을 입력해주세요.${RESET}" >&2
        done
    fi
}

# 비밀 입력 (화면에 가림)
prompt_secret() {
    local label="$1"
    local default="$2"
    local result

    if [ -n "$default" ]; then
        read -srp "  $label [기존값 유지 Enter]: " result
        echo "" >&2
        echo "${result:-$default}"
    else
        while true; do
            read -srp "  $label: " result
            echo "" >&2
            if [ -n "$result" ]; then
                echo "$result"
                return
            fi
            echo -e "  ${RED}값을 입력해주세요.${RESET}" >&2
        done
    fi
}

# 기존 Secret에서 값 읽기 (있으면)
get_existing() {
    local secret_name="$1"
    local key="$2"
    kubectl get secret "$secret_name" -n "$NAMESPACE" -o jsonpath="{.data.$key}" 2>/dev/null | base64 -d 2>/dev/null || echo ""
}

# ──────────────────────────────────────────────
# 1. PostgreSQL DB 시크릿 (trading-db-creds)
# ──────────────────────────────────────────────

echo -e "${BOLD}━━━ 1/4. PostgreSQL 데이터베이스 ━━━${RESET}"
echo -e "${DIM}  Backend와 모든 Worker가 DB 접속에 사용합니다.${RESET}"
echo ""

existing_pg_pw=$(get_existing "trading-db-creds" "POSTGRES_PASSWORD")

POSTGRES_PASSWORD=$(prompt_secret "POSTGRES_PASSWORD (DB 비밀번호)" "$existing_pg_pw")

echo ""

# ──────────────────────────────────────────────
# 2. KIS 증권 API 시크릿 (kis-credentials)
# ──────────────────────────────────────────────

echo -e "${BOLD}━━━ 2/4. 한국투자증권 (KIS) API ━━━${RESET}"
echo -e "${DIM}  https://apiportal.koreainvestment.com 에서 발급${RESET}"
echo ""

existing_app_key=$(get_existing "kis-credentials" "KIS_APP_KEY")
existing_app_secret=$(get_existing "kis-credentials" "KIS_APP_SECRET")
existing_account=$(get_existing "kis-credentials" "KIS_ACCOUNT_NO")
existing_hts_id=$(get_existing "kis-credentials" "KIS_HTS_ID")
existing_virtual=$(get_existing "kis-credentials" "KIS_IS_VIRTUAL")

KIS_APP_KEY=$(prompt_secret "KIS_APP_KEY (앱 키)" "$existing_app_key")
KIS_APP_SECRET=$(prompt_secret "KIS_APP_SECRET (앱 시크릿)" "$existing_app_secret")
KIS_ACCOUNT_NO=$(prompt_value "KIS_ACCOUNT_NO (계좌번호, 예: 00000000-01)" "$existing_account")
KIS_HTS_ID=$(prompt_value "KIS_HTS_ID (HTS 아이디)" "$existing_hts_id")
KIS_IS_VIRTUAL=$(prompt_value "KIS_IS_VIRTUAL (모의투자: true / 실전: false)" "${existing_virtual:-true}")

echo ""

# ──────────────────────────────────────────────
# 3. 앱 시크릿 (trading-app-secrets)
# ──────────────────────────────────────────────

echo -e "${BOLD}━━━ 3/4. 앱 설정 (인증/알림) ━━━${RESET}"
echo -e "${DIM}  JWT, 로그인 비밀번호, 텔레그램 알림 설정${RESET}"
echo ""

existing_jwt=$(get_existing "trading-app-secrets" "JWT_SECRET_KEY")
existing_stealth=$(get_existing "trading-app-secrets" "STEALTH_PASSWORD")
existing_tg_token=$(get_existing "trading-app-secrets" "TELEGRAM_BOT_TOKEN")
existing_tg_chat=$(get_existing "trading-app-secrets" "TELEGRAM_CHAT_ID")

JWT_SECRET_KEY=$(prompt_secret "JWT_SECRET_KEY (JWT 시크릿)" "${existing_jwt:-$(openssl rand -hex 32)}")
STEALTH_PASSWORD=$(prompt_secret "STEALTH_PASSWORD (로그인 비밀번호)" "${existing_stealth:-change-me}")

echo -e "  ${DIM}텔레그램 알림 (선택, Enter로 건너뛰기)${RESET}"
read -rp "  TELEGRAM_BOT_TOKEN: " TELEGRAM_BOT_TOKEN
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-${existing_tg_token}}"
read -rp "  TELEGRAM_CHAT_ID: " TELEGRAM_CHAT_ID
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-${existing_tg_chat}}"

echo ""

# ──────────────────────────────────────────────
# 4. 확인 및 적용
# ──────────────────────────────────────────────

echo -e "${BOLD}━━━ 4/4. 설정 확인 ━━━${RESET}"
echo ""
echo -e "  ${CYAN}[trading-db-creds]${RESET}"
echo "    POSTGRES_PASSWORD = ********"
echo ""
echo -e "  ${CYAN}[kis-credentials]${RESET}"
echo "    KIS_APP_KEY       = ${KIS_APP_KEY:0:4}****"
echo "    KIS_APP_SECRET    = ********"
echo "    KIS_ACCOUNT_NO    = $KIS_ACCOUNT_NO"
echo "    KIS_HTS_ID        = $KIS_HTS_ID"
echo "    KIS_IS_VIRTUAL    = $KIS_IS_VIRTUAL"
echo ""
echo -e "  ${CYAN}[trading-app-secrets]${RESET}"
echo "    JWT_SECRET_KEY    = ${JWT_SECRET_KEY:0:8}****"
echo "    STEALTH_PASSWORD  = ********"
echo "    TELEGRAM_BOT_TOKEN= ${TELEGRAM_BOT_TOKEN:+설정됨}${TELEGRAM_BOT_TOKEN:-미설정}"
echo "    TELEGRAM_CHAT_ID  = ${TELEGRAM_CHAT_ID:-미설정}"
echo ""

read -rp "$(echo -e "${YELLOW}위 설정으로 Secret을 생성하시겠습니까? (y/N): ${RESET}")" confirm
if [[ ! "$confirm" =~ ^[yY]$ ]]; then
    echo -e "${RED}취소되었습니다.${RESET}"
    exit 1
fi

echo ""
echo -e "${BOLD}=== K8s Secret 생성 ===${RESET}"

# trading-db-creds
kubectl delete secret trading-db-creds -n "$NAMESPACE" --ignore-not-found &>/dev/null
kubectl create secret generic trading-db-creds \
    -n "$NAMESPACE" \
    --from-literal=POSTGRES_PASSWORD="$POSTGRES_PASSWORD"
echo -e "  ${GREEN}✓${RESET} trading-db-creds"

# kis-credentials
kubectl delete secret kis-credentials -n "$NAMESPACE" --ignore-not-found &>/dev/null
kubectl create secret generic kis-credentials \
    -n "$NAMESPACE" \
    --from-literal=KIS_APP_KEY="$KIS_APP_KEY" \
    --from-literal=KIS_APP_SECRET="$KIS_APP_SECRET" \
    --from-literal=KIS_ACCOUNT_NO="$KIS_ACCOUNT_NO" \
    --from-literal=KIS_HTS_ID="$KIS_HTS_ID" \
    --from-literal=KIS_IS_VIRTUAL="$KIS_IS_VIRTUAL"
echo -e "  ${GREEN}✓${RESET} kis-credentials"

# trading-app-secrets
APP_SECRET_ARGS=(
    --from-literal=JWT_SECRET_KEY="$JWT_SECRET_KEY"
    --from-literal=STEALTH_PASSWORD="$STEALTH_PASSWORD"
)
[ -n "$TELEGRAM_BOT_TOKEN" ] && APP_SECRET_ARGS+=(--from-literal=TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN")
[ -n "$TELEGRAM_CHAT_ID" ] && APP_SECRET_ARGS+=(--from-literal=TELEGRAM_CHAT_ID="$TELEGRAM_CHAT_ID")

kubectl delete secret trading-app-secrets -n "$NAMESPACE" --ignore-not-found &>/dev/null
kubectl create secret generic trading-app-secrets \
    -n "$NAMESPACE" \
    "${APP_SECRET_ARGS[@]}"
echo -e "  ${GREEN}✓${RESET} trading-app-secrets"

echo ""
echo -e "${GREEN}${BOLD}Secret 생성 완료!${RESET}"
echo ""

# ──────────────────────────────────────────────
# 배포 여부 확인
# ──────────────────────────────────────────────

read -rp "$(echo -e "${YELLOW}바로 배포하시겠습니까? (y/N): ${RESET}")" deploy_confirm
if [[ "$deploy_confirm" =~ ^[yY]$ ]]; then
    echo ""
    echo -e "${DIM}배포 환경을 선택하세요:${RESET}"
    echo "  1) kind  (Mac Mini 등)"
    echo "  2) local (k3d)"
    read -rp "  선택 [1]: " env_choice

    case "${env_choice:-1}" in
        1) DEPLOY_ENV="kind" ;;
        2) DEPLOY_ENV="local" ;;
        *) DEPLOY_ENV="kind" ;;
    esac

    echo ""
    echo -e "${BOLD}=== $DEPLOY_ENV 환경으로 배포 시작 ===${RESET}"
    exec ./scripts/deploy.sh "$DEPLOY_ENV"
else
    echo ""
    echo -e "${DIM}나중에 배포하려면:${RESET}"
    echo "  ./scripts/deploy.sh kind    # Kind 환경"
    echo "  ./scripts/deploy.sh local   # k3d 환경"
fi
