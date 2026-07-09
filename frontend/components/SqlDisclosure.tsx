"use client";

import { Code2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

interface SqlDisclosureProps {
  sql: string;
}

export default function SqlDisclosure({ sql }: SqlDisclosureProps) {
  return (
    <Dialog>
      <DialogTrigger
        render={
          <Button
            variant="ghost"
            size="sm"
            className="mt-2 h-auto gap-1 px-0 font-mono text-xs text-muted-foreground hover:bg-transparent hover:text-primary"
          />
        }
      >
        <Code2 className="size-3" />
        View query
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="font-mono">Generated SQL</DialogTitle>
          <DialogDescription>
            The exact, validated read-only query executed for this answer.
          </DialogDescription>
        </DialogHeader>
        <pre className="max-h-80 overflow-auto rounded-md border border-border bg-muted/40 p-3 font-mono text-sm text-foreground">
          {sql}
        </pre>
      </DialogContent>
    </Dialog>
  );
}
