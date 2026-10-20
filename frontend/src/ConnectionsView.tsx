import { useEffect, useState } from 'react';

const PROVIDERS = [
  { id: 'groq', name: 'Groq', base: 'https://api.groq.com/openai/v1', key: 'https://console.groq.com/keys', hint: 'Use o ID exato de modelo mostrado no console.' },
  { id: 'openrouter', name: 'OpenRouter', base: 'https://openrouter.ai/api/v1', key: 'https://openrouter.ai/settings/keys', hint: 'Confira modelos gratuitos e limites da conta.' },
  { id: 'gemini', name: 'Google Gemini', base: 'https://generativelanguage.googleapis.com/v1beta/openai', key: 'https://aistudio.google.com/app/apikey', hint: 'Confirme suporte ao endpoint OpenAI-compatible e o ID do modelo.' },
  { id: 'cerebras', name: 'Cerebras', base: 'https://api.cerebras.ai/v1', key: 'https://cloud.cerebras.ai/', hint: 'Confira acesso e quotas atuais.' },
  { id: 'mistral', name: 'Mistral AI', base: 'https://api.mistral.ai/v1', key: 'https://console.mistral.ai/api-keys', hint: 'Use o ID exato de modelo habilitado.' },
  { id: 'deepseek', name: 'DeepSeek', base: 'https://api.deepseek.com/v1', key: 'https://platform.deepseek.com/api_keys', hint: 'Confira preço, limites e retenção antes do uso.' },
];
type ModelConfig = { id: string; provider: string; base_url: string; model: string; api_key_env: string; tasks: string[]; priority: number };
const TASKS = ['general', 'coding', 'research', 'marketing', 'analysis'];
const style = { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 14, padding: 18, marginBottom: 12 } as const;
const button = { border: '1px solid var(--line)', borderRadius: 9, padding: '9px 12px', color: '#e9e9f3', background: 'var(--panel-2)' } as const;

export function ConnectionsView() {
  const [selected, setSelected] = useState('groq');
  const [modelDraft, setModelDraft] = useState('');
  const [selectedTasks, setSelectedTasks] = useState<string[]>(TASKS);
  const [models, setModels] = useState<ModelConfig[]>(() => {
    try {
      const saved = window.sessionStorage.getItem('ia-empresarial-router-models');
      return saved ? JSON.parse(saved) as ModelConfig[] : [];
    } catch { return []; }
  });
  const [copied, setCopied] = useState(false);
  const provider = PROVIDERS.find(p => p.id === selected) ?? PROVIDERS[0];
  const keyEnv = `${provider.id.toUpperCase()}_API_KEY`;
  const configurationText = `AI_ROUTER_MODELS_JSON=${JSON.stringify(models)}\n${models.map(m => `${m.api_key_env}=COLOQUE_A_CHAVE_SECRETA_NO_RENDER`).join('\n')}`;

  useEffect(() => {
    try {
      if (models.length) window.sessionStorage.setItem('ia-empresarial-router-models', JSON.stringify(models));
      else window.sessionStorage.removeItem('ia-empresarial-router-models');
    } catch { /* Storage is optional; the manual configuration remains visible during this view. */ }
  }, [models]);

  function addModel() {
    if (!modelDraft.trim()) return;
    const entry: ModelConfig = {
      id: provider.id, provider: provider.name, base_url: provider.base, model: modelDraft.trim(),
      api_key_env: keyEnv, tasks: [...selectedTasks],
      priority: models.length * 10 + 10,
    };
    setModels(old => old.some(m => m.id === entry.id) ? old.map(m => m.id === entry.id ? entry : m) : [...old, entry]);
    setModelDraft('');
    setCopied(false);
  }
  async function copy() {
    if (!models.length) return;
    try { await navigator.clipboard.writeText(configurationText); setCopied(true); }
    catch { setCopied(false); }
  }

  return <section style={{ paddingBottom: 30 }}>
    <div style={{ marginBottom: 20 }}><span className="section-kicker">ROTEAMENTO MULTI-MODELO</span><h2 style={{ fontFamily: 'Space Grotesk', fontSize: 28, margin: '8px 0' }}>Conexões de IA</h2><p style={{ color: 'var(--muted)', lineHeight: 1.6 }}>Monte uma lista de modelos e gere a configuração do roteador. Esta página não armazena nem envia chaves secretas.</p></div>
    <div style={{ ...style, borderColor: '#b8abff' }}><strong>Catálogo não significa conexão ativa</strong><p style={{ color: 'var(--muted)', lineHeight: 1.6 }}>Adicionar um modelo aqui só prepara o JSON. Configure o ID real do modelo e as chaves no ambiente privado do backend/Render. Nunca cole segredos nesta interface.</p></div>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(230px,1fr))', gap: 12 }}>
      <div style={style}><span className="section-kicker">PROVEDORES</span>{PROVIDERS.map(p => <button key={p.id} type="button" onClick={() => { setSelected(p.id); setModelDraft(''); setSelectedTasks(TASKS); setCopied(false); }} style={{ display: 'block', width: '100%', textAlign: 'left', marginTop: 8, padding: 12, borderRadius: 9, border: `1px solid ${selected === p.id ? '#a99aff' : 'var(--line)'}`, background: selected === p.id ? '#302a45' : 'var(--panel-2)', color: '#e9e9f3' }}><strong>{p.name}</strong><small style={{ display: 'block', color: 'var(--muted)', marginTop: 4 }}>{p.base}</small></button>)}</div>
      <div style={style}><span className="section-kicker">ADICIONAR MODELO</span><h3>{provider.name}</h3><p style={{ color: 'var(--muted)' }}>{provider.hint}</p><label className="field">Base URL<input readOnly value={provider.base} onFocus={e => e.currentTarget.select()} /></label><label className="field">ID exato do modelo<input value={modelDraft} onChange={e => { setModelDraft(e.target.value); setCopied(false); }} placeholder="Cole o ID do painel oficial" /></label><p style={{ fontSize: 12, color: 'var(--muted)' }}>Variável secreta no backend: <code>{keyEnv}</code></p><div style={{ margin: '12px 0' }}><strong style={{ fontSize: 12 }}>Tipos de tarefa atendidos</strong><div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginTop: 8 }}>{TASKS.map(task => <label key={task} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12 }}><input type="checkbox" checked={selectedTasks.includes(task)} onChange={e => setSelectedTasks(old => e.target.checked ? [...old, task] : old.filter(t => t !== task))} />{task}</label>)}</div></div><a className="upload-button" href={provider.key} target="_blank" rel="noreferrer" style={{ display: 'inline-block', textDecoration: 'none' }}>Abrir painel oficial ↗</a><button className="upload-button" type="button" disabled={!modelDraft.trim() || !selectedTasks.length} onClick={addModel} style={{ marginLeft: 8 }}>Adicionar modelo</button></div>
    </div>
    <div style={style}><div className="panel-heading"><div><span className="section-kicker">ROTEADOR</span><h3>Modelos configurados</h3></div><button type="button" style={button} disabled={!models.length} onClick={() => void copy()}>{copied ? 'Configuração copiada' : 'Copiar configuração'}</button></div>
      {!models.length ? <p style={{ color: 'var(--muted)' }}>Adicione pelo menos um modelo. Para fallback real, adicione dois ou mais provedores.</p> : models.map(m => <div key={m.id} className="activity-row"><div style={{ flex: 1 }}><strong>{m.provider} · {m.model}</strong><p>{m.base_url} · prioridade {m.priority} · {m.api_key_env}</p></div><button type="button" style={button} onClick={() => { setModels(old => old.filter(x => x.id !== m.id)); setCopied(false); }}>Remover</button></div>)}
      <details style={{ marginTop: 12 }}><summary>Ver configuração para copiar manualmente</summary><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', fontSize: 11, color: 'var(--muted)' }}>{models.length ? configurationText : 'Adicione um modelo para gerar a configuração.'}</pre></details>
      <p style={{ fontSize: 12, color: 'var(--muted)', lineHeight: 1.6 }}>No Render, crie uma variável <code>AI_ROUTER_MODELS_JSON</code> contendo somente o JSON e uma variável secreta separada para cada chave (por exemplo, <code>GROQ_API_KEY</code>). Não cole o bloco .env inteiro em um único campo. O núcleo suporta endpoints compatíveis com <code>/chat/completions</code>; confirme disponibilidade, limites, custo e condições do provedor.</p>
    </div>
  </section>;
}
