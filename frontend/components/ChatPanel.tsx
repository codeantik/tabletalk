"use client";

import { useEffect, useRef, useState } from "react";
import type { MessageResponse } from "@/lib/api";
import ChatMessage from "@/components/ChatMessage";

interface ChatPanelProps {
  messages: MessageResponse[];
  onSend: (question: string) => Promise<void>;
  disabled: boolean;
  pending: boolean;
}

export default function ChatPanel({
  messages,
  onSend,
  disabled,
  pending,
}: ChatPanelProps) {
  const [question, setQuestion] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, pending]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || pending) return;
    setQuestion("");
    await onSend(trimmed);
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {messages.length === 0 && (
          <p className="mt-8 text-center text-sm text-zinc-400 dark:text-zinc-500">
            {disabled
              ? "Upload CSV files to start asking questions."
              : "Ask a question about your data, e.g. \"What's total revenue in 2024?\""}
          </p>
        )}
        {messages.map((m, i) => (
          <ChatMessage key={i} message={m} />
        ))}
        {pending && (
          <div className="mr-auto max-w-[80%] rounded-2xl rounded-bl-sm bg-zinc-100 px-4 py-3 text-sm text-zinc-400 dark:bg-zinc-900 dark:text-zinc-500">
            Thinking…
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={handleSubmit}
        className="flex items-center gap-2 border-t border-zinc-200 px-4 py-3 dark:border-zinc-800"
      >
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={disabled || pending}
          placeholder={
            disabled ? "Upload data to begin…" : "Ask a question about your data…"
          }
          className="flex-1 rounded-full border border-zinc-300 bg-white px-4 py-2 text-sm outline-none focus:border-indigo-500 disabled:cursor-not-allowed disabled:opacity-60 dark:border-zinc-700 dark:bg-zinc-950"
        />
        <button
          type="submit"
          disabled={disabled || pending || !question.trim()}
          className="rounded-full bg-indigo-600 px-5 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  );
}
