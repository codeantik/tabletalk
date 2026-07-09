"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  createSession,
  getMessages,
  getTables,
  postMessage,
  type MessageResponse,
  type TableSchema,
} from "@/lib/api";
import { clearStoredSessionId, loadStoredSessionId, storeSessionId } from "@/lib/storage";
import FileUpload from "@/components/FileUpload";
import TablesSidebar from "@/components/TablesSidebar";
import ChatPanel from "@/components/ChatPanel";

export default function Home() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [tables, setTables] = useState<TableSchema[]>([]);
  const [messages, setMessages] = useState<MessageResponse[]>([]);
  const [pending, setPending] = useState(false);
  const [bootError, setBootError] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      const storedId = loadStoredSessionId();
      if (storedId) {
        try {
          const [tablesRes, messagesRes] = await Promise.all([
            getTables(storedId),
            getMessages(storedId),
          ]);
          if (cancelled) return;
          setSessionId(storedId);
          setTables(tablesRes.tables);
          setMessages(messagesRes.messages);
          return;
        } catch {
          clearStoredSessionId();
        }
      }

      try {
        const session = await createSession();
        if (cancelled) return;
        storeSessionId(session.session_id);
        setSessionId(session.session_id);
      } catch {
        if (!cancelled) setBootError("Could not reach the backend. Is it running?");
      }
    }

    bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSend(question: string) {
    if (!sessionId) return;
    setPending(true);
    setBanner(null);
    try {
      const response = await postMessage(sessionId, question);
      setMessages((prev) => [...prev, response]);
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Something went wrong. Please try again.";
      setMessages((prev) => [
        ...prev,
        {
          session_id: sessionId,
          question,
          created_at: new Date().toISOString(),
          sql_used: null,
          intent: null,
          text: null,
          chart: null,
          table: null,
          error: message,
          row_limit_applied: false,
        },
      ]);
    } finally {
      setPending(false);
    }
  }

  if (bootError) {
    return (
      <div className="flex min-h-screen items-center justify-center px-6">
        <p className="max-w-md text-center text-sm text-red-600 dark:text-red-400">
          {bootError}
        </p>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col bg-zinc-50 dark:bg-black">
      <header className="border-b border-zinc-200 px-6 py-4 dark:border-zinc-800">
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">
          Table Talk
        </h1>
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          Upload CSVs and ask questions in plain English.
        </p>
      </header>

      {banner && (
        <div className="bg-amber-50 px-6 py-2 text-sm text-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
          {banner}
        </div>
      )}

      <main className="flex flex-1 flex-col md:flex-row">
        <aside className="w-full shrink-0 border-b border-zinc-200 p-4 md:w-80 md:border-b-0 md:border-r dark:border-zinc-800">
          <div className="flex flex-col gap-4">
            {sessionId && (
              <FileUpload
                sessionId={sessionId}
                onUploaded={(newTables) => {
                  setTables((prev) => {
                    const byName = new Map(prev.map((t) => [t.name, t]));
                    for (const t of newTables) byName.set(t.name, t);
                    return Array.from(byName.values());
                  });
                }}
              />
            )}
            <div>
              <h2 className="mb-2 text-xs font-semibold tracking-wide text-zinc-500 uppercase dark:text-zinc-400">
                Loaded tables
              </h2>
              <TablesSidebar tables={tables} />
            </div>
          </div>
        </aside>

        <section className="flex-1">
          <ChatPanel
            messages={messages}
            onSend={handleSend}
            disabled={tables.length === 0 || !sessionId}
            pending={pending}
          />
        </section>
      </main>
    </div>
  );
}
