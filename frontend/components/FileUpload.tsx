"use client";

import { useRef, useState } from "react";
import { ApiError, uploadCsvFiles, type TableSchema } from "@/lib/api";

const MAX_FILE_SIZE_MB = 50;

interface FileUploadProps {
  sessionId: string;
  onUploaded: (tables: TableSchema[]) => void;
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

export default function FileUpload({ sessionId, onUploaded }: FileUploadProps) {
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
        className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors ${
          dragActive
            ? "border-indigo-500 bg-indigo-50 dark:bg-indigo-950/40"
            : "border-zinc-300 hover:border-indigo-400 dark:border-zinc-700"
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
        <span className="text-sm font-medium text-zinc-700 dark:text-zinc-200">
          {uploading ? "Uploading…" : "Drop CSV files here, or click to browse"}
        </span>
        <span className="text-xs text-zinc-500 dark:text-zinc-400">
          Multiple files supported · up to {MAX_FILE_SIZE_MB}MB each
        </span>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/50 dark:text-red-300">
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
      )}

      {lastUploaded && lastUploaded.length > 0 && (
        <div className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200">
          <p className="font-medium">Loaded {lastUploaded.length} file(s):</p>
          <ul className="mt-1 space-y-0.5">
            {lastUploaded.map((t) => (
              <li key={t.name}>
                {t.source_filename} &rarr;{" "}
                <span className="font-mono">{t.name}</span> ({t.row_count.toLocaleString()} rows,{" "}
                {t.columns.length} cols)
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
