# IA Empresarial

Plataforma de IA empresarial modular com chat de texto e voz, transcrição multilíngue e instalação controlada de capacidades a partir de ZIPs de repositórios. A interface usa a metáfora de escritório/salas de trabalho como inspiração visual de Habblaud, com identidade e componentes próprios.

## Arquitetura

- `backend/`: FastAPI, autenticação administrativa de desenvolvimento, upload seguro, catálogo de skills, chat e endpoint de transcrição.
- `frontend/`: React + TypeScript + Vite, chat, upload ZIP, seleção de idioma e voz no navegador.
- `skills/`: exemplo de skill declarativa.
- `tests/`: testes unitários de segurança do ZIP e do catálogo.
- `docker-compose.yml`: ambiente de desenvolvimento.
- `docs/SECURITY.md`: modelo de ameaça e controles.
- `docs/ARCHITECTURE.md`: arquitetura, fluxos e limites atuais.
- `docs/REFERENCE-UI.md`: decisões de UX inspiradas na referência.
- `docs/TEST-PLAN.md`: plano de testes e critérios de aceitação.

## Requisitos

- Python 3.11+
- Node.js 20+
- Para transcrição server-side: `OPENAI_API_KEY` e `openai` SDK (opcional).
- Para executar a aplicação via Compose: Docker Engine e Docker Compose.

## Inicialização rápida

### Backend
```bash
cd backend
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Frontend em `http://localhost:5173`, API em `http://127.0.0.1:8000`.

## Segurança importante

O modo padrão só aceita skills declarativas com `manifest.json` e ferramentas do tipo `prompt_template`. ZIPs são inspecionados antes da extração, rejeitando traversal, links, nomes perigosos, arquivos excessivos e bomb ZIP. Não é feito `exec()` de código Python/JavaScript enviado no ZIP.

Para executar código de terceiros, use um executor separado, não privilegiado, com rede desativada, filesystem temporário, limites de CPU/memória/tempo e política de aprovação. O Dockerfile/Compose desta entrega executa a própria aplicação; não existe executor de código de skills. Não ligue o daemon Docker ao serviço web para processar uploads não confiáveis.

## Modelo de linguagem

Por padrão, o endpoint de chat usa modo de eco controlado e aplica as skills declarativas aprovadas ao contexto. Configure `LLM_BASE_URL`, `LLM_API_KEY` e `LLM_MODEL` para um endpoint compatível com OpenAI Chat Completions. Não envie segredos ao frontend. O backend permanece em modo de demonstração quando o provedor não está configurado; o health check e o cabeçalho da interface distinguem esse estado de um modelo real conectado.

## Áudio e idiomas

Idiomas permitidos: `pt`, `en`, `zh`, `es`, `hi`. Português (`pt`) é padrão. O utilizador pode escolher um idioma explicitamente; em modo automático, um manifesto de skill aprovada pode sugerir `default_language`, desde que esse idioma esteja na lista `languages`. A preferência explícita do utilizador prevalece. O frontend usa Web Speech API quando disponível para reconhecimento e síntese. O endpoint opcional `/api/audio/transcribe` usa o SDK OpenAI com um modelo de transcrição configurável; a disponibilidade dos idiomas depende do modelo/provider. A API não promete que qualquer modelo reconheça todos os idiomas com a mesma qualidade.

## Instalar uma skill

O ZIP deve conter `manifest.json` na raiz ou dentro de uma única pasta superior. Exemplo:

```json
{
  "schema_version": "1.0",
  "id": "summarize-text",
  "name": "Resumir texto",
  "version": "1.0.0",
  "description": "Resume texto fornecido pelo usuário.",
  "languages": ["pt", "en"],
  "tools": [{
    "name": "summarize",
    "description": "Gera instruções de resumo para o modelo.",
    "kind": "prompt_template",
    "template": "Resuma o seguinte texto em tópicos claros:\n{{input}}"
  }]
}
```

Upload cria uma versão em estado `pending_review`. Um administrador aprova para `active`. As skills não executam código arbitrário; o motor só interpreta tipos de ferramenta explicitamente suportados.

## Minhas tarefas e decisões humanas

A área **Minhas tarefas** usa a API autenticada `/api/human-tasks` e SQLite para registrar tarefas, prioridades, responsáveis, dependências, idempotência e histórico de auditoria. Tarefas podem exigir aprovação humana; a aprovação guarda apenas o escopo exato e não executa ações externas. Pix, saques e transferências/pagamentos de saída são bloqueados. A migração versionada e os contratos estão em `backend/migrations/versions/0008_human_tasks.py` e `docs/HUMAN-TASKS.md`.

A persistência depende de um volume durável montado em `DATA_DIR`. Não publique usando filesystem efêmero se os registros precisarem sobreviver a reinícios. O painel de tarefas usa o mesmo token administrativo da área Capacidades.

## Interface

A interface apresenta um escritório digital com salas para conversa, capacidades e voz, ilustração em pixel art feita em CSS, resumo de estado e atividade da sessão. A atividade é real apenas para eventos desta página; o painel não simula agentes autónomos. Veja `docs/REFERENCE-UI.md`.

## Limitações do protótipo

- O catálogo de skills é persistido em JSON e restaurado ao reiniciar; é adequado apenas para uma instância. Para produção com múltiplas instâncias, usar PostgreSQL e storage partilhado.
- A autenticação administrativa usa token compartilhado; antes de produção multiusuário, substituir por OIDC/RBAC, sessões seguras, rate limiting e auditoria de identidade individual.
- O chat mantém histórico no cliente; não é um sistema multi-tenant pronto para produção.
- A ativação dinâmica afeta o catálogo de ferramentas declarativas, não os pesos internos do modelo.
- O checkout real e os webhooks de Mercado Pago não estão implementados. Não tratar esta versão como pronta para receber pagamentos.
- O GLM-5.2 não está embutido nem configurado; sem endpoint compatível configurado, o chat permanece em modo de demonstração. Não foi ativada nenhuma API paga.

## Deploy (Render + Vercel)

1. Push this repository to a GitHub repository you control.
2. In Render, create a Blueprint from the repository and use `render.yaml`. Set `ALLOWED_ORIGINS` to the exact deployed Vercel origin (for example `https://your-app.vercel.app`, no trailing slash). Keep `ADMIN_TOKEN` generated by Render and copy it only into the private admin UI/configuration; never commit secrets.
3. In Vercel, import the `frontend` directory as the project root. Add `VITE_API_BASE` with the Render backend URL, without a trailing slash, then deploy.
4. Configure `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL` in Render using a provider that implements the OpenAI-compatible `/chat/completions` API. The API runs in demo mode when these are missing. Configure `OPENAI_API_KEY` separately if using server-side audio transcription.
5. Re-deploy the frontend after changing its environment variables. Verify `https://YOUR-BACKEND/api/health`, chat, audio transcription, and admin-only ZIP moderation.

The Render blueprint requests a persistent disk for the declarative skills catalog and extracted skill packages. Persistent disks are available only on supported paid Render services. For other hosts, mount a persistent writable volume at `DATA_DIR`. This prototype's JSON catalog is appropriate for a single API instance; use a transactional database before scaling horizontally.

## Local validation

Backend: `cd backend && pip install -r requirements.txt && pytest -q`
Frontend: `cd frontend && npm install && npm run build`

## Inicialização unificada em desenvolvimento

Na raiz do projeto, instale as dependências do frontend e do backend e depois execute o script:

```bash
python -m pip install -r backend/requirements.txt
npm run install:frontend
npm run dev
```

O `start.sh` inicia o FastAPI e o Vite em paralelo e encerra ambos ao terminar.

- Frontend: `http://localhost:5173`
- API: `http://localhost:8000`
- Health check: `http://localhost:8000/api/health`
- Swagger/OpenAPI: `http://localhost:8000/docs`

Em GitHub Codespaces, encaminhe a porta **5173** na aba Ports para testar o painel. O Vite encaminha `/api` ao backend local na porta 8000, evitando configurar um domínio público para a API durante o desenvolvimento. Encaminhe também a porta **8000** quando quiser acessar diretamente o Swagger ou o health check. Para uma implantação separada do frontend, defina `VITE_API_BASE` com a URL pública da API e configure a origem correspondente em `ALLOWED_ORIGINS`.

O backend não implementa atualmente um protocolo dedicado para controlar nós móveis. A porta 8000 expõe os endpoints documentados em `/docs`; não considere isso uma conexão de cluster móvel já operacional.

## Validação completa no GitHub Codespaces

Na raiz do repositório, execute:

```bash
npm run verify
```

O comando instala as dependências do frontend e backend, executa o build do React/Vite e roda os testes Python. Ele para no primeiro erro e só informa sucesso quando todas as etapas terminam com código de saída zero.

Para iniciar o frontend e o backend em modo de desenvolvimento, depois da validação:

```bash
npm run dev
```

Portas locais esperadas: frontend `5173`, backend `8000`, documentação da API `8000/docs`. A integração com nós móveis requer implementação e validação específicas; essas URLs não comprovam, por si só, comunicação com os celulares.

See `docs/REA_INTEGRATION.md` for the safe local REA/MCP integration plan and current limitations.

## CEO agent orchestration

The separate **Agentes IA** tab creates a persisted run via `POST /api/agent-runs`. The CEO plans 1–15 tasks, up to four independent tasks run concurrently, each textual result is reviewed, and the CEO produces a final delivery. Runs and approval decisions are stored in SQLite under `DATA_DIR`.

- `GET /api/agent-runs` and `GET /api/agent-runs/{id}`: list and inspect runs (admin token required).
- `POST /api/agent-runs`: start a run with `{"goal":"..."}`.
- `POST /api/agent-runs/{id}/retry`: retry a failed/interrupted run.
- `POST /api/agent-approvals/{id}/decision`: approve/reject a sensitive task with `{"approve":true|false}`.
- `GET /api/policies` and admin-only `PATCH /api/policies`: manage optional permissions; protected controls cannot be changed.
- The `Conexões de IA` tab generates `AI_ROUTER_MODELS_JSON` for multiple providers. Configure each `api_key_env` variable in the backend/Render environment; do not paste API keys into the UI or Git.

The orchestration layer produces and reviews text. Approval does **not** execute publishing, messaging, shell, browser or code execution. Those actions need separate real adapters, sandboxing and end-to-end tests. Financial transfers, payments and withdrawals are blocked. The REA tool is local developer tooling and is not connected to the production API yet; see `docs/REA_INTEGRATION.md`.

See `docs/VALIDACAO_UI.md` for the supplied simulator compatibility assessment and the Playwright desktop/mobile validation strategy.

Before deploying, follow `docs/RELEASE_CHECKLIST.md`; production requires valid provider credentials and end-to-end acceptance tests.
