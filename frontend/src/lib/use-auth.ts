"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

export function useAuth() {
  const [token, setToken] = useState<string | null>(null);
  const [checked, setChecked] = useState(false);
  const router = useRouter();

  useEffect(() => {
    const stored = localStorage.getItem("token");
    if (!stored) {
      router.replace("/login");
    } else {
      setToken(stored);
    }
    setChecked(true);
  }, [router]);

  return { token, checked };
}
