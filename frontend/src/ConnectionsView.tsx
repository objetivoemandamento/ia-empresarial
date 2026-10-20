import { useState } from 'react';

const PROVIDERS = [
  { id: 'groq', name: 'Groq', base: 'https://api.groq.com/openai/v1', key: 'https://console.groq.com/keys', hint: 'Use o ID exato de modelo mostrado no console.' },
  { id: 'openrouter', name: 'OpenRouter', base: 'https://openrouter.ai/api/v1', key: 'https://openrouter.ai/settings/keys', hint: 'Confira modelos gratuitos e limites da conta.' },
  { id: 'gemini', name: 'Google Gemini', base: 'https://generativelanguage.googleapis.com/v1beta/openai', key: 'https://aistudio.google.com/app/apikey', hint: 'Confirme suporte ao endpoint OpenAI-compatible e o ID do modelo.' },
  { id: 'cerebras', name: 'Cerebras', base: 'https://api.cerebras.ai/v1', key: 'https://cloud.cerebras.ai/', hint: 'Confira acesso e quotas atuais.' },
  { id: 'mistral', name: 'Mistral AI', base: 'https://api.mistral.ai/v1', key: 'https://console.mistral.ai/api-keys', hint: 'Use o ID exato de modelo habilitado.' },
  { id: 'deepseek', name: 'DeepSeek', base: 'https://api.deepseek.com/v1', key: 'https://platform.deepseek.com/api_keys', hint: 'Confira preço, limites e retenção antes do uso.' },
];
const style = { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 14, padding: 18, marginBottom: 12 } as const;

export function ConnectionsView() {
  const [selected, setSelected] = useState('groq');
  const [model, setModel] = useState('');
  const [copied, setCopied] = useState(false);
  const provider = PROVIDERS.find(p => p.id === selected) ?? PROVIDERS[0];
  const keyEnv = `${provider.id.toUpperCase()}_API_KEY`;
  const config = JSON.stringify([{
    id: provider.id, provider: provider.name, base_url: provider.base, model: model.trim() || 'PREENCHA_ID_DO_MODELO',
    api_key_env: keyEnv, tasks: ['general', 'coding', 'research', 'marketing', 'analysis'], priority: 10,
  }]);

  async function copy() {
    const snippet = `AI_ROUTER_MODELS_JSON=${config}\n${keyEnv}=COLOQUE_A_CHAVE_SECRETA_NO_RENDER`;
    try { await navigator.clipboard.writeText(snippet); setCopied(true); }
    catch { setCopied(false); }
  }

  return <section style={{ paddingBottom: 30 }}>
    <div style={{ marginBottom: 20 }}><span className="section-kicker">ROTEAMENTO MULTI-MODELO</span><h2 style={{ fontFamily: 'Space Grotesk', fontSize: 28, margin: '8px 0' }}>Conexões de IA</h2><p style={{ color: 'var(--muted)', lineHeight: 1.6 }}>Prepare a configuração do roteador. Esta página não armazena nem envia chaves secretas.</p></div>
    <div style={{ ...style, borderColor: '#b8abff' }}><strong>Importante: catálogo não é conexão ativa</strong><p style={{ color: 'var(--muted)', lineHeight: 1.6 }}>Escolher um provedor não cria conta nem habilita um modelo. A chave e o JSON precisam ser configurados no ambiente privado do backend/Render. Não cole segredos nesta interface.</p></div>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(230px,1fr))', gap: 12 }}>
      <div style={style}><span className="section-kicker">PROVEDORES</span>{PROVIDERS.map(p => <button key={p.id} type="button" onClick={() => { setSelected(p.id); setCopied(false); }} style={{ display: 'block', width: '100%', textAlign: 'left', marginTop: 8, padding: 12, borderRadius: 9, border: `1px solid ${selected === p.id ? '#a99aff' : 'var(--line)'}`, background: selected === p.id ? '#302a45' : 'var(--panel-2)', color: '#e9e9f3' }}><strong>{p.name}</strong><small style={{ display: 'block', color: 'var(--muted)', marginTop: 4 }}>{p.base}</small></button>)}</div>
      <div style={style}><span className="section-kicker">CONFIGURAÇÃO</span><h3>{provider.name}</h3><p style={{ color: 'var(--muted)' }}>{provider.hint}</p><label className="field">Base URL<input readOnly value={provider.base} onFocus={e => e.currentTarget.select()} /></label><label className="field">ID exato do modelo<input value={model} onChange={e => { setModel(e.target.value); setCopied(false); }} placeholder="Ex.: identificador do painel do provedor" /></label><p style={{ fontSize: 12, color: 'var(--muted)' }}>Variável secreta a criar no backend: <code>{keyEnv}</code></p><a className="upload-button" href={provider.key} target="_blank" rel="noreferrer" style={{ display: 'inline-block', textDecoration: 'none' }}>Abrir painel oficial ↗</a><button className="upload-button" type="button" onClick={() => void copy()} style={{ marginLeft: 8 }}>{copied ? 'Configuração copiada' : 'Copiar configuração do roteador'}</button><p style={{ fontSize: 12, color: 'var(--muted)', lineHeight: 1.6 }}>O núcleo suporta endpoints compatíveis com <code>/chat/completions</code>. A disponibilidade gratuita, os modelos e os limites devem ser confirmados no provedor.</p></div>
    </div>
  </section>;
}
