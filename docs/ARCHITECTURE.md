# Arquitetura técnica — Modular AI Workspace

## 1. Objetivo e limites

A aplicação organiza uma conversa com um modelo de linguagem, capacidades declarativas instaláveis e ferramentas de áudio. A interface adota o conceito visual de um escritório com salas de trabalho e personagens em pixel art, inspirado na apresentação pública do Habblaud (https://habblaud.com/), mas usa identidade, código e componentes próprios. A interface não afirma que existam agentes autónomos ou sessões de Claude/Codex em execução: as salas são módulos desta aplicação.

## 2. Componentes

- **Frontend:** React + TypeScript + Vite. Mantém estado transitório da conversa, seleção de idioma, capacidades selecionadas, avisos e atividade da sessão.
- **API:** FastAPI. Expõe health check, upload/listagem/moderação de capacidades, chat e transcrição de áudio.
- **Gestor de capacidades:** valida um `manifest.json`, extrai ZIP com política de segurança, coloca a capacidade em `pending_review` e só ativa ferramentas declarativas após aprovação.
- **Motor LLM:** chama um endpoint compatível com OpenAI Chat Completions quando configurado; a configuração e a chave permanecem no servidor.
- **Áudio:** reconhecimento de voz do navegador quando disponível; `MediaRecorder` + endpoint de transcrição server-side como alternativa; síntese de voz via Web Speech API.

## 3. Fluxo de instalação de capacidade

1. Administrador escolhe um ZIP e envia o token no cabeçalho `Authorization: Bearer …`.
2. API faz upload limitado por bytes para um ficheiro temporário.
3. O extrator valida estrutura, caminhos, quantidade, tamanho expandido, razão de compressão, entradas especiais e duplicadas antes de escrever.
4. O gestor exige exatamente um `manifest.json` válido e rejeita fontes executáveis/binaries no modo declarativo.
5. Capacidade é registada como `pending_review`.
6. Administrador aprova ou rejeita. Apenas capacidades `active` explicitamente selecionadas pelo utilizador entram no contexto do chat.
7. O motor só interpreta `prompt_template`; não importa nem executa código Python, JavaScript, shell ou binários do ZIP.

## 4. Idiomas

Códigos permitidos: `pt`, `en`, `zh`, `es`, `hi`. A aplicação inicia em `pt`. Uma escolha explícita da interface tem prioridade; no modo `auto`, o backend pode usar uma sugestão de manifesto aprovado, se estiver dentro da lista de idiomas da capacidade; a última alternativa é português. A disponibilidade de voz varia por navegador, sistema operativo e provedor de transcrição.

## 5. Estado atual e limitações

- O catálogo de capacidades é mantido em memória; um reinício perde o catálogo. A persistência precisa de PostgreSQL e armazenamento de objetos.
- O token administrativo é uma proteção mínima para desenvolvimento, não substitui OIDC/RBAC, rotação de segredos, rate limiting, auditoria ou proteção CSRF adequada ao modelo de autenticação escolhido.
- O projeto não oferece um executor de código de terceiros. Para capacidades executáveis, criar um serviço separado com isolamento real (container/VM por tarefa), usuário sem privilégios, filesystem efémero, rede bloqueada por padrão, quotas de CPU/memória/PIDs/tempo, logs auditáveis e aprovação humana.
- A aplicação não cria salas multi-tenant, não gere utilizadores e não implementa agentes autónomos de desenvolvimento. O painel de atividade regista ações reais desta sessão do navegador.
- O chat não usa streaming nesta versão. Streaming via SSE/WebSocket é uma evolução separada.

## 6. Variáveis de ambiente

Consulte `backend/.env.example`. Nunca incluir segredos no frontend, no manifesto, no ZIP ou no repositório Git.
