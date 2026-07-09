"use client";

import type { TableResponse } from "@/lib/api";

interface TableViewProps {
  table: TableResponse;
}

export default function TableView({ table }: TableViewProps) {
  return (
    <div className="max-h-80 overflow-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
      <table className="min-w-full text-left text-sm">
        <thead className="sticky top-0 bg-zinc-100 dark:bg-zinc-900">
          <tr>
            {table.columns.map((col) => (
              <th
                key={col}
                className="whitespace-nowrap px-3 py-2 font-medium text-zinc-600 dark:text-zinc-300"
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, i) => (
            <tr
              key={i}
              className="border-t border-zinc-100 odd:bg-white even:bg-zinc-50 dark:border-zinc-800 dark:odd:bg-zinc-950 dark:even:bg-zinc-900"
            >
              {row.map((cell, j) => (
                <td key={j} className="whitespace-nowrap px-3 py-1.5 text-zinc-700 dark:text-zinc-300">
                  {cell === null ? (
                    <span className="text-zinc-400 italic dark:text-zinc-600">null</span>
                  ) : (
                    String(cell)
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
