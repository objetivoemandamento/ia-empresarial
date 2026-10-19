# Validação e estado do protótipo

Data desta revisão: 2026-10-18.

## Verificações executadas nesta revisão

- **25 testes pytest passaram**, incluindo novos testes para impedir transições inválidas de moderação, permitir nova submissão após rejeição e exigir configuração de LLM em produção.
- `python -m compileall -q app tests` passou.
- Nova execução nesta sessão: `python -m pytest -q` — **25 passed em 0,45 s**.
- Tentativa de `npm install --no-audit --no-fund` nesta sessão expirou após 120 s. A verificação TypeScript global confirmou que as dependências `react`, `react-dom` e os tipos de Vite não estão instalados; os erros de JSX e de inferência daí resultantes não permitem avaliar os tipos reais da aplicação.
- A integridade do ZIP de origem foi verificada antes da revisão.
- O catálogo continua a persistir em JSON com gravação por substituição atómica; alterações de estado são revertidas em memória quando a gravação falha.
- A instalação de skills continua declarativa: não executa código arbitrário enviado em ZIP.

## Correções realizadas

- Aprovação e rejeição agora só são permitidas para skills em `pending_review`.
- Uma skill rejeitada pode ser enviada novamente para nova revisão; skills pendentes ou ativas não podem ser substituídas silenciosamente.
- Erros de transição de estado retornam HTTP 409.
- O lock é inicializado antes do carregamento do catálogo.
- O ambiente `production` exige token administrativo forte e configuração explícita de `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` e `ALLOWED_ORIGINS`, evitando iniciar silenciosamente em modo de demonstração.

## Não confirmado nesta revisão

- **Build React/Vite e verificação completa de tipos:** `npm install --no-audit --no-fund` expirou após 120 s nesta sessão. Portanto, `npm run build` continua pendente e **não pode ser declarado concluído**.
- Docker/Compose: não executados.
- Provedor LLM real e transcrição de áudio real: dependem de credenciais e de serviços externos.
- Teste de carga, concorrência multi-processo, teste de invasão e acessibilidade com leitores de ecrã: não executados.

## Antes de produção

- Num ambiente com acesso ao npm, executar `npm install`, confirmar e versionar `package-lock.json`, depois executar `npm run build`.
- Fazer testes de integração com o provedor LLM e de transcrição nos cinco idiomas.
- Para múltiplas instâncias, migrar o catálogo JSON para armazenamento transacional partilhado (por exemplo, PostgreSQL).
- Implementar OIDC/RBAC, rate limiting, auditoria, retenção de áudio e sandbox isolado se vier a ser necessário executar código de terceiros.
- Rever dependências, SBOM, headers de segurança e configuração do proxy antes de exposição pública.
