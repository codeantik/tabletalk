"use client";

import { Rows3, Table2 } from "lucide-react";
import type { TableSchema } from "@/lib/api";

interface TablesSidebarProps {
  tables: TableSchema[];
}

export default function TablesSidebar({ tables }: TablesSidebarProps) {
  if (tables.length === 0) {
    return (
      <p className="text-base text-muted-foreground">
        No files loaded yet. Upload CSVs to start asking questions.
      </p>
    );
  }

  return (
    <ul className="flex flex-col gap-2">
      {tables.map((table) => (
        <li
          key={table.name}
          className="rounded-md border border-border bg-card px-3.5 py-3 text-sm"
        >
          <div className="flex items-center gap-1.5">
            <Table2 className="size-4 shrink-0 text-primary" />
            <p className="truncate font-mono text-sm font-medium text-foreground">{table.name}</p>
          </div>
          <p className="mt-1 flex items-center gap-1 text-sm text-muted-foreground">
            <Rows3 className="size-3.5 shrink-0" />
            {table.source_filename} &middot; {table.row_count.toLocaleString()} rows
          </p>
          <p className="mt-1 truncate font-mono text-xs text-muted-foreground/80">
            {table.columns.map((c) => c.name).join(", ")}
          </p>
        </li>
      ))}
    </ul>
  );
}
