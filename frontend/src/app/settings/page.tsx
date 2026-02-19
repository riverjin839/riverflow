"use client";

import { useEffect, useState } from "react";
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

export default function SettingsPage() {
  const { token, checked } = useAuth();
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setSettings(loadSettings());
  }, []);

  const update = (patch: Partial<AppSettings>) => {
    const next = { ...settings, ...patch };
    setSettings(next);
    saveSettings(next);
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
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
    </div>
  );
}
