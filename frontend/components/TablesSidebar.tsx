"use client";

import type { TableSchema } from "@/lib/api";

interface TablesSidebarProps {
  tables: TableSchema[];
}

export default function TablesSidebar({ tables }: TablesSidebarProps) {
  if (tables.length === 0) {
    return (
      <p className="text-sm text-zinc-500 dark:text-zinc-400">
        No files loaded yet. Upload CSVs to start asking questions.
      </p>
    );
  }

  return (
    <ul className="flex flex-col gap-3">
      {tables.map((table) => (
        <li
          key={table.name}
          className="rounded-lg border border-zinc-200 px-3 py-2 text-sm dark:border-zinc-800"
        >
          <p className="font-mono font-medium text-zinc-800 dark:text-zinc-100">
            {table.name}
          </p>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            {table.source_filename} · {table.row_count.toLocaleString()} rows
          </p>
          <p className="mt-1 truncate text-xs text-zinc-400 dark:text-zinc-500">
            {table.columns.map((c) => c.name).join(", ")}
          </p>
        </li>
      ))}
    </ul>
  );
}
