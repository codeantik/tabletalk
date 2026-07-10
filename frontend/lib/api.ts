export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  errors?: { filename: string; detail: string }[];

  constructor(
    status: number,
    message: string,
    errors?: { filename: string; detail: string }[],
  ) {
    super(message);
    this.status = status;
    this.errors = errors;
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (res.ok) return (await res.json()) as T;

  let message = `Request failed (${res.status})`;
  let errors: { filename: string; detail: string }[] | undefined;
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") {
      message = body.detail;
    } else if (body?.detail?.message) {
      message = body.detail.message;
      errors = body.detail.errors;
    }
  } catch {
    // response had no JSON body; keep the generic message
  }
  throw new ApiError(res.status, message, errors);
}

export interface SessionResponse {
  session_id: string;
  created_at: string;
  expires_at: string;
}

export interface ColumnSchema {
  name: string;
  type: string;
  missing_count: number;
  missing_pct: number;
  outlier_count: number | null;
  coerced_from: string | null;
}

export interface TableSchema {
  name: string;
  source_filename: string;
  row_count: number;
  columns: ColumnSchema[];
}

export interface UploadResponse {
  session_id: string;
  tables: TableSchema[];
}

export interface TablesResponse {
  session_id: string;
  tables: TableSchema[];
}

export interface ChartSeriesPoint {
  name: string;
  value: number;
}

export interface ChartDataPoint {
  x: string;
  series: ChartSeriesPoint[];
}

export interface ChartResponse {
  type: "chart:line" | "chart:bar" | "chart:pie";
  data: ChartDataPoint[];
}

export interface TableResponse {
  columns: string[];
  rows: unknown[][];
}

export interface MessageResponse {
  session_id: string;
  question: string;
  created_at: string;
  sql_used: string | null;
  intent: string | null;
  text: string | null;
  chart: ChartResponse | null;
  table: TableResponse | null;
  error: string | null;
  row_limit_applied: boolean;
}

export interface MessagesHistoryResponse {
  session_id: string;
  messages: MessageResponse[];
}

export async function createSession(): Promise<SessionResponse> {
  const res = await fetch(`${API_BASE_URL}/api/sessions`, { method: "POST" });
  return handleResponse<SessionResponse>(res);
}

export async function uploadCsvFiles(
  sessionId: string,
  files: File[],
): Promise<UploadResponse> {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  const res = await fetch(`${API_BASE_URL}/api/sessions/${sessionId}/upload`, {
    method: "POST",
    body: form,
  });
  return handleResponse<UploadResponse>(res);
}

export async function getTables(sessionId: string): Promise<TablesResponse> {
  const res = await fetch(`${API_BASE_URL}/api/sessions/${sessionId}/tables`);
  return handleResponse<TablesResponse>(res);
}

export async function postMessage(
  sessionId: string,
  question: string,
): Promise<MessageResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/sessions/${sessionId}/messages`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    },
  );
  return handleResponse<MessageResponse>(res);
}

export async function getMessages(
  sessionId: string,
): Promise<MessagesHistoryResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/sessions/${sessionId}/messages`,
  );
  return handleResponse<MessagesHistoryResponse>(res);
}
