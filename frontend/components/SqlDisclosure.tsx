"use client";

import { useState } from "react";

interface SqlDisclosureProps {
  sql: string;
}

export default function SqlDisclosure({ sql }: SqlDisclosureProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen((v) => !v)}
        className="text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400"
      >
        {open ? "Hide query" : "Show query"}
      </button>
      {open && (
        <pre className="mt-1 overflow-x-auto rounded-lg bg-zinc-100 px-3 py-2 text-xs text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300">
          {sql}
        </pre>
      )}
    </div>
  );
}
