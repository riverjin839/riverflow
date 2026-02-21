"""K8s 클러스터 일일 모니터링 워커.

CronJob으로 매일 08:00 KST(23:00 UTC 전일)에 실행된다.
trading-system 네임스페이스의 pod/CronJob 상태를 K8s API에서 수집하고,
내부 pod로 운영되는 Ollama LLM으로 이상 징후를 분석한 뒤
market_briefing 테이블에 저장하고 Telegram으로 발송한다.

LLM 연결: http://ollama:11434 (클러스터 내부 ClusterIP 서비스)
"""

import asyncio
import json
import logging
import os
import ssl
from datetime import datetime, timezone

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from backend.app.services.llm_client import LLMClient
from backend.app.services.notifier import Notifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

# K8s in-cluster API 접근 설정
_K8S_API_HOST = os.environ.get("KUBERNETES_SERVICE_HOST", "")
_K8S_API_PORT = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
_K8S_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
_K8S_CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
_NAMESPACE = "trading-system"

K8S_MONITOR_SYSTEM = (
    "당신은 Kubernetes 클러스터 운영 전문가입니다. "
    "trading-system 네임스페이스의 pod/CronJob 상태 데이터를 분석하여 "
    "이상 징후, 리소스 경고, 개선 제안을 한국어로 간결하게 작성하세요. "
    "정상 상태라면 '이상 없음'으로 명확히 표기하세요."
)


class K8sApiClient:
    """K8s in-cluster REST API 클라이언트"""

    def __init__(self) -> None:
        if not _K8S_API_HOST:
            raise RuntimeError(
                "KUBERNETES_SERVICE_HOST 환경변수 없음 - in-cluster 환경에서만 실행 가능"
            )
        self.base_url = f"https://{_K8S_API_HOST}:{_K8S_API_PORT}"
        with open(_K8S_TOKEN_PATH) as f:
            token = f.read().strip()
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        # CA 인증서로 TLS 검증
        ssl_ctx = ssl.create_default_context(cafile=_K8S_CA_PATH)
        self._client = httpx.AsyncClient(
            headers=self._headers,
            verify=ssl_ctx,
            timeout=30.0,
        )

    async def _get(self, path: str) -> dict:
        resp = await self._client.get(f"{self.base_url}{path}")
        resp.raise_for_status()
        return resp.json()

    async def list_pods(self, namespace: str = _NAMESPACE) -> list[dict]:
        """네임스페이스 내 모든 pod 상태 조회"""
        data = await self._get(f"/api/v1/namespaces/{namespace}/pods")
        pods = []
        for item in data.get("items", []):
            meta = item.get("metadata", {})
            status = item.get("status", {})
            phase = status.get("phase", "Unknown")
            # container 상태 요약
            container_statuses = status.get("containerStatuses", [])
            restarts = sum(cs.get("restartCount", 0) for cs in container_statuses)
            ready_count = sum(1 for cs in container_statuses if cs.get("ready"))
            total_count = len(container_statuses)
            pods.append(
                {
                    "name": meta.get("name", ""),
                    "phase": phase,
                    "ready": f"{ready_count}/{total_count}",
                    "restarts": restarts,
                    "start_time": status.get("startTime", ""),
                }
            )
        return pods

    async def list_cronjobs(self, namespace: str = _NAMESPACE) -> list[dict]:
        """네임스페이스 내 CronJob 목록 및 최근 실행 이력 조회"""
        data = await self._get(f"/apis/batch/v1/namespaces/{namespace}/cronjobs")
        cronjobs = []
        for item in data.get("items", []):
            meta = item.get("metadata", {})
            spec = item.get("spec", {})
            status = item.get("status", {})
            last_schedule = status.get("lastScheduleTime", "없음")
            last_success = status.get("lastSuccessfulTime", "없음")
            active_count = len(status.get("active", []))
            cronjobs.append(
                {
                    "name": meta.get("name", ""),
                    "schedule": spec.get("schedule", ""),
                    "suspended": spec.get("suspend", False),
                    "active": active_count,
                    "last_schedule": last_schedule,
                    "last_success": last_success,
                }
            )
        return cronjobs

    async def list_recent_failed_jobs(self, namespace: str = _NAMESPACE) -> list[dict]:
        """최근 24h 내 실패한 Job 조회"""
        data = await self._get(f"/apis/batch/v1/namespaces/{namespace}/jobs")
        failed = []
        now = datetime.now(timezone.utc)
        for item in data.get("items", []):
            meta = item.get("metadata", {})
            status = item.get("status", {})
            if status.get("failed", 0) > 0:
                # 24h 이내 실패만 포함
                start_raw = status.get("startTime", "")
                if start_raw:
                    try:
                        start_dt = datetime.fromisoformat(
                            start_raw.replace("Z", "+00:00")
                        )
                        if (now - start_dt).total_seconds() > 86400:
                            continue
                    except ValueError:
                        pass
                owner = ""
                for ref in meta.get("ownerReferences", []):
                    if ref.get("kind") == "CronJob":
                        owner = ref.get("name", "")
                        break
                failed.append(
                    {
                        "job": meta.get("name", ""),
                        "cronjob": owner,
                        "failed_count": status.get("failed", 0),
                        "start_time": start_raw,
                    }
                )
        return failed

    async def close(self) -> None:
        await self._client.aclose()


def _build_monitor_prompt(
    pods: list[dict],
    cronjobs: list[dict],
    failed_jobs: list[dict],
    now_kst: str,
) -> str:
    """LLM 프롬프트 구성"""
    lines = [f"## K8s 클러스터 상태 보고 ({now_kst} KST)\n"]

    # Pod 요약
    lines.append("### Pod 상태")
    if pods:
        problem_pods = [p for p in pods if p["phase"] not in ("Running", "Succeeded")]
        running = [p for p in pods if p["phase"] == "Running"]
        high_restart = [p for p in pods if p["restarts"] >= 5]
        lines.append(f"- 전체: {len(pods)}개 / 실행 중: {len(running)}개")
        if problem_pods:
            lines.append(f"- 비정상 pod: {[p['name'] for p in problem_pods]}")
        if high_restart:
            lines.append(
                f"- 재시작 5회 이상: "
                + ", ".join(f"{p['name']}({p['restarts']}회)" for p in high_restart)
            )
        if not problem_pods and not high_restart:
            lines.append("- 모든 pod 정상")
    else:
        lines.append("- pod 정보 없음")

    # CronJob 요약
    lines.append("\n### CronJob 상태")
    if cronjobs:
        for cj in cronjobs:
            status_tag = "[일시정지]" if cj["suspended"] else ""
            lines.append(
                f"- {cj['name']} {status_tag} | 스케줄: {cj['schedule']} | "
                f"마지막 스케줄: {cj['last_schedule']} | "
                f"마지막 성공: {cj['last_success']}"
            )
    else:
        lines.append("- CronJob 없음")

    # 실패 Job
    lines.append("\n### 최근 24h 실패 Job")
    if failed_jobs:
        for fj in failed_jobs:
            lines.append(
                f"- {fj['job']} (CronJob: {fj['cronjob']}) "
                f"| 실패횟수: {fj['failed_count']} | 시작: {fj['start_time']}"
            )
    else:
        lines.append("- 실패 없음")

    return "\n".join(lines)


async def run_k8s_daily_monitor() -> None:
    """K8s 일일 모니터링 실행"""
    logger.info("K8s 일일 모니터링 시작")

    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://trading:trading@localhost:5432/trading",
    )
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # 내부 K8s pod Ollama 서비스 사용 (http://ollama:11434)
    llm = LLMClient()
    notifier = Notifier()
    k8s: K8sApiClient | None = None

    try:
        k8s = K8sApiClient()

        # K8s 상태 수집 (병렬)
        pods, cronjobs, failed_jobs = await asyncio.gather(
            k8s.list_pods(),
            k8s.list_cronjobs(),
            k8s.list_recent_failed_jobs(),
        )
        logger.info(
            "수집 완료: pod %d개, CronJob %d개, 실패 Job %d개",
            len(pods),
            len(cronjobs),
            len(failed_jobs),
        )

        # KST 현재 시각
        now_kst = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

        prompt = _build_monitor_prompt(pods, cronjobs, failed_jobs, now_kst)

        # 내부 Ollama로 LLM 분석 (OLLAMA_BASE_URL = http://ollama:11434)
        analysis = await llm.generate(
            prompt=f"{prompt}\n\n위 상태를 분석하여 이상 징후, 경고, 권장 조치를 작성하세요.",
            system=K8S_MONITOR_SYSTEM,
        )

        # raw_data: 수집 데이터 JSON 요약
        raw_data = json.dumps(
            {
                "pod_count": len(pods),
                "cronjob_count": len(cronjobs),
                "failed_job_count": len(failed_jobs),
                "problem_pods": [
                    p["name"]
                    for p in pods
                    if p["phase"] not in ("Running", "Succeeded")
                ],
                "failed_jobs": [fj["job"] for fj in failed_jobs],
            },
            ensure_ascii=False,
        )

        async with async_session() as db:
            await db.execute(
                text(
                    "INSERT INTO market_briefing (briefing_type, raw_data, summary) "
                    "VALUES ('k8s_daily_monitor', :raw_data::jsonb, :summary)"
                ),
                {"raw_data": raw_data, "summary": analysis},
            )
            await db.commit()

        await notifier.send(f"[K8s 일일 모니터]\n{analysis}")
        logger.info("K8s 일일 모니터링 완료")

    except RuntimeError as e:
        # in-cluster 환경이 아닌 경우 (로컬 개발)
        logger.warning("K8s API 접근 불가 (로컬 개발 환경): %s", e)
    finally:
        if k8s:
            await k8s.close()
        await llm.close()
        await notifier.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_k8s_daily_monitor())
