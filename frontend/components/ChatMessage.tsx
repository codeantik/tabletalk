"use client";

import type { MessageResponse } from "@/lib/api";
import ChartView from "@/components/ChartView";
import TableView from "@/components/TableView";
import SqlDisclosure from "@/components/SqlDisclosure";

interface ChatMessageProps {
  message: MessageResponse;
}

export default function ChatMessage({ message }: ChatMessageProps) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex justify-end">
        <div className="flex max-w-[85%] items-start gap-2 rounded-sm border border-primary/30 bg-primary/10 px-3.5 py-2.5 text-base text-foreground">
          <span className="mt-1 font-mono text-xs font-semibold tracking-widest text-primary uppercase">
            Q
          </span>
          <span>{message.question}</span>
        </div>
      </div>

      <div className="rounded-md border border-border border-l-2 border-l-accent bg-card px-4 py-3.5 text-base text-foreground sm:px-5">
        {message.error ? (
          <p className="text-destructive">{message.error}</p>
        ) : (
          <>
            {message.text && <p className="leading-relaxed">{message.text}</p>}
            {message.chart && (
              <div className="mt-3 min-w-0 animate-in fade-in slide-in-from-bottom-1 duration-500 motion-reduce:animate-none">
                <ChartView chart={message.chart} />
              </div>
            )}
            {message.table && (
              <div className="mt-3 min-w-0">
                <TableView table={message.table} />
              </div>
            )}
            {message.row_limit_applied && (
              <p className="mt-1.5 font-mono text-xs text-muted-foreground">
                Result truncated to the row limit.
              </p>
            )}
          </>
        )}
        {message.sql_used && <SqlDisclosure sql={message.sql_used} />}
      </div>
    </div>
  );
}
