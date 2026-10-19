export type HumanTaskStatus = 'awaiting_approval' | 'open' | 'in_progress' | 'blocked' | 'done' | 'rejected' | 'cancelled';
export type HumanTaskPriority = 'low' | 'normal' | 'high' | 'urgent';

export type HumanTask = {
  id: string;
  title: string;
  description: string;
  status: HumanTaskStatus;
  priority: HumanTaskPriority;
  owner: string | null;
  due_at: string | null;
  dependencies: string[];
  evidence: string[];
  requires_approval: boolean;
  approved_scope: string | null;
  completion_note: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
};

const API = import.meta.env.VITE_API_BASE ?? '';

async function request<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...(init.headers ?? {}),
    },
  });
  if (!response.ok) {
    let message = `Solicitação falhou (${response.status})`;
    try { message = (await response.json()).detail ?? message; } catch { /* Keep status fallback. */ }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export async function listHumanTasks(token: string): Promise<HumanTask[]> {
  const result = await request<{tasks: HumanTask[]}>('/api/human-tasks', token);
  return result.tasks;
}

export async function createHumanTask(token: string, payload: {
  title: string; description: string; owner?: string | null;
  priority: HumanTaskPriority; requires_approval: boolean;
}) {
  const result = await request<{task: HumanTask}>('/api/human-tasks', token, {
    method: 'POST', body: JSON.stringify(payload),
  });
  return result.task;
}

export async function decideHumanTask(token: string, id: string, decision: 'approve' | 'reject', scope: string) {
  const result = await request<{task: HumanTask}>(`/api/human-tasks/${encodeURIComponent(id)}/decision`, token, {
    method: 'POST',
    body: JSON.stringify({ decision, scope, note: 'Decisão registrada pelo painel; nenhuma ação externa foi executada.' }),
  });
  return result.task;
}

export async function changeHumanTaskStatus(token: string, id: string, status: 'open' | 'in_progress' | 'blocked' | 'cancelled') {
  const result = await request<{task: HumanTask}>(`/api/human-tasks/${encodeURIComponent(id)}/status`, token, {
    method: 'POST', body: JSON.stringify({ status, note: 'Atualização manual pelo painel.' }),
  });
  return result.task;
}

export async function completeHumanTask(token: string, id: string) {
  const result = await request<{task: HumanTask}>(`/api/human-tasks/${encodeURIComponent(id)}/complete`, token, {
    method: 'POST', body: JSON.stringify({ note: 'Conclusão registrada manualmente no painel.' }),
  });
  return result.task;
}
