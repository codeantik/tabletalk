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
      <div className="ml-auto max-w-[80%] rounded-2xl rounded-br-sm bg-indigo-600 px-4 py-2 text-sm text-white">
        {message.question}
      </div>

      <div className="mr-auto max-w-[80%] rounded-2xl rounded-bl-sm bg-zinc-100 px-4 py-3 text-sm text-zinc-800 dark:bg-zinc-900 dark:text-zinc-100">
        {message.error ? (
          <p className="text-red-600 dark:text-red-400">{message.error}</p>
        ) : (
          <>
            {message.text && <p>{message.text}</p>}
            {message.chart && (
              <div className="mt-3 min-w-[20rem]">
                <ChartView chart={message.chart} />
              </div>
            )}
            {message.table && (
              <div className="mt-3 min-w-[20rem]">
                <TableView table={message.table} />
              </div>
            )}
            {message.row_limit_applied && (
              <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-500">
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
