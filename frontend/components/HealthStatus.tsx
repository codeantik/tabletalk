"use client";

import { useEffect, useState } from "react";
import { API_BASE_URL } from "@/lib/api";

type Status = "loading" | "ok" | "error";

export default function HealthStatus() {
  const [status, setStatus] = useState<Status>("loading");

  useEffect(() => {
    let cancelled = false;

    fetch(`${API_BASE_URL}/api/health`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => {
        if (!cancelled) setStatus(data.status === "ok" ? "ok" : "error");
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const styles: Record<Status, string> = {
    loading: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300",
    ok: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200",
    error: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  };

  const labels: Record<Status, string> = {
    loading: "Checking backend...",
    ok: "Backend connected",
    error: "Backend unreachable",
  };

  return (
    <div
      className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium ${styles[status]}`}
    >
      <span
        className={`h-2 w-2 rounded-full ${
          status === "ok"
            ? "bg-emerald-500"
            : status === "error"
              ? "bg-red-500"
              : "bg-zinc-400"
        }`}
      />
      {labels[status]}
    </div>
  );
}
