# Plano de testes e critérios de aceitação

## Automatizados — backend

- ZIP inválido, truncado, malformado ou com entradas perigosas é rejeitado.
- Path traversal, caminhos absolutos, links e bomb ZIP são rejeitados.
- Upload sem token ou com token incorreto é negado.
- Upload válido fica `pending_review` e não é usado no chat antes da aprovação.
- Aprovação ativa ferramentas declarativas; rejeição remove o pacote extraído.
- Idioma não permitido retorna 422; ausência de idioma resulta em `pt`.
- Upload maior que o limite retorna 413.
- Erros de provedor LLM e de transcrição são convertidos em respostas controladas.

Executar:

```bash
cd backend
pytest -q
```

## Frontend

- `npm ci` instala versões do lockfile (gerar e versionar `package-lock.json` num ambiente com acesso ao npm).
- `npm run build` conclui sem erros de TypeScript ou Vite.
- Em ecrãs de 320 px, 768 px e desktop, nenhum controlo essencial fica inacessível.
- Navegação por teclado, foco visível, rótulos de formulário e mensagens `role=status` funcionam.
- Testar estados da API: online, offline, erro 401/403, ZIP inválido e timeout.
- Testar os cinco idiomas; a escolha explícita não deve ser sobrescrita por uma skill.
- Testar microfone negado, Web Speech API ausente, MediaRecorder ausente, transcrição sem chave e áudio acima de 25 MB.

## Integração e segurança antes de produção

- Executar build e smoke test com o mesmo ambiente de deployment.
- Validar limites de upload através de proxy/reverse proxy e API.
- Testar uploads concorrentes com IDs iguais e versões repetidas.
- Introduzir persistência transacional e garantir que o estado de moderação é atómico.
- Testar autenticação OIDC/RBAC, rate limiting, quotas, logs sem segredos e políticas de retenção.
- Rever permissões do container, sistema de ficheiros, rede de saída e dependências.
- Fazer threat modeling e análise de dependências/SBOM antes de abrir uploads a utilizadores externos.
