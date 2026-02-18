"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";

export default function LoginPage() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await apiFetch<{ access_token: string }>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ password }),
      });
      localStorage.setItem("token", res.access_token);
      router.push("/dashboard");
    } catch {
      setError("인증 실패");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-[70vh] items-center justify-center">
      <form
        onSubmit={handleLogin}
        className="w-full max-w-sm rounded-2xl border border-gray-800 bg-gray-900/60 p-8 backdrop-blur"
      >
        <h1 className="mb-1 text-xl font-bold text-gray-100">Riverflow</h1>
        <p className="mb-6 text-xs text-gray-500">Trading System</p>

        <label className="mb-1.5 block text-xs font-medium text-gray-400">
          비밀번호
        </label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="비밀번호 입력"
          autoFocus
          className="mb-4 w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2.5 text-sm text-gray-100 placeholder-gray-600 outline-none transition-colors focus:border-blue-500 focus:ring-1 focus:ring-blue-500/30"
        />

        {error && (
          <p className="mb-3 text-xs text-red-400">{error}</p>
        )}

        <button
          type="submit"
          disabled={loading || !password}
          className="w-full rounded-lg bg-blue-600 py-2.5 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {loading ? "로그인 중…" : "로그인"}
        </button>
      </form>
    </div>
  );
}
