/**
 * NXT1 — AgentOS API client (Phase 22)
 */
import api from "@/lib/api";
import { getToken } from "@/lib/auth";

export const listAgents       = () => api.get("/agentos/agents");
export const listAgentTasks   = (params = {}) => api.get("/agentos/tasks", { params });
export const getAgentTask     = (id) => api.get(`/agentos/tasks/${id}`);
export const submitAgentTask  = (agent, payload, label = null) =>
  api.post("/agentos/tasks", { agent, payload, label });
export const cancelAgentTask  = (id) => api.post(`/agentos/tasks/${id}/cancel`);
export const agentosStats     = () => api.get("/agentos/stats");

/** Upload a resume file (PDF / DOCX / TXT) and get back extracted text. */
export const extractResumeFile = (file) => {
  const fd = new FormData();
  fd.append("file", file);
  return api.post("/agentos/resume/extract", fd, {
    headers: { "Content-Type": "multipart/form-data" },
  });
};

/** Open a WebSocket subscribed to live task events. */
export function openAgentTaskWS(taskId, onEvent) {
  const base = (process.env.REACT_APP_BACKEND_URL || "")
    .replace(/^http/, "ws");
  const url = `${base}/api/agentos/ws/tasks/${taskId}?token=${encodeURIComponent(getToken())}`;
  const ws = new WebSocket(url);
  ws.onmessage = (m) => {
    try { onEvent(JSON.parse(m.data)); } catch { /* ignore */ }
  };
  ws.onerror = (e) => console.warn("agentos WS error", e);
  return ws;
}
