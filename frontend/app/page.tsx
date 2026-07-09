"use client";

import { useEffect, useState } from "react";
import { Menu } from "lucide-react";
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
import EmptyStateHero from "@/components/EmptyStateHero";
import DataManifestRail from "@/components/DataManifestRail";
import ChatPanel from "@/components/ChatPanel";
import ThemeToggle from "@/components/ThemeToggle";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";

export default function Home() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [tables, setTables] = useState<TableSchema[]>([]);
  const [messages, setMessages] = useState<MessageResponse[]>([]);
  const [pending, setPending] = useState(false);
  const [bootError, setBootError] = useState<string | null>(null);

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

  function handleUploaded(newTables: TableSchema[]) {
    setTables((prev) => {
      const byName = new Map(prev.map((t) => [t.name, t]));
      for (const t of newTables) byName.set(t.name, t);
      return Array.from(byName.values());
    });
  }

  async function handleSend(question: string) {
    if (!sessionId) return;
    setPending(true);
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
        <p className="max-w-md text-center text-sm text-destructive">{bootError}</p>
      </div>
    );
  }

  const hasTables = tables.length > 0;

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-background">
      <header className="flex shrink-0 items-center justify-between border-b border-border px-4 py-3 sm:px-6">
        <div className="flex items-center gap-3">
          {hasTables && (
            <Sheet>
              <SheetTrigger
                render={
                  <Button variant="outline" size="icon" className="md:hidden" aria-label="Open data manifest" />
                }
              >
                <Menu className="size-4" />
              </SheetTrigger>
              <SheetContent side="left" className="w-full max-w-xs p-0">
                <SheetTitle className="sr-only">Data manifest</SheetTitle>
                {sessionId && (
                  <DataManifestRail sessionId={sessionId} tables={tables} onUploaded={handleUploaded} />
                )}
              </SheetContent>
            </Sheet>
          )}
          <div>
            <h1 className="font-heading text-xl font-semibold text-foreground">Table Talk</h1>
            <p className="hidden text-sm text-muted-foreground sm:block">
              Upload CSVs and ask questions in plain English.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <ThemeToggle />
        </div>
      </header>

      {!hasTables && sessionId && (
        <EmptyStateHero sessionId={sessionId} onUploaded={handleUploaded} />
      )}

      {hasTables && (
        <main className="flex min-h-0 flex-1 flex-col md:flex-row">
          <aside className="hidden min-w-0 shrink-0 overflow-hidden border-r border-border md:flex md:w-64 lg:w-72 xl:w-80">
            {sessionId && (
              <DataManifestRail sessionId={sessionId} tables={tables} onUploaded={handleUploaded} />
            )}
          </aside>
          <section className="min-h-0 min-w-0 flex-1 overflow-hidden">
            <ChatPanel messages={messages} onSend={handleSend} disabled={!sessionId} pending={pending} />
          </section>
        </main>
      )}
    </div>
  );
}
