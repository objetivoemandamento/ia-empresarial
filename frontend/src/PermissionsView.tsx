import { useEffect, useState } from 'react';

type Policies = {
  voice_enabled: boolean;
  approved_skills_enabled: boolean;
  prime_sandbox_enabled: boolean;
  external_network_enabled: boolean;
  optional_telemetry_enabled: boolean;
  protected_controls: { key: string; title: string; enabled: true }[];
};
const API = import.meta.env.VITE_API_BASE ?? '';
const OPTIONAL: { key: keyof Omit<Policies, 'protected_controls'>; title: string; description: string }[] = [
  { key: 'voice_enabled', title: 'Recursos de voz', description: 'Permite gravação e transcrição de áudio.' },
  { key: 'approved_skills_enabled', title: 'Capacidades aprovadas', description: 'Permite instalar, moderar e utilizar skills declarativas aprovadas.' },
  { key: 'external_network_enabled', title: 'Rede externa para agentes', description: 'Mantida desativada por padrão; não cria um executor de rede por si só.' },
  { key: 'prime_sandbox_enabled', title: 'Sandbox de código', description: 'Mantido desativado até existir um executor isolado validado.' },
  { key: 'optional_telemetry_enabled', title: 'Telemetria opcional', description: 'Controle de telemetria não essencial.' },
];
const boxStyle = { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 14, padding: 18, marginBottom: 12 } as const;

export function PermissionsView({ token }: { token: string }) {
  const [policies, setPolicies] = useState<Policies | null>(null);
  const [draft, setDraft] = useState<Partial<Policies>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  async function load() {
    try {
      const r = await fetch(`${API}/api/policies`);
      if (!r.ok) throw new Error(`Não foi possível carregar permissões (${r.status})`);
      const data = await r.json() as Policies;
      setPolicies(data);
      setDraft({
        voice_enabled: data.voice_enabled,
        approved_skills_enabled: data.approved_skills_enabled,
        prime_sandbox_enabled: data.prime_sandbox_enabled,
        external_network_enabled: data.external_network_enabled,
        optional_telemetry_enabled: data.optional_telemetry_enabled,
      });
      setError('');
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }
  useEffect(() => { void load(); }, []);

  async function save() {
    if (!token.trim()) { setError('Informe o token administrativo no painel Capacidades da tela inicial para salvar permissões.'); return; }
    setBusy(true); setNotice(''); setError('');
    try {
      const r = await fetch(`${API}/api/policies`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(draft),
      });
      if (!r.ok) { const data = await r.json().catch(() => ({})); throw new Error(data.detail ?? `Falha ao salvar (${r.status})`); }
      const data = await r.json() as Policies;
      setPolicies(data);
      setDraft({
        voice_enabled: data.voice_enabled,
        approved_skills_enabled: data.approved_skills_enabled,
        prime_sandbox_enabled: data.prime_sandbox_enabled,
        external_network_enabled: data.external_network_enabled,
        optional_telemetry_enabled: data.optional_telemetry_enabled,
      });
      setNotice('Permissões salvas no backend.');
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  return <section style={{ paddingBottom: 30 }}>
    <div style={{ marginBottom: 20 }}><span className="section-kicker">CONTROLES ADMINISTRATIVOS</span><h2 style={{ fontFamily: 'Space Grotesk', fontSize: 28, margin: '8px 0' }}>Permissões</h2><p style={{ color: 'var(--muted)', lineHeight: 1.6 }}>Controles opcionais podem ser alterados. Proteções legais e de segurança permanecem ativas e não podem ser desligadas nesta interface.</p></div>
    {error && <p role="alert" style={{ color: '#f6a5a5' }}>{error}</p>}
    {notice && <p role="status" style={{ color: 'var(--green)' }}>{notice}</p>}
    {OPTIONAL.map(item => {
      const checked = Boolean(draft[item.key]);
      return <label key={item.key} style={{ ...boxStyle, display: 'flex', alignItems: 'center', gap: 16, cursor: 'pointer' }}>
        <input type="checkbox" checked={checked} onChange={e => setDraft(old => ({ ...old, [item.key]: e.target.checked }))} style={{ width: 20, height: 20, accentColor: '#a99aff', flex: 'none' }} />
        <span style={{ flex: 1 }}><strong>{item.title}</strong><span style={{ display: 'block', color: 'var(--muted)', fontSize: 12, marginTop: 5 }}>{item.description}</span></span>
        <span style={{ color: checked ? 'var(--green)' : 'var(--amber)', fontSize: 11 }}>{checked ? 'Ativado' : 'Desativado'}</span>
      </label>;
    })}
    <button type="button" className="upload-button" disabled={busy || !policies} onClick={() => void save()}>{busy ? 'Salvando…' : 'Salvar permissões'}</button>
    <div style={{ marginTop: 24 }}><span className="section-kicker">PROTEÇÕES OBRIGATÓRIAS</span>
      {(policies?.protected_controls ?? [
        { key: 'financial_actions', title: 'Transferências, pagamentos e saques bloqueados', enabled: true },
        { key: 'authentication', title: 'Autenticação obrigatória', enabled: true },
        { key: 'security_audit', title: 'Auditoria de segurança obrigatória', enabled: true },
      ]).map(item => <div key={item.key} style={{ ...boxStyle, display: 'flex', justifyContent: 'space-between', gap: 12 }}><span>{item.title}</span><strong style={{ color: 'var(--green)', whiteSpace: 'nowrap' }}>Sempre ativo</strong></div>)}
    </div>
  </section>;
}
