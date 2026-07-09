const SESSION_KEY = "table-talk:session-id";

export function loadStoredSessionId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(SESSION_KEY);
}

export function storeSessionId(sessionId: string): void {
  window.localStorage.setItem(SESSION_KEY, sessionId);
}

export function clearStoredSessionId(): void {
  window.localStorage.removeItem(SESSION_KEY);
}
