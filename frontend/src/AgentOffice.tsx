import { useCallback, useEffect, useState } from 'react';
import { createAgentRun, decideAgentApproval, getAgentRun, listAgentRuns, retryAgentRun } from './agentRuns';
import type { AgentRun, AgentRunSummary } from './agentRuns';

const LABEL: Record<string, string> = {
  queued: 'Na fila', planning: 'CEO planejando', running: 'Em execução',
  awaiting_approval: 'Aguardando aprovação', delivered: 'Entregue', failed: 'Falhou',
  interrupted: 'Interrompida', pending: 'Pendente', running_task: 'Executando',
  done: 'Concluída', blocked: 'Bloqueada por política', rejected: 'Recusada',
  needs_approval: 'Requer aprovação',
};
const ACTIVE = new Set(['queued', 'planning', 'running']);
const SPECIALISTS = ['CEO coordenador', 'Estratégia', 'Pesquisa', 'Engenharia', 'Qualidade', 'Segurança', 'Produto', 'UX e acessibilidade', 'Marketing', 'Vendas e parcerias', 'Análise financeira', 'Operações', 'Dados e métricas', 'Compliance e privacidade', 'Documentação', 'Integrações', 'Revisor'];

const panelStyle = { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 16, padding: 20, marginBottom: 16 } as const;
const buttonStyle = { border: '1px solid var(--line)', background: 'var(--panel-2)', color: '#e9e9f3', borderRadius: 9, padding: '10px 13px', fontWeight: 600 } as const;

export function AgentOffice({ token, apiOnline, llmReady }: { token: string; apiOnline: boolean | null; llmReady: boolean | null }) {
  const [goal, setGoal] = useState('');
  const [runs, setRuns] = useState<AgentRunSummary[]>([]);
  const [detail, setDetail] = useState<AgentRun | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async (selectedId?: number) => {
    if (!token.trim()) return;
    try {
      const list = await listAgentRuns(token);
      setRuns(list);
      if (selectedId !== undefined) setDetail(await getAgentRun(selectedId, token));
      setError('');
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }, [token]);

  const active = runs.some(r => ACTIVE.has(r.status)) || Boolean(detail && ACTIVE.has(detail.status));
  useEffect(() => { void refresh(detail?.id); }, [refresh, detail?.id]);
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => { void refresh(detail?.id); }, 2500);
    return () => window.clearInterval(timer);
  }, [active, refresh, detail?.id]);

  async function act(fn: () => Promise<AgentRun>) {
    setBusy(true);
    try { const next = await fn(); setDetail(next); await refresh(next.id); setError(''); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  return <section style={{ paddingBottom: 30 }}>
    <div style={{ marginBottom: 20 }}>
      <span className="section-kicker">CEO → AGENTES → REVISÃO → ENTREGA</span>
      <h2 style={{ fontFamily: 'Space Grotesk', fontSize: 28, margin: '8px 0' }}>Escritório de IAs</h2>
      <p style={{ color: 'var(--muted)', lineHeight: 1.6, maxWidth: 760 }}>O CEO divide objetivos em tarefas verificáveis. Até quatro tarefas independentes podem ser processadas em paralelo. Publicação, envio, exclusão, rede externa e código aguardam autorização; operações financeiras ficam bloqueadas.</p>
      <p style={{ color: apiOnline ? 'var(--green)' : '#f6ce89', fontSize: 12 }}>{apiOnline ? 'API conectada' : apiOnline === false ? 'API indisponível' : 'Verificando API'} · {llmReady ? 'Modelo configurado' : llmReady === false ? 'Modelo ainda não configurado' : 'Verificando modelo'}. A aprovação apenas libera a etapa textual: nenhuma ação externa ou execução de código é realizada nesta versão.</p>
    </div>

    <div style={panelStyle}>
      <div className="panel-heading"><div><span className="section-kicker">NÚCLEO DE COORDENAÇÃO</span><h2>Nova missão</h2></div></div>
      {llmReady === false && <p role="status" style={{ color: '#f6ce89' }}>Configure um provedor e sua chave secreta no backend antes de iniciar uma missão.</p>}
      {!token.trim() ? <p style={{ color: 'var(--muted)' }}>Informe o token administrativo no painel Capacidades da tela inicial para criar e acompanhar execuções.</p> : <>
        <label className="field">Objetivo para o CEO<textarea value={goal} maxLength={4000} onChange={e => setGoal(e.target.value)} placeholder="Ex.: pesquise o mercado, compare opções e entregue um plano de implementação." /></label>
        <button type="button" style={buttonStyle} disabled={busy || !goal.trim() || llmReady === false} onClick={() => { const value = goal.trim(); setGoal(''); void act(() => createAgentRun(value, token)); }}>Planejar e executar</button>
      </>}
      {error && <p role="alert" style={{ color: '#f6a5a5', marginTop: 12 }}>{error}</p>}
    </div>

    <div style={{ ...panelStyle, display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(130px,1fr))', gap: 10 }}>
      {SPECIALISTS.map((name, i) => <div key={name} style={{ background: 'var(--panel-2)', border: '1px solid var(--line)', borderRadius: 10, padding: 12 }}>
        <div style={{ color: i === 0 ? 'var(--violet)' : 'var(--blue)', fontSize: 10, letterSpacing: '.08em' }}>AGENTE {String(i + 1).padStart(2, '0')}</div>
        <strong style={{ display: 'block', marginTop: 6, fontSize: 12 }}>{name}</strong>
        <small style={{ color: 'var(--muted)', display: 'block', marginTop: 4 }}>{i === 0 ? 'Coordena' : i === 16 ? 'Revisa resultados' : 'Persona especializada'}</small>
      </div>)}
    </div>

    {token.trim() && <div style={panelStyle}>
      <div className="panel-heading"><div><span className="section-kicker">PERSISTÊNCIA E ACOMPANHAMENTO</span><h2>Execuções</h2></div><button style={buttonStyle} type="button" onClick={() => void refresh(detail?.id)}>Atualizar</button></div>
      {!runs.length ? <p style={{ color: 'var(--muted)' }}>Nenhuma execução registrada ainda.</p> : runs.map(run => <div key={run.id} className="activity-row">
        <div style={{ flex: 1 }}><strong>#{run.id} · {LABEL[run.status] ?? run.status}</strong><p>{run.goal.slice(0, 160)}</p></div>
        <button style={buttonStyle} type="button" onClick={() => void act(() => getAgentRun(run.id, token))}>Detalhes</button>
      </div>)}
    </div>}

    {detail && <div style={panelStyle}>
      <div className="panel-heading"><div><span className="section-kicker">MISSÃO #{detail.id}</span><h2>{LABEL[detail.status] ?? detail.status}</h2></div></div>
      {detail.error && <p role="alert" style={{ color: '#f6a5a5' }}>{detail.error}</p>}
      {detail.tasks.map(task => <div key={task.id} className="activity-row"><div style={{ flex: 1 }}>
        <strong>{task.title}</strong><p>{LABEL[task.status] ?? task.status} · tentativas {task.attempts}</p>
        {task.error && <p role="alert">{task.error}</p>}{task.output && <details><summary>Ver resultado</summary><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{task.output}</pre></details>}
      </div></div>)}
      {detail.approvals.filter(a => a.status === 'pending').map(a => <div key={a.id} className="activity-row"><div style={{ flex: 1 }}><strong>Aprovação necessária: {a.action}</strong><p>{a.detail}</p></div>
        <button style={buttonStyle} type="button" disabled={busy} onClick={() => void act(() => decideAgentApproval(a.id, true, token))}>Aprovar</button>
        <button style={{ ...buttonStyle, borderColor: '#9d5555' }} type="button" disabled={busy} onClick={() => void act(() => decideAgentApproval(a.id, false, token))}>Recusar</button>
      </div>)}
      {(detail.status === 'failed' || detail.status === 'interrupted') && <button style={buttonStyle} type="button" disabled={busy} onClick={() => void act(() => retryAgentRun(detail.id, token))}>Tentar novamente</button>}
      {detail.events?.length > 0 && <details style={{ marginTop: 16 }}><summary>Histórico de auditoria ({detail.events.length} eventos)</summary>
        {detail.events.map(event => <div key={event.id} className="activity-row"><div style={{ flex: 1 }}><strong>{event.kind}</strong><p>{new Date(event.ts * 1000).toLocaleString('pt-BR')} · {event.detail}</p></div></div>)}
      </details>}
      {detail.result && <><h3>Entrega revisada</h3><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{detail.result}</pre></>}
    </div>}
  </section>;
}
