export type AgentTask = {
  id: number; idx: number; title: string; instructions: string; action: string | null;
  status: string; output: string | null; review: string | null; attempts: number; error: string | null;
};
export type AgentApproval = { id: number; task_id: number; action: string; detail: string; status: 'pending' | 'approved' | 'rejected' };
export type AgentEvent = { id: number; run_id: number; ts: number; kind: string; detail: string };
export type AgentRunSummary = { id: number; goal: string; status: string; error: string | null; created: number; updated: number };
export type AgentRun = {
  id: number; goal: string; status: string; result: string | null; error: string | null;
  tasks: AgentTask[]; approvals: AgentApproval[]; events: AgentEvent[];
};
const API = import.meta.env.VITE_API_BASE ?? '';
async function request<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}`, ...(init.headers ?? {}) },
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : `Falha na API (${response.status})`);
  }
  return response.json() as Promise<T>;
}
export const listAgentRuns = (token: string) => request<{ runs: AgentRunSummary[] }>('/api/agent-runs', token).then(r => r.runs);
export const getAgentRun = (id: number, token: string) => request<AgentRun>(`/api/agent-runs/${id}`, token);
export const createAgentRun = (goal: string, token: string) => request<AgentRun>('/api/agent-runs', token, { method: 'POST', body: JSON.stringify({ goal }) });
export const retryAgentRun = (id: number, token: string) => request<AgentRun>(`/api/agent-runs/${id}/retry`, token, { method: 'POST' });
export const decideAgentApproval = (id: number, approve: boolean, token: string) =>
  request<AgentRun>(`/api/agent-approvals/${id}/decision`, token, { method: 'POST', body: JSON.stringify({ approve }) });
