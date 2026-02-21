"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/use-auth";

/* ── Types ── */
type Tab = "chat" | "docs" | "recommend";

interface ChatMsg {
  role: "user" | "assistant";
  content: string;
  created_at?: string;
}

interface ChatSession {
  session_id: string;
  preview: string;
  started_at: string;
  msg_count: number;
}

interface DocItem {
  id: number;
  doc_type: string;
  title: string;
  content_preview: string;
  created_at: string;
}

interface StockSearchResult {
  ticker: string;
  ticker_name: string;
  market: string;
}

/* ── Helper: apiFetch for FormData (no Content-Type header) ── */
async function apiUpload<T>(path: string, formData: FormData, token: string): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
    cache: "no-store",
  });
  if (!res.ok) {
    if (res.status === 401) {
      localStorage.removeItem("token");
      window.location.href = "/login";
    }
    const text = await res.text();
    throw new Error(text || `API Error: ${res.status}`);
  }
  return res.json();
}

export default function AIPage() {
  const { token, checked } = useAuth();
  const [tab, setTab] = useState<Tab>("chat");

  if (!checked) return null;
  if (!token) return null;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold text-gray-100">AI 어시스턴트</h1>

      {/* 탭 네비게이션 */}
      <div className="flex gap-1 rounded-lg bg-gray-900/60 p-1">
        {([
          ["chat", "채팅"],
          ["docs", "학습자료"],
          ["recommend", "종목분석"],
        ] as [Tab, string][]).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`flex-1 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
              tab === key
                ? "bg-blue-600/20 text-blue-400"
                : "text-gray-500 hover:bg-gray-800/60 hover:text-gray-300"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "chat" && <ChatTab token={token} />}
      {tab === "docs" && <DocsTab token={token} />}
      {tab === "recommend" && <RecommendTab token={token} />}
    </div>
  );
}

/* ══════════════════════════════════════
   채팅 탭
   ══════════════════════════════════════ */
function ChatTab({ token }: { token: string }) {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [showSessions, setShowSessions] = useState(false);
  const [sources, setSources] = useState<string[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  // 세션 목록 로드
  const loadSessions = useCallback(async () => {
    try {
      const data = await apiFetch<ChatSession[]>("/api/ai/chat/sessions", { token });
      setSessions(data);
    } catch { /* ignore */ }
  }, [token]);

  useEffect(() => { loadSessions(); }, [loadSessions]);

  // 세션 히스토리 로드
  const loadSession = async (sid: string) => {
    try {
      const data = await apiFetch<ChatMsg[]>(`/api/ai/chat/history?session_id=${sid}`, { token });
      setMessages(data);
      setSessionId(sid);
      setShowSessions(false);
    } catch { /* ignore */ }
  };

  // 새 대화
  const newChat = () => {
    setMessages([]);
    setSessionId(null);
    setSources([]);
    setInput("");
  };

  // 메시지 전송
  const send = async () => {
    if (!input.trim() || sending) return;
    const userMsg = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setSending(true);

    try {
      const res = await apiFetch<{ reply: string; session_id: string; sources: string[] }>(
        "/api/ai/chat",
        {
          token,
          method: "POST",
          body: JSON.stringify({ message: userMsg, session_id: sessionId }),
        },
      );
      setMessages((prev) => [...prev, { role: "assistant", content: res.reply }]);
      setSessionId(res.session_id);
      setSources(res.sources);
      loadSessions();
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `오류: ${err instanceof Error ? err.message : "전송 실패"}` },
      ]);
    } finally {
      setSending(false);
    }
  };

  // 자동 스크롤
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  // 세션 삭제
  const deleteSession = async (sid: string) => {
    try {
      await apiFetch(`/api/ai/chat/${sid}`, { token, method: "DELETE" });
      loadSessions();
      if (sessionId === sid) newChat();
    } catch { /* ignore */ }
  };

  return (
    <div className="flex gap-4" style={{ height: "calc(100vh - 220px)" }}>
      {/* 사이드: 세션 목록 */}
      <div className={`${showSessions ? "block" : "hidden"} lg:block w-56 shrink-0 overflow-auto rounded-lg border border-gray-800 bg-gray-900/40`}>
        <div className="flex items-center justify-between border-b border-gray-800 px-3 py-2">
          <span className="text-xs font-medium text-gray-400">대화 목록</span>
          <button onClick={newChat} className="rounded bg-blue-600/20 px-2 py-1 text-[10px] text-blue-400 hover:bg-blue-600/30">
            + 새 대화
          </button>
        </div>
        <div className="space-y-0.5 p-1">
          {sessions.map((s) => (
            <div
              key={s.session_id}
              className={`group flex items-center justify-between rounded-md px-2 py-2 text-xs cursor-pointer transition-colors ${
                sessionId === s.session_id ? "bg-gray-800 text-gray-200" : "text-gray-500 hover:bg-gray-800/60 hover:text-gray-300"
              }`}
              onClick={() => loadSession(s.session_id)}
            >
              <span className="truncate flex-1">{s.preview || "새 대화"}</span>
              <button
                onClick={(e) => { e.stopPropagation(); deleteSession(s.session_id); }}
                className="ml-1 hidden text-gray-600 hover:text-red-400 group-hover:block"
              >
                &times;
              </button>
            </div>
          ))}
          {sessions.length === 0 && (
            <div className="px-2 py-4 text-center text-xs text-gray-600">대화 기록 없음</div>
          )}
        </div>
      </div>

      {/* 채팅 영역 */}
      <div className="flex flex-1 flex-col rounded-lg border border-gray-800 bg-gray-900/40">
        {/* 헤더 */}
        <div className="flex items-center gap-2 border-b border-gray-800 px-4 py-2">
          <button onClick={() => setShowSessions(!showSessions)} className="lg:hidden text-gray-500 text-xs">
            목록
          </button>
          <span className="flex-1 text-sm text-gray-400">
            {sessionId ? `세션: ${sessionId}` : "새 대화"}
          </span>
          {sources.length > 0 && (
            <span className="text-[10px] text-gray-600">참고: {sources.length}건</span>
          )}
        </div>

        {/* 메시지 */}
        <div ref={scrollRef} className="flex-1 overflow-auto px-4 py-3 space-y-3">
          {messages.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <div className="text-4xl mb-4">
                <svg className="mx-auto h-16 w-16 text-gray-700" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={0.8}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" />
                </svg>
              </div>
              <p className="text-sm text-gray-500 mb-2">Riverflow AI와 대화를 시작하세요</p>
              <div className="space-y-1 text-xs text-gray-600">
                <p>&quot;삼성전자 005930 지금 매수해도 될까?&quot;</p>
                <p>&quot;코스닥 시장 전망 분석해줘&quot;</p>
                <p>&quot;내 투자원칙에 맞는 종목 추천해줘&quot;</p>
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[80%] rounded-xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
                  m.role === "user"
                    ? "bg-blue-600/20 text-gray-200"
                    : "bg-gray-800/80 text-gray-300"
                }`}
              >
                {m.content}
              </div>
            </div>
          ))}

          {sending && (
            <div className="flex justify-start">
              <div className="rounded-xl bg-gray-800/80 px-4 py-2.5 text-sm text-gray-500">
                <span className="inline-flex gap-1">
                  <span className="animate-pulse">분석 중</span>
                  <span className="animate-bounce" style={{ animationDelay: "0.1s" }}>.</span>
                  <span className="animate-bounce" style={{ animationDelay: "0.2s" }}>.</span>
                  <span className="animate-bounce" style={{ animationDelay: "0.3s" }}>.</span>
                </span>
              </div>
            </div>
          )}
        </div>

        {/* 입력 */}
        <div className="border-t border-gray-800 p-3">
          <div className="flex gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="메시지를 입력하세요... (종목코드 입력 시 자동 시세 조회)"
              rows={1}
              className="flex-1 resize-none rounded-lg border border-gray-700 bg-gray-800 px-3 py-2.5 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500"
            />
            <button
              onClick={send}
              disabled={sending || !input.trim()}
              className="rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-40 transition-colors"
            >
              전송
            </button>
          </div>
          <p className="mt-1 text-[10px] text-gray-600">
            업로드한 학습자료를 기반으로 답변합니다. Shift+Enter로 줄바꿈.
          </p>
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════
   학습자료 탭
   ══════════════════════════════════════ */
function DocsTab({ token }: { token: string }) {
  const [docs, setDocs] = useState<DocItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const loadDocs = useCallback(async () => {
    try {
      const data = await apiFetch<DocItem[]>("/api/ai/documents", { token });
      setDocs(data);
    } catch { /* ignore */ } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { loadDocs(); }, [loadDocs]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !token) return;
    setUploading(true);
    setUploadMsg("");

    const formData = new FormData();
    formData.append("file", file);
    formData.append("doc_type", "general");

    try {
      const res = await apiUpload<{ message: string; chunks: number; total_chars: number }>(
        "/api/ai/documents/upload",
        formData,
        token,
      );
      setUploadMsg(`${res.message} (${res.chunks}개 청크, ${res.total_chars.toLocaleString()}자)`);
      loadDocs();
    } catch (err) {
      setUploadMsg(`업로드 실패: ${err instanceof Error ? err.message : "오류"}`);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const deleteByTitle = async (title: string) => {
    const base = title.split(" [")[0];
    if (!confirm(`'${base}' 관련 모든 청크를 삭제하시겠습니까?`)) return;
    try {
      await apiFetch(`/api/ai/documents?title=${encodeURIComponent(title)}`, { token, method: "DELETE" });
      loadDocs();
    } catch { /* ignore */ }
  };

  // 중복 제거: 같은 파일에서 나온 청크는 그룹핑
  const grouped = docs.reduce<Record<string, { docs: DocItem[]; baseTitle: string }>>((acc, d) => {
    const base = (d.title || "").split(" [")[0];
    if (!acc[base]) acc[base] = { docs: [], baseTitle: base };
    acc[base].docs.push(d);
    return acc;
  }, {});

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
        <h2 className="mb-3 text-sm font-semibold text-gray-300">학습자료 업로드</h2>
        <p className="mb-3 text-xs text-gray-500">
          PDF, TXT, MD, CSV 파일을 업로드하면 AI가 학습하여 투자 분석에 활용합니다.
          (Google NotebookLM 등에서 내보낸 텍스트 파일도 지원)
        </p>

        <div className="flex items-center gap-3">
          <label className="cursor-pointer rounded-lg border border-dashed border-gray-700 bg-gray-800/50 px-6 py-3 text-sm text-gray-400 hover:border-blue-500 hover:text-blue-400 transition-colors">
            {uploading ? "업로드 중..." : "파일 선택"}
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.txt,.md,.csv"
              onChange={handleUpload}
              disabled={uploading}
              className="hidden"
            />
          </label>
          <span className="text-xs text-gray-600">최대 20MB</span>
        </div>

        {uploadMsg && (
          <div className={`mt-3 rounded-lg px-3 py-2 text-xs ${
            uploadMsg.includes("실패") ? "bg-red-900/20 text-red-400" : "bg-emerald-900/20 text-emerald-400"
          }`}>
            {uploadMsg}
          </div>
        )}
      </div>

      {/* 문서 목록 */}
      <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
        <h2 className="mb-3 text-sm font-semibold text-gray-300">
          업로드된 자료 ({Object.keys(grouped).length}개 파일, {docs.length}개 청크)
        </h2>

        {loading ? (
          <p className="text-xs text-gray-600">로딩 중...</p>
        ) : Object.keys(grouped).length === 0 ? (
          <div className="text-center py-8 text-gray-600">
            <p className="text-sm">업로드된 학습자료가 없습니다</p>
            <p className="mt-1 text-xs">PDF, 텍스트 파일을 업로드하여 AI 분석 정확도를 높여보세요</p>
          </div>
        ) : (
          <div className="space-y-2">
            {Object.entries(grouped).map(([base, { docs: chunks }]) => (
              <div
                key={base}
                className="flex items-center justify-between rounded-lg border border-gray-800/60 bg-gray-800/30 px-4 py-3"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <svg className="h-4 w-4 shrink-0 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                    </svg>
                    <span className="truncate text-sm text-gray-300">{base}</span>
                    <span className="shrink-0 rounded bg-gray-700 px-1.5 py-0.5 text-[10px] text-gray-500">
                      {chunks.length}청크
                    </span>
                    <span className="shrink-0 rounded bg-gray-700 px-1.5 py-0.5 text-[10px] text-gray-500">
                      {chunks[0]?.doc_type}
                    </span>
                  </div>
                  <p className="mt-1 truncate text-xs text-gray-600">
                    {chunks[0]?.content_preview}
                  </p>
                </div>
                <button
                  onClick={() => deleteByTitle(chunks[0].title)}
                  className="ml-3 shrink-0 rounded px-2 py-1 text-xs text-gray-600 hover:bg-red-500/10 hover:text-red-400 transition-colors"
                >
                  삭제
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ══════════════════════════════════════
   종목분석 탭
   ══════════════════════════════════════ */
function RecommendTab({ token }: { token: string }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<StockSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const [selected, setSelected] = useState<StockSearchResult | null>(null);
  const [analysis, setAnalysis] = useState("");
  const [analysisSources, setAnalysisSources] = useState<string[]>([]);
  const [analyzing, setAnalyzing] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);

  // 종목 검색
  const search = useCallback(async (q: string) => {
    if (q.length === 0) { setResults([]); return; }
    setSearching(true);
    try {
      const r = await apiFetch<{ results: StockSearchResult[] }>(
        `/api/journal/search-stock?q=${encodeURIComponent(q)}`,
        { token },
      );
      setResults(r.results);
      setShowDropdown(r.results.length > 0);
    } catch {
      setResults([]);
    } finally {
      setSearching(false);
    }
  }, [token]);

  const handleInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = e.target.value;
    setQuery(v);
    if (timerRef.current) clearTimeout(timerRef.current);
    if (v.length > 0) {
      timerRef.current = setTimeout(() => search(v), 300);
    } else {
      setResults([]);
      setShowDropdown(false);
    }
  };

  const selectStock = (item: StockSearchResult) => {
    setSelected(item);
    setQuery(`${item.ticker_name} (${item.ticker})`);
    setShowDropdown(false);
    setResults([]);
    setAnalysis("");
    setAnalysisSources([]);
  };

  // 분석 요청
  const analyze = async () => {
    if (!selected || analyzing) return;
    setAnalyzing(true);
    setAnalysis("");
    try {
      const res = await apiFetch<{ analysis: string; sources: string[] }>("/api/ai/recommend", {
        token,
        method: "POST",
        body: JSON.stringify({ ticker: selected.ticker, ticker_name: selected.ticker_name }),
      });
      setAnalysis(res.analysis);
      setAnalysisSources(res.sources);
    } catch (err) {
      setAnalysis(`분석 실패: ${err instanceof Error ? err.message : "오류"}`);
    } finally {
      setAnalyzing(false);
    }
  };

  // 외부 클릭
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setShowDropdown(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div className="space-y-4">
      {/* 종목 선택 */}
      <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
        <h2 className="mb-3 text-sm font-semibold text-gray-300">종목 분석</h2>
        <p className="mb-3 text-xs text-gray-500">
          종목을 선택하면 시세/차트/재무 데이터 + 학습자료를 기반으로 AI가 매수/매도/관망 의견을 제시합니다.
        </p>

        <div className="flex gap-2">
          <div className="relative flex-1" ref={boxRef}>
            <input
              type="text"
              value={query}
              onChange={handleInput}
              onFocus={() => { if (results.length > 0) setShowDropdown(true); }}
              placeholder="종목코드(005930) 또는 종목명(삼성전자)"
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2.5 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500"
            />
            {searching && (
              <span className="absolute right-3 top-3 text-xs text-gray-500">검색중...</span>
            )}
            {showDropdown && results.length > 0 && (
              <div className="absolute z-20 mt-1 w-full max-h-60 overflow-auto rounded-lg border border-gray-700 bg-gray-800 shadow-xl">
                {results.map((item) => (
                  <button
                    key={item.ticker}
                    type="button"
                    onClick={() => selectStock(item)}
                    className="flex w-full items-center justify-between px-3 py-2.5 text-left text-sm hover:bg-gray-700/60 transition-colors"
                  >
                    <div>
                      <span className="font-medium text-gray-200">{item.ticker_name}</span>
                      <span className="ml-2 text-xs text-gray-500">{item.ticker}</span>
                    </div>
                    {item.market && (
                      <span className="rounded bg-gray-700 px-1.5 py-0.5 text-[10px] text-gray-400">
                        {item.market}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>

          <button
            onClick={analyze}
            disabled={!selected || analyzing}
            className="shrink-0 rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-40 transition-colors"
          >
            {analyzing ? "분석 중..." : "AI 분석"}
          </button>
        </div>

        {selected && (
          <div className="mt-2 flex items-center gap-2">
            <span className="rounded-lg bg-blue-900/30 px-2.5 py-1 text-xs text-blue-300">
              {selected.ticker_name} ({selected.ticker})
            </span>
            <button
              onClick={() => { setSelected(null); setQuery(""); setAnalysis(""); setAnalysisSources([]); }}
              className="text-xs text-gray-500 hover:text-gray-300"
            >
              초기화
            </button>
          </div>
        )}
      </div>

      {/* 분석 결과 */}
      {analyzing && (
        <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-25" />
              <path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" className="opacity-75" />
            </svg>
            시세 조회 + 학습자료 분석 + AI 의견 생성 중...
          </div>
        </div>
      )}

      {analysis && !analyzing && (
        <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-5">
          <h3 className="mb-3 text-sm font-semibold text-gray-300">
            분석 결과 - {selected?.ticker_name}
          </h3>
          <div className="whitespace-pre-wrap text-sm leading-relaxed text-gray-300">
            {analysis}
          </div>
          {analysisSources.length > 0 && (
            <div className="mt-4 border-t border-gray-800 pt-3">
              <p className="text-[10px] text-gray-600 mb-1">참고한 학습자료:</p>
              <div className="flex flex-wrap gap-1">
                {analysisSources.map((s, i) => (
                  <span key={i} className="rounded bg-gray-800 px-1.5 py-0.5 text-[10px] text-gray-500">
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
