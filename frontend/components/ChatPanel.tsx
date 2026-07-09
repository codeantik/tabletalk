"use client";

import { useEffect, useRef, useState } from "react";
import { SendHorizontal } from "lucide-react";
import type { MessageResponse } from "@/lib/api";
import ChatMessage from "@/components/ChatMessage";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

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
      <div className="mx-auto w-full max-w-4xl flex-1 space-y-4 overflow-y-auto px-4 py-4 sm:px-6 lg:px-8">
        {messages.length === 0 && (
          <p className="mt-8 text-center text-base text-muted-foreground">
            {disabled
              ? "Upload CSV files to start asking questions."
              : 'Ask a question about your data, e.g. "What\'s total revenue in 2024?"'}
          </p>
        )}
        {messages.map((m, i) => (
          <ChatMessage key={i} message={m} />
        ))}
        {pending && (
          <div className="flex flex-col gap-2 rounded-md border border-border border-l-2 border-l-accent bg-card px-4 py-3.5">
            <Skeleton className="h-3.5 w-3/4" />
            <Skeleton className="h-3.5 w-1/2" />
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={handleSubmit}
        className="border-t border-border px-4 py-3 sm:px-6 lg:px-8"
      >
        <div className="mx-auto flex w-full max-w-4xl items-center gap-2">
          <Input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            disabled={disabled || pending}
            placeholder={disabled ? "Upload data to begin…" : "Ask a question about your data…"}
            className="h-11 flex-1 text-base"
          />
          <Button
            type="submit"
            disabled={disabled || pending || !question.trim()}
            size="lg"
            aria-label="Send question"
          >
            <SendHorizontal className="size-4" />
            <span className="hidden sm:inline">Send</span>
          </Button>
        </div>
      </form>
    </div>
  );
}
