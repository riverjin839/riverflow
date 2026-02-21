"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/use-auth";

const REFRESH_OPTIONS = [
  { value: 0, label: "수동 (자동 새로고침 끔)" },
  { value: 10, label: "10초" },
  { value: 15, label: "15초" },
  { value: 30, label: "30초" },
  { value: 60, label: "1분" },
  { value: 120, label: "2분" },
  { value: 300, label: "5분" },
];

const STORAGE_KEY = "settings";

interface AppSettings {
  refreshInterval: number; // 초 단위, 0 = 수동
}

const DEFAULT_SETTINGS: AppSettings = { refreshInterval: 30 };

function loadSettings(): AppSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
  } catch { /* ignore */ }
  return DEFAULT_SETTINGS;
}

function saveSettings(s: AppSettings) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
}

interface BrokerSettings {
  KIS_APP_KEY: string;
  KIS_APP_SECRET: string;
  KIS_ACCOUNT_NO: string;
  KIS_HTS_ID: string;
  KIS_IS_VIRTUAL: boolean;
  has_keys: boolean;
}

export default function SettingsPage() {
  const { token, checked } = useAuth();
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS);
  const [saved, setSaved] = useState(false);

  // 브로커 설정
  const [broker, setBroker] = useState<BrokerSettings>({
    KIS_APP_KEY: "", KIS_APP_SECRET: "", KIS_ACCOUNT_NO: "",
    KIS_HTS_ID: "", KIS_IS_VIRTUAL: true, has_keys: false,
  });
  const [brokerForm, setBrokerForm] = useState({
    KIS_APP_KEY: "", KIS_APP_SECRET: "", KIS_ACCOUNT_NO: "",
    KIS_HTS_ID: "", KIS_IS_VIRTUAL: true,
  });
  const [brokerSaving, setBrokerSaving] = useState(false);
  const [brokerMsg, setBrokerMsg] = useState("");
  const [showSecrets, setShowSecrets] = useState(false);

  useEffect(() => {
    setSettings(loadSettings());
  }, []);

  useEffect(() => {
    if (!token) return;
    apiFetch<BrokerSettings>("/api/settings/broker", { token })
      .then((data) => {
        setBroker(data);
        setBrokerForm({
          KIS_APP_KEY: data.KIS_APP_KEY,
          KIS_APP_SECRET: data.KIS_APP_SECRET,
          KIS_ACCOUNT_NO: data.KIS_ACCOUNT_NO,
          KIS_HTS_ID: data.KIS_HTS_ID,
          KIS_IS_VIRTUAL: data.KIS_IS_VIRTUAL,
        });
      })
      .catch(() => {});
  }, [token]);

  const update = (patch: Partial<AppSettings>) => {
    const next = { ...settings, ...patch };
    setSettings(next);
    saveSettings(next);
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  };

  const saveBroker = async () => {
    if (!token) return;
    setBrokerSaving(true);
    setBrokerMsg("");
    try {
      await apiFetch("/api/settings/broker", {
        token, method: "PUT",
        body: JSON.stringify(brokerForm),
      });
      setBrokerMsg("저장되었습니다");
      const data = await apiFetch<BrokerSettings>("/api/settings/broker", { token });
      setBroker(data);
      setBrokerForm({
        KIS_APP_KEY: data.KIS_APP_KEY, KIS_APP_SECRET: data.KIS_APP_SECRET,
        KIS_ACCOUNT_NO: data.KIS_ACCOUNT_NO, KIS_HTS_ID: data.KIS_HTS_ID,
        KIS_IS_VIRTUAL: data.KIS_IS_VIRTUAL,
      });
    } catch {
      setBrokerMsg("저장 실패");
    } finally {
      setBrokerSaving(false);
      setTimeout(() => setBrokerMsg(""), 2000);
    }
  };

  const deleteBroker = async () => {
    if (!token || !confirm("브로커 API 키를 모두 삭제하시겠습니까?")) return;
    try {
      await apiFetch("/api/settings/broker", { token, method: "DELETE" });
      setBroker({ KIS_APP_KEY: "", KIS_APP_SECRET: "", KIS_ACCOUNT_NO: "", KIS_HTS_ID: "", KIS_IS_VIRTUAL: true, has_keys: false });
      setBrokerForm({ KIS_APP_KEY: "", KIS_APP_SECRET: "", KIS_ACCOUNT_NO: "", KIS_HTS_ID: "", KIS_IS_VIRTUAL: true });
      setBrokerMsg("삭제되었습니다");
      setTimeout(() => setBrokerMsg(""), 2000);
    } catch {
      setBrokerMsg("삭제 실패");
    }
  };

  if (!checked || !token) return null;

  return (
    <div className="space-y-8">
      <h1 className="text-lg font-bold text-gray-200">설정</h1>

      {/* 새로고침 주기 */}
      <section className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
        <h2 className="mb-1 text-sm font-semibold text-gray-300">자동 새로고침 주기</h2>
        <p className="mb-4 text-xs text-gray-500">시황 / 대시보드 데이터를 자동으로 갱신하는 주기를 설정합니다.</p>

        <div className="flex flex-wrap gap-2">
          {REFRESH_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => update({ refreshInterval: opt.value })}
              className={`rounded-lg px-4 py-2 text-sm transition-colors ${
                settings.refreshInterval === opt.value
                  ? "bg-blue-600 text-white"
                  : "border border-gray-700 bg-gray-800/60 text-gray-400 hover:border-gray-600 hover:text-gray-200"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {saved && (
          <p className="mt-3 text-xs text-emerald-400">저장되었습니다</p>
        )}
      </section>

      {/* 증권사 API 키 */}
      <section className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-gray-300">한국투자증권 API 연동</h2>
            <p className="mt-1 text-xs text-gray-500">
              API 키는 AES-256 암호화되어 서버에 저장됩니다.
            </p>
          </div>
          {broker.has_keys && (
            <span className="rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-medium text-emerald-400">
              연동됨
            </span>
          )}
        </div>

        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-400">APP KEY</label>
            <input
              type={showSecrets ? "text" : "password"}
              value={brokerForm.KIS_APP_KEY}
              onChange={(e) => setBrokerForm({ ...brokerForm, KIS_APP_KEY: e.target.value })}
              placeholder="한국투자증권 앱 키"
              className="w-full rounded-lg border border-gray-700 bg-gray-800/80 px-3 py-2.5 text-sm text-gray-200 placeholder-gray-600 focus:border-blue-500 focus:outline-none"
              autoComplete="off"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-gray-400">APP SECRET</label>
            <input
              type={showSecrets ? "text" : "password"}
              value={brokerForm.KIS_APP_SECRET}
              onChange={(e) => setBrokerForm({ ...brokerForm, KIS_APP_SECRET: e.target.value })}
              placeholder="한국투자증권 앱 시크릿"
              className="w-full rounded-lg border border-gray-700 bg-gray-800/80 px-3 py-2.5 text-sm text-gray-200 placeholder-gray-600 focus:border-blue-500 focus:outline-none"
              autoComplete="off"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-gray-400">계좌번호</label>
            <input
              type={showSecrets ? "text" : "password"}
              value={brokerForm.KIS_ACCOUNT_NO}
              onChange={(e) => setBrokerForm({ ...brokerForm, KIS_ACCOUNT_NO: e.target.value })}
              placeholder="00000000-00 형식"
              className="w-full rounded-lg border border-gray-700 bg-gray-800/80 px-3 py-2.5 text-sm text-gray-200 placeholder-gray-600 focus:border-blue-500 focus:outline-none"
              autoComplete="off"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-gray-400">HTS ID (선택)</label>
            <input
              type="text"
              value={brokerForm.KIS_HTS_ID}
              onChange={(e) => setBrokerForm({ ...brokerForm, KIS_HTS_ID: e.target.value })}
              placeholder="HTS 아이디"
              className="w-full rounded-lg border border-gray-700 bg-gray-800/80 px-3 py-2.5 text-sm text-gray-200 placeholder-gray-600 focus:border-blue-500 focus:outline-none"
              autoComplete="off"
            />
          </div>

          {/* 모의투자 토글 */}
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setBrokerForm({ ...brokerForm, KIS_IS_VIRTUAL: !brokerForm.KIS_IS_VIRTUAL })}
              className={`relative h-6 w-11 rounded-full transition-colors ${
                brokerForm.KIS_IS_VIRTUAL ? "bg-blue-600" : "bg-red-500"
              }`}
            >
              <span
                className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
                  brokerForm.KIS_IS_VIRTUAL ? "left-0.5" : "left-[22px]"
                }`}
              />
            </button>
            <span className="text-sm text-gray-300">
              {brokerForm.KIS_IS_VIRTUAL ? "모의투자" : "실전투자"}
            </span>
            {!brokerForm.KIS_IS_VIRTUAL && (
              <span className="rounded bg-red-500/15 px-2 py-0.5 text-xs text-red-400">
                실전 모드 주의
              </span>
            )}
          </div>

          <button
            type="button"
            onClick={() => setShowSecrets(!showSecrets)}
            className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
          >
            {showSecrets ? "값 숨기기" : "값 보기"}
          </button>

          {/* 버튼 */}
          <div className="flex items-center gap-3 pt-2">
            <button
              onClick={saveBroker}
              disabled={brokerSaving}
              className="rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
            >
              {brokerSaving ? "저장 중..." : "저장"}
            </button>
            {broker.has_keys && (
              <button
                onClick={deleteBroker}
                className="rounded-lg border border-red-500/30 px-4 py-2.5 text-sm text-red-400 transition-colors hover:bg-red-500/10"
              >
                키 삭제
              </button>
            )}
            {brokerMsg && (
              <span className={`text-xs ${brokerMsg.includes("실패") ? "text-red-400" : "text-emerald-400"}`}>
                {brokerMsg}
              </span>
            )}
          </div>
        </div>

        {/* 보안 안내 */}
        <div className="mt-5 rounded-lg border border-gray-800 bg-gray-950/50 p-3">
          <h3 className="mb-2 text-xs font-semibold text-gray-400">보안 안내</h3>
          <ul className="space-y-1 text-xs text-gray-500">
            <li>- API 키는 서버에서 Fernet(AES-256) 대칭키로 암호화 후 저장됩니다</li>
            <li>- 암호화 키는 서버의 JWT 시크릿에서 파생되며, 클라이언트에 평문이 전송되지 않습니다</li>
            <li>- 조회 시 마스킹된 값(앞4자리****뒤4자리)만 반환됩니다</li>
            <li>- 환경변수(KIS_APP_KEY 등)가 설정된 경우 DB 설정보다 우선합니다</li>
          </ul>
        </div>
      </section>
    </div>
  );
}
