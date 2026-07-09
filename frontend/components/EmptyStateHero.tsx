"use client";

import SchemaGraphBackdrop from "@/components/SchemaGraphBackdrop";
import FileUpload from "@/components/FileUpload";
import type { TableSchema } from "@/lib/api";

interface EmptyStateHeroProps {
  sessionId: string;
  onUploaded: (tables: TableSchema[]) => void;
}

export default function EmptyStateHero({ sessionId, onUploaded }: EmptyStateHeroProps) {
  return (
    <div className="relative flex flex-1 items-center justify-center overflow-hidden px-4 py-12 sm:px-8">
      <SchemaGraphBackdrop />
      <div className="relative z-10 mx-auto flex w-full max-w-xl flex-col items-center gap-6 text-center">
        <div className="flex flex-col gap-3">
          <span className="font-mono text-sm tracking-widest text-primary uppercase">
            Manifest &middot; Table Talk
          </span>
          <h1 className="font-heading text-4xl font-semibold text-balance text-foreground sm:text-5xl">
            Talk to your data.
          </h1>
          <p className="text-base text-balance text-muted-foreground sm:text-lg">
            Upload your customers, orders, order_items, products, payment, shipments,
            reviews, and suppliers CSVs. We&apos;ll chart the joins and let you ask
            questions in plain English.
          </p>
        </div>
        <div className="w-full rounded-lg border border-border bg-card/80 p-4 backdrop-blur-sm sm:p-5">
          <FileUpload sessionId={sessionId} onUploaded={onUploaded} variant="hero" />
        </div>
      </div>
    </div>
  );
}
