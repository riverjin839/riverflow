"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

export function NavBar() {
  const [loggedIn, setLoggedIn] = useState(false);
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    setLoggedIn(!!localStorage.getItem("token"));
  }, [pathname]);

  const logout = () => {
    localStorage.removeItem("token");
    setLoggedIn(false);
    router.push("/login");
  };

  const link = (href: string, label: string) => {
    const active = pathname === href;
    return (
      <a
        href={href}
        className={`transition-colors ${
          active ? "text-white" : "text-gray-400 hover:text-white"
        }`}
      >
        {label}
      </a>
    );
  };

  return (
    <nav className="sticky top-0 z-50 border-b border-gray-800 bg-gray-950/80 backdrop-blur-md">
      <div className="mx-auto flex h-12 max-w-7xl items-center justify-between px-4">
        <a
          href="/dashboard"
          className="text-lg font-bold tracking-tight text-blue-400 hover:text-blue-300 transition-colors"
        >
          Riverflow
        </a>

        <div className="flex items-center gap-6 text-sm">
          {loggedIn ? (
            <>
              {link("/dashboard", "대시보드")}
              {link("/market", "시황")}
              {link("/journal", "매매일지")}
              <button
                onClick={logout}
                className="text-gray-500 hover:text-red-400 transition-colors"
              >
                로그아웃
              </button>
            </>
          ) : (
            <a href="/login" className="text-gray-400 hover:text-white transition-colors">
              로그인
            </a>
          )}
        </div>
      </div>
    </nav>
  );
}
