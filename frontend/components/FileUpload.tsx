"use client";

import { useRef, useState } from "react";
import { AlertCircle, CheckCircle2, UploadCloud } from "lucide-react";
import { ApiError, uploadCsvFiles, type TableSchema } from "@/lib/api";

const MAX_FILE_SIZE_MB = 50;

interface FileUploadProps {
  sessionId: string;
  onUploaded: (tables: TableSchema[]) => void;
  variant?: "hero" | "compact";
}

function validateFiles(files: File[]): string | null {
  if (files.length === 0) return "Select at least one CSV file.";
  for (const file of files) {
    if (!file.name.toLowerCase().endsWith(".csv")) {
      return `"${file.name}" is not a .csv file.`;
    }
    if (file.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
      return `"${file.name}" exceeds the ${MAX_FILE_SIZE_MB}MB upload limit.`;
    }
  }
  return null;
}

export default function FileUpload({ sessionId, onUploaded, variant = "hero" }: FileUploadProps) {
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileErrors, setFileErrors] = useState<
    { filename: string; detail: string }[] | null
  >(null);
  const [lastUploaded, setLastUploaded] = useState<TableSchema[] | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFiles(fileList: FileList | null) {
    if (!fileList) return;
    const files = Array.from(fileList);
    const validationError = validateFiles(files);
    if (validationError) {
      setError(validationError);
      setFileErrors(null);
      return;
    }

    setError(null);
    setFileErrors(null);
    setUploading(true);
    try {
      const result = await uploadCsvFiles(sessionId, files);
      setLastUploaded(result.tables);
      onUploaded(result.tables);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        setFileErrors(err.errors ?? null);
      } else {
        setError("Upload failed. Please try again.");
      }
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  const isHero = variant === "hero";

  return (
    <div className="flex flex-col gap-3">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragActive(false);
          handleFiles(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
        }}
        role="button"
        tabIndex={0}
        aria-label="Upload CSV files"
        className={`group flex cursor-pointer flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed text-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background ${
          isHero ? "px-5 py-9 sm:px-8 sm:py-12" : "px-4 py-6"
        } ${
          dragActive
            ? "border-primary bg-primary/5"
            : "border-border hover:border-primary/60 hover:bg-muted/40"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          multiple
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
        <UploadCloud
          className={`${isHero ? "size-9" : "size-6"} text-muted-foreground transition-colors group-hover:text-primary`}
        />
        <span className={`font-medium text-foreground ${isHero ? "text-base" : "text-sm"}`}>
          {uploading ? "Uploading…" : "Drop CSV files here, or click to browse"}
        </span>
        <span className="text-sm text-muted-foreground">
          Multiple files supported &middot; up to {MAX_FILE_SIZE_MB}MB each
        </span>
      </div>

      {error && (
        <div className="flex gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3.5 py-2.5 text-sm text-destructive">
          <AlertCircle className="mt-0.5 size-4 shrink-0" />
          <div>
            {error}
            {fileErrors && (
              <ul className="mt-1 list-disc pl-4">
                {fileErrors.map((fe) => (
                  <li key={fe.filename}>
                    <span className="font-medium">{fe.filename}:</span> {fe.detail}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {lastUploaded && lastUploaded.length > 0 && (
        <div className="flex gap-2 rounded-md border border-positive/30 bg-positive/10 px-3.5 py-2.5 text-sm text-positive-foreground dark:text-positive">
          <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-positive" />
          <div>
            <p className="font-medium text-foreground">Loaded {lastUploaded.length} file(s)</p>
            <ul className="mt-1 space-y-0.5 text-sm text-muted-foreground">
              {lastUploaded.map((t) => (
                <li key={t.name}>
                  {t.source_filename} &rarr; <span className="font-mono">{t.name}</span> (
                  {t.row_count.toLocaleString()} rows, {t.columns.length} cols)
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
