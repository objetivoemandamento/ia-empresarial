import { useEffect, useMemo, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { checkHealth, listSkills, uploadSkill, moderateSkill, sendChat, transcribe } from './api';
import type { Language, Skill } from './api';
import { listHumanTasks, createHumanTask, decideHumanTask, changeHumanTaskStatus, completeHumanTask } from './humanTasks';
import type { HumanTask, HumanTaskPriority } from './humanTasks';
import { AgentOffice } from './AgentOffice';
import { PermissionsView } from './PermissionsView';

type Message = { role: 'user' | 'assistant'; content: string };
type Activity = { id: number; time: string; label: string; detail: string; tone: 'blue' | 'green' | 'amber' };
const LANGUAGES: { code: Language; label: string; native: string; speech: string }[] = [
  { code: 'pt', label: 'Português', native: 'PT', speech: 'pt-BR' },
  { code: 'en', label: 'English', native: 'EN', speech: 'en-US' },
  { code: 'zh', label: 'Mandarim', native: '中文', speech: 'zh-CN' },
  { code: 'es', label: 'Español', native: 'ES', speech: 'es-ES' },
  { code: 'hi', label: 'Hindi', native: 'हिंदी', speech: 'hi-IN' },
];
const initial: Message[] = [{ role: 'assistant', content: 'Bem-vindo ao escritório. Posso conversar por texto, usar ditado por voz e incorporar capacidades declarativas após revisão. Para respostas de um modelo real, configure o provedor de IA no backend.' }];
const clock = () => new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });

export default function App() {
  const [activeTab, setActiveTab] = useState<'home' | 'office' | 'permissions'>('home');
  const [language, setLanguage] = useState<Language | 'auto'>('pt');
  const [messages, setMessages] = useState<Message[]>(initial);
  const [draft, setDraft] = useState('');
  const [skills, setSkills] = useState<Skill[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [token, setToken] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [voiceStatus, setVoiceStatus] = useState('Pronto para ouvir');
  const [recording, setRecording] = useState(false);
  const [serverRecording, setServerRecording] = useState(false);
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);
  const [llmReady, setLlmReady] = useState<boolean | null>(null);
  const [activities, setActivities] = useState<Activity[]>([{ id: 1, time: clock(), label: 'Escritório iniciado', detail: 'Interface pronta em português', tone: 'green' }]);
  const [tasks, setTasks] = useState<HumanTask[]>([]);
  const [taskTitle, setTaskTitle] = useState('');
  const [taskDescription, setTaskDescription] = useState('');
  const [taskOwner, setTaskOwner] = useState('');
  const [taskDueAt, setTaskDueAt] = useState('');
  const [taskDependencies, setTaskDependencies] = useState<string[]>([]);
  const [taskPriority, setTaskPriority] = useState<HumanTaskPriority>('normal');
  const [taskRequiresApproval, setTaskRequiresApproval] = useState(false);
  const [taskFilter, setTaskFilter] = useState('all');
  const [taskBusy, setTaskBusy] = useState(false);
  const [taskError, setTaskError] = useState('');
  const fileInput = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const activityId = useRef(2);

  const addActivity = (label: string, detail: string, tone: Activity['tone'] = 'blue') => {
    setActivities(prev => [{ id: activityId.current++, time: clock(), label, detail, tone }, ...prev].slice(0, 8));
  };

  async function refreshTasks() {
    if (!token.trim()) { setTasks([]); return; }
    try { setTasks(await listHumanTasks(token)); setTaskError(''); }
    catch (e) { setTaskError(String(e)); }
  }

  async function createTask(e?: FormEvent) {
    e?.preventDefault();
    if (!token.trim()) { setTaskError('Introduza o token administrativo para gerir tarefas.'); return; }
    if (!taskTitle.trim() || taskBusy) return;
    setTaskBusy(true);
    try {
      await createHumanTask(token, {
        title: taskTitle.trim(), description: taskDescription.trim(),
        owner: taskOwner.trim() || null, priority: taskPriority,
        requires_approval: taskRequiresApproval,
        due_at: taskDueAt ? new Date(taskDueAt).toISOString() : null,
        dependencies: taskDependencies,
      });
      setTaskTitle(''); setTaskDescription(''); setTaskOwner(''); setTaskDueAt(''); setTaskDependencies([]);
      setTaskRequiresApproval(false); setTaskError('');
      await refreshTasks();
      addActivity('Tarefa criada', taskTitle.trim(), 'green');
    } catch (e) { setTaskError(String(e)); }
    finally { setTaskBusy(false); }
  }

  async function decideTask(task: HumanTask, decision: 'approve' | 'reject') {
    if (!token.trim()) { setTaskError('Introduza o token administrativo.'); return; }
    try {
      await decideHumanTask(token, task.id, decision, task.title);
      setTaskError('');
      addActivity(decision === 'approve' ? 'Escopo aprovado' : 'Tarefa rejeitada', task.title, decision === 'approve' ? 'green' : 'amber');
      await refreshTasks();
    } catch (e) { setTaskError(String(e)); }
  }

  async function changeTaskStatus(task: HumanTask, status: 'open' | 'in_progress' | 'blocked' | 'cancelled') {
    if (!token.trim()) { setTaskError('Introduza o token administrativo.'); return; }
    try {
      await changeHumanTaskStatus(token, task.id, status);
      setTaskError('');
      await refreshTasks();
      addActivity('Estado da tarefa atualizado', task.title, 'green');
    } catch (e) { setTaskError(String(e)); }
  }

  async function finishTask(task: HumanTask) {
    if (!token.trim()) { setTaskError('Introduza o token administrativo.'); return; }
    try {
      await completeHumanTask(token, task.id);
      setTaskError('');
      await refreshTasks();
      addActivity('Tarefa concluída', task.title, 'green');
    } catch (e) { setTaskError(String(e)); }
  }

  async function refreshSkills() {
    try { setSkills(await listSkills()); setApiOnline(true); }
    catch (e) { setApiOnline(false); setNotice(`API indisponível: ${String(e)}`); }
  }
  useEffect(() => { void refreshSkills(); void checkHealth().then(health => { setApiOnline(true); setLlmReady(health.llm_ready); }).catch(() => { setApiOnline(false); setLlmReady(null); }); }, []);
  useEffect(() => { if (token.trim()) void refreshTasks(); else { setTasks([]); setTaskError(''); } }, [token]);
  useEffect(() => { scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' }); }, [messages]);
  useEffect(() => () => { recognitionRef.current?.abort?.(); if (mediaRecorderRef.current?.state === 'recording') mediaRecorderRef.current.stop(); window.speechSynthesis?.cancel(); }, []);

  const selectedLanguage = LANGUAGES.find(l => l.code === language) ?? LANGUAGES[0];
  const activeSkills = useMemo(() => skills.filter(s => s.status === 'active'), [skills]);
  const pendingSkills = useMemo(() => skills.filter(s => s.status === 'pending_review'), [skills]);
  const visibleTasks = useMemo(() => taskFilter === 'all' ? tasks : tasks.filter(task => task.status === taskFilter), [tasks, taskFilter]);
  const languageName = language === 'auto' ? 'Automático' : selectedLanguage.label;

  async function submit(e?: FormEvent) {
    e?.preventDefault();
    const text = draft.trim();
    if (!text || busy) return;
    const next: Message[] = [...messages, { role: 'user', content: text }];
    setMessages(next); setDraft(''); setBusy(true); setNotice('');
    addActivity('Mensagem enviada', text.length > 70 ? `${text.slice(0, 70)}…` : text);
    try {
      const result = await sendChat(next.slice(-30), language === 'auto' ? null : language, selected);
      if (language === 'auto') setLanguage(result.language);
      setMessages([...next, { role: 'assistant', content: result.answer }]);
      addActivity('Resposta recebida', `Provedor: ${result.provider}`, 'green');
    } catch (err) {
      setMessages([...next, { role: 'assistant', content: `Não foi possível obter resposta: ${String(err)}` }]);
      addActivity('Falha no chat', String(err), 'amber');
    } finally { setBusy(false); }
  }

  async function handleUpload(file?: File) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.zip')) { setNotice('Selecione um ficheiro .zip.'); return; }
    if (!token.trim()) { setNotice('Introduza o token administrativo para instalar e moderar repositórios.'); return; }
    setNotice('A validar e a enviar o pacote…');
    try {
      const skill = await uploadSkill(file, token);
      setNotice(`Pacote recebido: ${skill.name}. Aguarda aprovação.`);
      addActivity('Pacote recebido', `${skill.name} · revisão pendente`, 'amber');
      await refreshSkills();
    } catch (err) { setNotice(String(err)); addActivity('Upload recusado', String(err), 'amber'); }
    if (fileInput.current) fileInput.current.value = '';
  }

  async function moderate(skill: Skill, action: 'approve' | 'reject') {
    try {
      await moderateSkill(skill.id, action, token);
      setNotice(action === 'approve' ? `${skill.name} aprovada e ativada.` : `${skill.name} rejeitada.`);
      addActivity(action === 'approve' ? 'Capacidade ativada' : 'Capacidade rejeitada', skill.name, action === 'approve' ? 'green' : 'amber');
      await refreshSkills();
    } catch (err) { setNotice(String(err)); }
  }

  function speak(text: string) {
    if (!('speechSynthesis' in window)) { setVoiceStatus('Síntese de voz não suportada neste navegador.'); return; }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = selectedLanguage.speech;
    window.speechSynthesis.speak(utterance);
    setVoiceStatus(`A falar: ${selectedLanguage.label}`);
  }

  function startRecognition() {
    const w = window as any;
    const Recognition = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!Recognition) { setVoiceStatus('Ditado do navegador indisponível. Use a gravação para transcrição no servidor.'); return; }
    const rec = new Recognition();
    rec.lang = selectedLanguage.speech;
    rec.interimResults = true;
    rec.continuous = false;
    rec.onresult = (event: any) => {
      let text = '';
      for (let i = event.resultIndex; i < event.results.length; i++) text += event.results[i][0].transcript;
      setDraft(text);
    };
    rec.onerror = (event: any) => setVoiceStatus(`Reconhecimento: ${event.error}`);
    rec.onend = () => { setRecording(false); setVoiceStatus('Ditado finalizado'); };
    recognitionRef.current = rec;
    try { rec.start(); setRecording(true); setVoiceStatus(`A ouvir: ${selectedLanguage.label}`); }
    catch { setVoiceStatus('Não foi possível iniciar o microfone. Verifique a permissão do navegador.'); }
  }
  function stopRecognition() { recognitionRef.current?.stop?.(); setRecording(false); }

  async function toggleServerRecording() {
    if (serverRecording) {
      mediaRecorderRef.current?.stop();
      setServerRecording(false);
      setVoiceStatus('A transcrever áudio…');
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setVoiceStatus('Gravação de áudio não suportada neste navegador.'); return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      chunksRef.current = [];
      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;
      recorder.ondataavailable = event => { if (event.data.size) chunksRef.current.push(event.data); };
      recorder.onerror = () => { stream.getTracks().forEach(track => track.stop()); setServerRecording(false); setVoiceStatus('Erro ao gravar áudio.'); };
      recorder.onstop = async () => {
        stream.getTracks().forEach(track => track.stop());
        const audio = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' });
        if (!audio.size) { setVoiceStatus('Nenhum áudio capturado.'); return; }
        try {
          const text = await transcribe(audio, language === 'auto' ? 'pt' : language);
          setDraft(prev => prev ? `${prev} ${text}` : text);
          setVoiceStatus('Transcrição adicionada ao campo de mensagem.');
          addActivity('Áudio transcrito', `${audio.size.toLocaleString('pt-BR')} bytes`, 'green');
        } catch (err) { setVoiceStatus(`Falha na transcrição: ${String(err)}`); }
      };
      recorder.start(); setServerRecording(true); setVoiceStatus('A gravar. Clique em parar quando terminar.');
    } catch (err) { setVoiceStatus(`Microfone indisponível: ${String(err)}`); }
  }

  if (activeTab !== 'home') {
    const officeTitle = activeTab === 'office' ? 'Escritório de IAs' : 'Permissões';
    return <div className="app-frame">
      <aside className="rail">
        <a className="brand-mark" href="#top" aria-label="Início" onClick={() => setActiveTab('home')}><span className="pixel-logo">V</span></a>
        <nav className="rail-nav" aria-label="Navegação do escritório">
          <button type="button" className="rail-link" onClick={() => setActiveTab('home')}><span>▦</span><small>Escritório</small></button>
          <button type="button" className={`rail-link ${activeTab === 'office' ? 'selected' : ''}`} onClick={() => setActiveTab('office')}><span>♟</span><small>Agentes IA</small></button>
          <button type="button" className={`rail-link ${activeTab === 'permissions' ? 'selected' : ''}`} onClick={() => setActiveTab('permissions')}><span>⚙</span><small>Permissões</small></button>
        </nav>
        <div className="rail-bottom"><span className={`connection-dot ${apiOnline ? 'online' : apiOnline === false ? 'offline' : ''}`} /><small>{apiOnline ? 'API' : apiOnline === false ? 'Offline' : '…'}</small></div>
      </aside>
      <main className="workspace" id="top">
        <header className="topbar">
          <div className="brand-lockup"><div className="eyebrow">IA EMPRESARIAL · WORKSPACE</div><h1>{officeTitle}</h1><p>{activeTab === 'office' ? 'Coordenação de tarefas, agentes especialistas e revisão.' : 'Configurações opcionais e proteções obrigatórias.'}</p></div>
          <div className={`api-pill ${apiOnline ? 'ok' : apiOnline === false ? 'bad' : ''}`}><span className="connection-dot" />{apiOnline ? 'API conectada' : apiOnline === false ? 'API offline' : 'A verificar API'}</div>
        </header>
        {activeTab === 'office' ? <AgentOffice token={token} apiOnline={apiOnline} /> : <PermissionsView token={token} />}
      </main>
    </div>;
  }

  return <div className="app-frame">
    <aside className="rail">
      <a className="brand-mark" href="#top" aria-label="Início"><span className="pixel-logo">V</span></a>
      <nav className="rail-nav" aria-label="Navegação do escritório">
        <a className={`rail-link ${activeTab === 'home' ? 'selected' : ''}`} href="#top" title="Escritório" onClick={() => setActiveTab('home')}><span>▦</span><small>Escritório</small></a>
        <button type="button" className="rail-link" title="Escritório de IAs" onClick={() => setActiveTab('office')}><span>♟</span><small>Agentes IA</small></button>
        <button type="button" className="rail-link" title="Permissões" onClick={() => setActiveTab('permissions')}><span>⚙</span><small>Permissões</small></button>
        <a className="rail-link" href="#conversation" title="Conversa" onClick={() => setActiveTab('home')}><span>▤</span><small>Conversa</small></a>
        <a className="rail-link" href="#skills" title="Capacidades"><span>⌘</span><small>Skills</small></a>
        <a className="rail-link" href="#human-tasks" title="Minhas tarefas"><span>✓</span><small>Tarefas</small></a>
        <a className="rail-link" href="#voice" title="Voz"><span>♫</span><small>Voz</small></a>
      </nav>
      <div className="rail-bottom"><span className={`connection-dot ${apiOnline ? 'online' : apiOnline === false ? 'offline' : ''}`} title={apiOnline ? 'API conectada' : 'A verificar API'} /><small>{apiOnline ? 'API' : apiOnline === false ? 'Offline' : '…'}</small></div>
    </aside>

    <main className="workspace" id="top">
      <header className="topbar">
        <div className="brand-lockup"><div className="eyebrow">MODULAR AI · WORKSPACE</div><h1>Escritório <span>Vértice</span></h1><p>Um espaço de trabalho para conversar, instalar capacidades e gerir a voz.</p></div>
        <div className="top-actions">
          <div className={`api-pill ${apiOnline ? 'ok' : apiOnline === false ? 'bad' : ''}`}><span className="connection-dot" />{apiOnline ? (llmReady ? 'Modelo conectado' : 'API online · IA demo') : apiOnline === false ? 'API desconectada' : 'A ligar…'}</div>
          <label className="language-picker"><span>IDIOMA</span><select value={language} onChange={e => setLanguage(e.target.value as Language | 'auto')} aria-label="Idioma da conversa">
            {LANGUAGES.map(l => <option key={l.code} value={l.code}>{l.native} · {l.label}{l.code === 'pt' ? ' (padrão)' : ''}</option>)}
            <option value="auto">AUTO · Pelo manifesto</option>
          </select></label>
        </div>
      </header>

      <section className="welcome-strip">
        <div className="welcome-copy"><span className="section-kicker"><i /> ESCRITÓRIO ABERTO</span><h2>As suas capacidades,<br /><em>num só lugar.</em></h2><p>Converse com o núcleo, instale skills declarativas e acompanhe o que aconteceu nesta sessão.</p><a href="#conversation" className="primary-link">Abrir conversa <span>↗</span></a></div>
        <div className="pixel-office" aria-label="Ilustração abstrata de um escritório digital" role="img">
          <div className="office-window"><span /><span /><span /></div><div className="office-shelf shelf-one" /><div className="office-shelf shelf-two" />
          <div className="desk desk-back" /><div className="monitor"><div className="monitor-screen"><i /><i /><i /></div><div className="monitor-neck" /></div>
          <div className="plant"><i /><i /><b /></div><div className="desk desk-front" />
          <div className="pixel-person person-one"><i className="hair" /><i className="face" /><i className="body" /><i className="legs" /></div>
          <div className="pixel-person person-two"><i className="hair" /><i className="face" /><i className="body" /><i className="legs" /></div>
          <div className="speech-bubble">A trabalhar<span>•••</span></div>
          <div className="room-tag">SALA 01 <b>●</b></div>
        </div>
      </section>

      <section className="metrics-grid" aria-label="Resumo do sistema">
        <article className="metric-card"><div className="metric-icon blue">⌘</div><div><span>CAPACIDADES ATIVAS</span><strong>{activeSkills.length.toString().padStart(2, '0')}</strong><small>{pendingSkills.length ? `${pendingSkills.length} aguardam revisão` : 'Nenhuma pendente'}</small></div><span className="metric-decoration">↗</span></article>
        <article className="metric-card"><div className="metric-icon violet">◉</div><div><span>IDIOMAS DISPONÍVEIS</span><strong>05</strong><small>Português por padrão</small></div><span className="metric-decoration">↗</span></article>
        <article className="metric-card"><div className="metric-icon green">▤</div><div><span>MENSAGENS NA SESSÃO</span><strong>{Math.max(0, messages.length - 1).toString().padStart(2, '0')}</strong><small>Histórico local desta página</small></div><span className="metric-decoration">↗</span></article>
      </section>

      <section className="rooms-section" aria-labelledby="rooms-title">
        <div className="section-heading"><div><span className="section-kicker">O SEU ESPAÇO</span><h2 id="rooms-title">Salas de trabalho</h2></div><span className="section-caption">Módulos desta plataforma</span></div>
        <div className="rooms-grid">
          <a className="room-card room-chat" href="#conversation"><div className="room-card-top"><span className="room-icon">▤</span><span className="room-state"><i /> PRONTA</span></div><div className="room-illustration chat-illustration"><span className="bubble b1">Olá!</span><span className="bubble b2">...</span><div className="mini-avatar"><i /><b /></div></div><h3>Conversa central</h3><p>Envie instruções por texto ou voz e receba respostas do modelo configurado.</p><span className="room-footer">Entrar na sala <b>↗</b></span></a>
          <a className="room-card room-skills" href="#skills"><div className="room-card-top"><span className="room-icon">⌘</span><span className="room-state"><i /> {activeSkills.length} ATIVAS</span></div><div className="room-illustration skill-illustration"><span className="tile t1">JS</span><span className="tile t2">AI</span><span className="tile t3">ZIP</span><span className="tile t4">✓</span></div><h3>Oficina de capacidades</h3><p>Instale pacotes ZIP, reveja manifestos e aprove ferramentas declarativas.</p><span className="room-footer">Gerir capacidades <b>↗</b></span></a>
          <a className="room-card room-voice" href="#voice"><div className="room-card-top"><span className="room-icon">♫</span><span className="room-state"><i /> MULTILÍNGUE</span></div><div className="room-illustration voice-illustration"><span className="wave w1"/><span className="wave w2"/><span className="wave w3"/><span className="wave w4"/><span className="wave w5"/><span className="wave w6"/><span className="wave w7"/></div><h3>Estúdio de voz</h3><p>Ditado, transcrição server-side e síntese de voz com cinco idiomas.</p><span className="room-footer">Abrir estúdio <b>↗</b></span></a>
        </div>
      </section>

      <section className="panel tasks-panel" id="human-tasks">
        <div className="panel-heading compact">
          <div className="panel-heading-icon amber">✓</div>
          <div><span className="section-kicker">ORGANIZAÇÃO · DECISÃO HUMANA</span><h2>Minhas tarefas</h2><p>Tarefas persistidas no backend, com histórico de decisões e conclusão.</p></div>
          <span className="count-badge">{tasks.length}</span>
        </div>
        <p className="security-note">Aprovações registram apenas o escopo exato do título. Nenhuma aprovação executa ações externas; Pix, saques e transferências de saída são bloqueados.</p>
        <form className="task-create-form" onSubmit={createTask}>
          <label className="field">Título da tarefa<input value={taskTitle} onChange={e => setTaskTitle(e.target.value)} maxLength={200} required placeholder="Ex.: Revisar o plano de implantação" /></label>
          <label className="field">Descrição<textarea value={taskDescription} onChange={e => setTaskDescription(e.target.value)} maxLength={5000} rows={2} placeholder="Contexto, resultado esperado e critérios de conclusão" /></label>
          <div className="task-fields-row">
            <label className="field">Responsável<input value={taskOwner} onChange={e => setTaskOwner(e.target.value)} maxLength={120} placeholder="Pessoa responsável" /></label>
            <label className="field">Prioridade<select value={taskPriority} onChange={e => setTaskPriority(e.target.value as HumanTaskPriority)}><option value="low">Baixa</option><option value="normal">Normal</option><option value="high">Alta</option><option value="urgent">Urgente</option></select></label>
          </div>
          <div className="task-fields-row">
            <label className="field">Prazo<input type="datetime-local" value={taskDueAt} onChange={e => setTaskDueAt(e.target.value)} /></label>
            <label className="field">Dependências<select multiple value={taskDependencies} onChange={e => setTaskDependencies(Array.from(e.target.selectedOptions, option => option.value))} aria-label="Dependências da tarefa">{tasks.filter(task => !['done', 'rejected', 'cancelled'].includes(task.status)).map(task => <option key={task.id} value={task.id}>{task.title}</option>)}</select></label>
          </div>
          <label className="check"><input type="checkbox" checked={taskRequiresApproval} onChange={e => setTaskRequiresApproval(e.target.checked)} /> Exigir aprovação humana antes de iniciar</label>
          <button className="upload-button" type="submit" disabled={!token.trim() || taskBusy || !taskTitle.trim()}><span>＋</span>{taskBusy ? 'A criar…' : 'Criar tarefa'}</button>
        </form>
        <div className="task-toolbar">
          <label className="field">Filtrar estado<select value={taskFilter} onChange={e => setTaskFilter(e.target.value)}>
            <option value="all">Todos os estados</option><option value="awaiting_approval">Aguardando aprovação</option><option value="open">Aberta</option><option value="in_progress">Em andamento</option><option value="blocked">Bloqueada</option><option value="done">Concluída</option><option value="rejected">Rejeitada</option><option value="cancelled">Cancelada</option>
          </select></label>
          <button type="button" className="upload-button" onClick={() => void refreshTasks()} disabled={!token.trim()}>Atualizar lista</button>
        </div>
        {taskError && <div className="notice" role="status">{taskError}</div>}
        {!token.trim() && <div className="empty-state"><span>◇</span><strong>Autenticação necessária</strong><p>Introduza o token administrativo no painel Capacidades para carregar e gerir tarefas.</p></div>}
        {token.trim() && visibleTasks.length === 0 && <div className="empty-state"><span>✓</span><strong>Nenhuma tarefa neste filtro</strong><p>Crie uma tarefa acima ou altere o filtro para ver outros estados.</p></div>}
        <div className="skill-list task-list">
          {visibleTasks.map(task => <article className="skill-item task-item" key={task.id}>
            <div className="skill-head"><span className="skill-glyph">{task.priority === 'urgent' ? '!' : task.priority === 'high' ? '↑' : '✓'}</span><div className="skill-title"><strong>{task.title}</strong><small>{task.owner ? `Responsável: ${task.owner}` : 'Sem responsável'} · Prioridade {task.priority === 'urgent' ? 'urgente' : task.priority === 'high' ? 'alta' : task.priority === 'low' ? 'baixa' : 'normal'}</small></div><span className={`status task-status ${task.status}`}>{task.status === 'awaiting_approval' ? 'Aguardando aprovação' : task.status === 'open' ? 'Aberta' : task.status === 'in_progress' ? 'Em andamento' : task.status === 'blocked' ? 'Bloqueada' : task.status === 'done' ? 'Concluída' : task.status === 'rejected' ? 'Rejeitada' : 'Cancelada'}</span></div>
            {task.description && <p>{task.description}</p>}
            {task.due_at && <p>Prazo: {new Date(task.due_at).toLocaleString('pt-BR')}</p>}
            {task.approved_scope && <p className="security-note">Escopo aprovado: {task.approved_scope}. Nenhuma ação foi executada automaticamente.</p>}
            {task.dependencies.length > 0 && <p className="security-note">Dependências: {task.dependencies.map(id => tasks.find(item => item.id === id)?.title ?? id).join(', ')}</p>}
            <div className="skill-actions">
              {task.status === 'awaiting_approval' && <><button type="button" onClick={() => void decideTask(task, 'approve')}>Aprovar escopo exato</button><button type="button" className="danger" onClick={() => void decideTask(task, 'reject')}>Rejeitar</button></>}
              {task.status === 'open' && <button type="button" onClick={() => void changeTaskStatus(task, 'in_progress')}>Iniciar</button>}
              {task.status === 'in_progress' && <><button type="button" onClick={() => void finishTask(task)}>Concluir</button><button type="button" className="danger" onClick={() => void changeTaskStatus(task, 'blocked')}>Bloquear</button></>}
              {task.status === 'blocked' && <button type="button" onClick={() => void changeTaskStatus(task, 'in_progress')}>Retomar</button>}
            </div>
          </article>)}
        </div>
      </section>

      <div className="main-columns">
        <section className="panel conversation-panel" id="conversation">
          <div className="panel-heading"><div className="panel-heading-icon">▤</div><div><span className="section-kicker">SALA 01 · NÚCLEO</span><h2>Conversa central</h2><p>Idioma ativo: {languageName}</p></div><span className="live-label"><i /> SESSÃO LOCAL</span></div>
          <div className="messages" ref={scrollRef} aria-live="polite">
            {messages.map((m, i) => <article key={i} className={`message ${m.role}`}>
              <div className={`message-avatar ${m.role}`}>{m.role === 'user' ? 'TU' : 'AI'}</div><div className="message-body"><div className="message-meta"><strong>{m.role === 'user' ? 'Você' : 'Núcleo IA'}</strong><time>{i === 0 ? 'Bem-vindo' : `${i + 1}ª mensagem`}</time></div><p>{m.content}</p>{m.role === 'assistant' && <button className="text-action" onClick={() => speak(m.content)}>▶ Ouvir resposta</button>}</div>
            </article>)}
            {busy && <div className="working"><span className="typing-dots"><i/><i/><i/></span> O núcleo está a processar…</div>}
          </div>
          <form className="composer" onSubmit={submit}>
            <textarea value={draft} onChange={e => setDraft(e.target.value)} placeholder="Diga ao núcleo o que precisa de fazer…" rows={3} maxLength={20000} aria-label="Mensagem para o núcleo" />
            <div className="composer-bottom"><div className="voice-actions"><button type="button" className={`icon-button ${recording ? 'recording' : ''}`} onClick={recording ? stopRecognition : startRecognition} title={recording ? 'Parar ditado' : 'Ditado no navegador'}>{recording ? '■' : '🎙'}<span>{recording ? 'Parar ditado' : 'Ditado'}</span></button><span className="voice-status">{voiceStatus}</span></div><button type="submit" className="send-button" disabled={busy || !draft.trim()}>{busy ? 'A processar…' : 'Enviar mensagem'} <span>↑</span></button></div>
          </form>
        </section>

        <aside className="right-column">
          <section className="panel skills-panel" id="skills">
            <div className="panel-heading compact"><div className="panel-heading-icon purple">⌘</div><div><span className="section-kicker">MÓDULO DE REPOSITÓRIOS</span><h2>Capacidades</h2></div><span className="count-badge">{skills.length}</span></div>
            <label className="field">Token administrativo<input type="password" autoComplete="current-password" value={token} onChange={e => setToken(e.target.value)} placeholder="ADMIN_TOKEN" /></label>
            <button className="upload-button" onClick={() => fileInput.current?.click()}><span>＋</span> Instalar pacote ZIP</button>
            <input ref={fileInput} hidden type="file" accept=".zip,application/zip" onChange={e => void handleUpload(e.target.files?.[0])}/>
            <p className="security-note"><span>◇</span> Pacotes ficam pendentes de aprovação. Código arbitrário não é executado.</p>
            <div className="skill-list">
              {skills.length === 0 && <div className="empty-state"><span>⌘</span><strong>A oficina está vazia</strong><p>Instale um ZIP com um manifesto de skill declarativa para começar.</p></div>}
              {skills.map(skill => <article className="skill-item" key={skill.id}>
                <div className="skill-head"><span className="skill-glyph">{skill.name.slice(0, 1).toUpperCase()}</span><div className="skill-title"><strong>{skill.name}</strong><small>v{skill.version} · {skill.tools.join(', ') || 'Sem ferramentas'}</small></div><span className={`status ${skill.status}`}>{skill.status === 'pending_review' ? 'Revisão' : skill.status === 'active' ? 'Ativa' : 'Rejeitada'}</span></div>
                <p>{skill.description}</p>
                {skill.status === 'active' && <label className="check"><input type="checkbox" checked={selected.includes(skill.id)} onChange={e => setSelected(prev => e.target.checked ? [...prev, skill.id] : prev.filter(id => id !== skill.id))}/> Disponível no chat</label>}
                {skill.status === 'pending_review' && <div className="skill-actions"><button onClick={() => void moderate(skill, 'approve')}>Aprovar</button><button className="danger" onClick={() => void moderate(skill, 'reject')}>Rejeitar</button></div>}
              </article>)}
            </div>
            {notice && <div className="notice" role="status">{notice}</div>}
          </section>

          <section className="panel voice-panel" id="voice">
            <div className="panel-heading compact"><div className="panel-heading-icon green">♫</div><div><span className="section-kicker">ÁUDIO · SPEECH</span><h2>Estúdio de voz</h2></div></div>
            <p className="voice-description">Grave uma nota e envie-a para transcrição no backend. O áudio depende de uma chave e de um provedor configurados no servidor.</p>
            <button type="button" className={`record-button ${serverRecording ? 'is-recording' : ''}`} onClick={() => void toggleServerRecording()}><span>{serverRecording ? '■' : '●'}</span>{serverRecording ? 'Parar e transcrever' : 'Gravar áudio para transcrição'}</button>
            <div className="language-list">{LANGUAGES.map((l, i) => <button type="button" key={l.code} onClick={() => setLanguage(l.code)} className={`language-row ${language === l.code ? 'active' : ''}`}><span className="language-code">{l.native}</span><span>{l.label}</span><small>{i === 0 ? 'Padrão' : l.code.toUpperCase()}</small>{language === l.code && <b>✓</b>}</button>)}</div>
            <div className="voice-footnote">A voz do navegador e a transcrição no servidor são recursos diferentes. A disponibilidade depende do navegador e do provedor configurado.</div>
          </section>

          <section className="panel activity-panel">
            <div className="panel-heading compact"><div className="panel-heading-icon amber">↯</div><div><span className="section-kicker">REGISTO DA SESSÃO</span><h2>Atividade recente</h2></div></div>
            <div className="activity-list">{activities.map(a => <div className="activity-row" key={a.id}><span className={`activity-mark ${a.tone}`} /><div><strong>{a.label}</strong><p>{a.detail}</p></div><time>{a.time}</time></div>)}</div>
            <p className="activity-footnote">Registos desta sessão do navegador; não representam agentes autónomos em execução.</p>
          </section>
        </aside>
      </div>
      <footer className="app-footer"><span>VÉRTICE · MODULAR AI WORKSPACE</span><span>Português por padrão · 5 idiomas · Skills com aprovação</span><a href="https://habblaud.com/" target="_blank" rel="noreferrer">Referência visual: Habblaud ↗</a></footer>
    </main>
  </div>;
}
