"use client";

import type { TableResponse } from "@/lib/api";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

interface TableViewProps {
  table: TableResponse;
}

function isNumeric(value: unknown): boolean {
  return typeof value === "number";
}

export default function TableView({ table }: TableViewProps) {
  return (
    <div className="max-h-80 overflow-auto rounded-md border border-border">
      <Table>
        <TableHeader className="sticky top-0 z-10 bg-muted">
          <TableRow className="hover:bg-transparent">
            {table.columns.map((col) => (
              <TableHead key={col} className="font-mono text-sm whitespace-nowrap text-muted-foreground">
                {col}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {table.rows.map((row, i) => (
            <TableRow key={i}>
              {row.map((cell, j) => (
                <TableCell
                  key={j}
                  className={`whitespace-nowrap text-sm ${
                    isNumeric(cell) ? "font-mono tabular-nums text-foreground" : "text-foreground"
                  }`}
                >
                  {cell === null ? (
                    <span className="font-mono text-muted-foreground italic">null</span>
                  ) : (
                    String(cell)
                  )}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
