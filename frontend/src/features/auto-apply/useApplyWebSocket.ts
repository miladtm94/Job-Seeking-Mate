import { useCallback, useRef, useState } from "react";

const WS_BASE = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1")
  .replace(/^http/, "ws")
  .replace("/api/v1", "");  // WebSocket is at root, not under /api/v1

export type EventType = "progress" | "confirm" | "screenshot" | "success" | "error";

export interface ApplyEvent {
  type: EventType;
  // progress
  step?: string;
  message?: string;
  // confirm
  field?: string;
  label?: string;
  suggestion?: string;
  confidence?: number;
  // screenshot
  data?: string;  // base64 JPEG
}

export type SessionState =
  | "idle"
  | "connecting"
  | "running"
  | "waiting_confirm"
  | "success"
  | "error"
  | "cancelled";

export interface UseApplyWebSocketReturn {
  state: SessionState;
  events: ApplyEvent[];
  pendingConfirm: ApplyEvent | null;
  screenshot: string | null;   // latest base64 screenshot
  start: (sessionId: string, payload: object) => void;
  confirm: () => void;
  edit: (value: string) => void;
  cancel: () => void;
  reset: () => void;
}

export function useApplyWebSocket(): UseApplyWebSocketReturn {
  const wsRef = useRef<WebSocket | null>(null);
  const [state, setState] = useState<SessionState>("idle");
  const [events, setEvents] = useState<ApplyEvent[]>([]);
  const [pendingConfirm, setPendingConfirm] = useState<ApplyEvent | null>(null);
  const [screenshot, setScreenshot] = useState<string | null>(null);

  const appendEvent = useCallback((ev: ApplyEvent) => {
    setEvents((prev) => [...prev, ev]);
  }, []);

  const send = useCallback((msg: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  const start = useCallback((sessionId: string, payload: object) => {
    // Close any existing connection
    wsRef.current?.close();
    setEvents([]);
    setPendingConfirm(null);
    setScreenshot(null);
    setState("connecting");

    const ws = new WebSocket(`${WS_BASE}/ws/apply/${sessionId}`);
    wsRef.current = ws;

    ws.onopen = () => {
      setState("running");
      ws.send(JSON.stringify(payload));
    };

    ws.onmessage = (evt) => {
      const ev: ApplyEvent = JSON.parse(evt.data);

      if (ev.type === "screenshot") {
        setScreenshot(ev.data ?? null);
        return;  // don't add screenshots to event log
      }

      appendEvent(ev);

      if (ev.type === "confirm") {
        setState("waiting_confirm");
        setPendingConfirm(ev);
      } else if (ev.type === "success") {
        setState("success");
        setPendingConfirm(null);
      } else if (ev.type === "error") {
        setState("error");
        setPendingConfirm(null);
      }
    };

    ws.onerror = () => {
      appendEvent({ type: "error", message: "WebSocket connection failed" });
      setState("error");
    };

    ws.onclose = () => {
      if (state !== "success" && state !== "error" && state !== "cancelled") {
        setState("idle");
      }
    };
  }, [appendEvent, state]);

  const confirm = useCallback(() => {
    send({ action: "confirm" });
    setPendingConfirm(null);
    setState("running");
  }, [send]);

  const edit = useCallback((value: string) => {
    send({ action: "edit", value });
    setPendingConfirm(null);
    setState("running");
  }, [send]);

  const cancel = useCallback(() => {
    send({ action: "cancel" });
    wsRef.current?.close();
    setState("cancelled");
    setPendingConfirm(null);
  }, [send]);

  const reset = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    setState("idle");
    setEvents([]);
    setPendingConfirm(null);
    setScreenshot(null);
  }, []);

  return { state, events, pendingConfirm, screenshot, start, confirm, edit, cancel, reset };
}
