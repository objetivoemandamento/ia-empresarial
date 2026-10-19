export type Language = 'pt' | 'en' | 'zh' | 'es' | 'hi';
export type Skill = {
  id: string; name: string; version: string; description: string;
  status: 'pending_review' | 'active' | 'rejected'; languages: Language[]; tools: string[];
};
const API = import.meta.env.VITE_API_BASE ?? ''; // In dev, Vite proxies /api to FastAPI.

export async function checkHealth(): Promise<{
  ok: boolean; language_default: Language; supported_languages: Language[];
  llm_ready: boolean; llm_mode: 'configured' | 'demo'; llm_model: string | null;
  transcription_ready: boolean;
}> {
  const r = await fetch(`${API}/api/health`);
  if (!r.ok) throw new Error(`API indisponível (${r.status})`);
  return r.json();
}

export async function listSkills(): Promise<Skill[]> {
  const r = await fetch(`${API}/api/repositories`);
  if (!r.ok) throw new Error(`Não foi possível listar skills (${r.status})`);
  return (await r.json()).skills;
}
export async function uploadSkill(file: File, token: string): Promise<Skill> {
  const body = new FormData(); body.append('file', file);
  const r = await fetch(`${API}/api/repositories/upload`, {
    method: 'POST', headers: { Authorization: `Bearer ${token}` }, body,
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? `Upload falhou (${r.status})`);
  return (await r.json()).skill;
}
export async function moderateSkill(id: string, action: 'approve' | 'reject', token: string): Promise<Skill> {
  const r = await fetch(`${API}/api/repositories/${encodeURIComponent(id)}/${action}`, {
    method: 'POST', headers: { Authorization: `Bearer ${token}` },
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? `Ação falhou (${r.status})`);
  return (await r.json()).skill;
}
export async function sendChat(messages: {role:'user'|'assistant';content:string}[], language: Language | null, skill_ids: string[]) {
  const r = await fetch(`${API}/api/chat`, {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({messages, language, skill_ids}),
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? `Chat falhou (${r.status})`);
  return r.json() as Promise<{answer:string; language:Language; active_skills:string[]; provider:string}>;
}
export async function transcribe(file: Blob, language: Language): Promise<string> {
  const body = new FormData();
  body.append('file', file, 'recording.webm'); body.append('language', language);
  const r = await fetch(`${API}/api/audio/transcribe`, {method:'POST', body});
  if (!r.ok) throw new Error((await r.json()).detail ?? `Transcrição falhou (${r.status})`);
  return (await r.json()).text as string;
}
