"use client";

import FileUpload from "@/components/FileUpload";
import TablesSidebar from "@/components/TablesSidebar";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { TableSchema } from "@/lib/api";

interface DataManifestRailProps {
  sessionId: string;
  tables: TableSchema[];
  onUploaded: (tables: TableSchema[]) => void;
}

export default function DataManifestRail({ sessionId, tables, onUploaded }: DataManifestRailProps) {
  return (
    <div className="flex h-full w-full min-w-0 flex-col gap-4 p-4">
      <FileUpload sessionId={sessionId} onUploaded={onUploaded} variant="compact" />
      <div className="flex min-h-0 flex-1 flex-col gap-2">
        <h2 className="font-mono text-sm font-semibold tracking-widest text-muted-foreground uppercase">
          Data manifest &middot; {tables.length} table{tables.length === 1 ? "" : "s"}
        </h2>
        <ScrollArea className="min-h-0 flex-1">
          <TablesSidebar tables={tables} />
        </ScrollArea>
      </div>
    </div>
  );
}
