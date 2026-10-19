# Escritório de IAs — auditoria técnica e plano de execução

**Estado da auditoria:** 2026-10-19  
**Repositório:** `objetivoemandamento/ia-empresarial`  
**Escopo:** escritório de IAs empresariais. Este projeto é separado do VÉRTICE/psicanálise.

## 1. Conclusão executiva

A branch `main` ainda não contém a aplicação-fonte importada. A árvore pública consultada contém o README, dois nomes para o mesmo ZIP e o script `scripts/import-zip.sh`. Portanto, não é correto afirmar que o produto está funcional apenas com base em resultados de testes relatados em conversas anteriores: esses testes precisam ser repetidos sobre o código que efetivamente estiver no repositório e no ambiente implantado.

O próximo marco técnico não é adicionar mais agentes. É recuperar/importar a fonte correta, auditar a aplicação real e estabelecer uma execução ponta a ponta segura e verificável.

## 2. Estado confirmado e limites

### Confirmado no repositório
- Branch padrão: `main`.
- O README descreve React + TypeScript + Vite no frontend e Python + FastAPI no backend.
- O README declara que a fonte do pacote ZIP ainda precisa ser importada para a branch.
- Existe `scripts/import-zip.sh`; ele verifica a presença de `package.json`, `frontend/` e `backend/`, exclui dependências/segredos/artefatos conhecidos e não usa `rsync --delete`.
- O script não faz commit nem push automaticamente.
- Há dois arquivos ZIP no repositório com o mesmo SHA, logo são duplicatas binárias.
- O código-fonte e o conteúdo interno do ZIP ainda precisam ser inspecionados antes de declarar o sistema pronto.

### Relatado anteriormente, mas precisa ser revalidado na fonte importada
- Painel e API para ativação/desativação de plugins.
- Catálogo persistido em JSON.
- Camada inicial de permissões com bloqueio por padrão.
- Testes de backend e build de frontend aprovados em uma cópia local anterior.
- Autenticação de produção, banco/fila durável, workers, executor real e recuperação após reinício ainda eram pendências.

**Não presumir:** que a aplicação está implantada, que as chaves de provedores estão configuradas, que o Supabase/Render/Vercel estão conectados, que o executor de plugins é real ou que os dispositivos móveis estão autenticados.

## 3. Arquitetura-alvo

### Plano de controle
- API autenticada para administrar agentes, ferramentas, tarefas, aprovações e políticas.
- Painel web como cliente da API; o frontend nunca deve guardar segredos de provedores.
- Identidade de usuário e papéis explícitos; separar autenticação de autorização.
- Auditoria de todas as mudanças de configuração e de todas as ações executadas.

### Orquestração
- CEO/Planner: transforma um objetivo em um plano estruturado; não executa ferramentas diretamente.
- Task Engine: persiste tarefas, dependências, tentativas, timeouts, leases e estados.
- Router/AI Gateway: escolhe um provedor/modelo por política, orçamento, latência e capacidade; permite fallback sem expor credenciais ao agente.
- Worker: executa uma tarefa de escopo limitado e retorna resultado estruturado e evidências.
- Reviewer/QA: verifica os resultados e pode rejeitar ou solicitar correção.
- Memória: distingue memória operacional, histórico de tarefas e documentos indexados; nunca trata texto recuperado como instrução confiável.

### Caminho obrigatório de execução

`Usuário autenticado → API → validação de objetivo → plano → autorização/política → fila persistente → worker isolado → ferramenta permitida → validação do resultado → auditoria → resposta`

Nenhum agente deve poder contornar a política chamando diretamente uma ferramenta.

## 4. Política de autorização

Implementar uma única função de decisão central e reutilizada por todos os executores. Cada decisão deve registrar: identidade/ator, tarefa, ferramenta, argumentos normalizados, escopo, decisão, motivo, instante e ID de correlação. Não registrar segredos nem dados desnecessários.

### Regras mínimas
- Negar por padrão ferramentas, operações e argumentos desconhecidos.
- Separar permissões de leitura, escrita, publicação, administração e ações financeiras.
- Usar lista explícita de ferramentas e esquemas de argumentos; nunca aceitar caminhos de arquivo, comandos shell, URLs internas ou nomes de ferramentas arbitrários diretamente de uma saída do modelo.
- Aprovação humana obrigatória para transferências/pagamentos, compras, ações legais, exclusão de dados, mudanças de permissões, publicação em produção e deploy.
- Aprovações devem ser específicas para ação, argumentos, ambiente, prazo e usuário aprovador; qualquer alteração material invalida a aprovação.
- Permitir revogação, expiração e idempotência. Bloquear replay de aprovações.
- Ferramentas em staging podem operar com dados sintéticos; produção exige controles adicionais e revisão.
- Limites de custo, chamadas, tempo, concorrência e tamanho de saída por tarefa, agente e usuário.

## 5. Persistência e confiabilidade

JSON local pode servir para protótipo de instância única, não como fonte autoritativa em produção com concorrência ou múltiplas instâncias.

Persistir em PostgreSQL/Supabase (ou serviço equivalente já aprovado):
- usuários/papéis;
- agentes e versões de configuração;
- catálogo de ferramentas e permissões;
- tarefas, etapas, tentativas e estados;
- aprovações e decisões de política;
- eventos de auditoria;
- uso/custo por provedor;
- referências a artefatos, com controle de acesso.

Usar fila durável ou tabela de jobs com locking/leases, retries com backoff, dead-letter, timeouts e idempotency keys. Não prometer execução “exatamente uma vez”; projetar tarefas para serem idempotentes e tratar efeitos externos de forma explícita.

## 6. Gateway de modelos e segredo

- Interface de provedor comum e adaptadores testáveis.
- Segredos apenas em variáveis de ambiente/secret manager do servidor.
- Nunca retornar chaves ao browser, incluí-las em logs, prompts, artefatos ou respostas de erro.
- Validar configuração no startup e expor apenas um health check sanitizado.
- Timeouts, limites de tokens, rate limits, retries limitados e fallback explícito.
- Registrar modelo/provedor, latência, tokens/custo quando disponíveis, erro e ID de correlação; não registrar conteúdo sensível por padrão.
- Se não houver credencial, marcar o provedor como indisponível e explicar isso sem simular resposta de IA.

## 7. Execução de ferramentas e isolamento

- Plugins declarativos descrevem capacidades; ativar um plugin não equivale a autorizá-lo nem a executar código.
- Cada ferramenta tem schema, escopo, permissões e timeout próprios.
- Executar código de terceiros em processo/contêiner isolado, sem acesso padrão a segredos, host, rede privada ou sistema de arquivos irrestrito.
- Permitir egress de rede por lista autorizada; bloquear SSRF e endereços internos/metadata.
- Sanitizar saída de ferramentas e tratá-la como dado não confiável.
- Logs de auditoria são append-only para o aplicativo e protegidos contra adulteração; acesso a logs é controlado.
- Nunca executar comandos sugeridos por modelo sem uma ferramenta específica, política e validação de argumentos.

## 8. Nós móveis e Automaton

Os telefones são workers/gateways opcionais, não a autoridade de segurança nem a fonte da verdade.

Antes de considerar um nó conectado:
- identidade individual por dispositivo e credencial revogável;
- TLS, autenticação mútua ou token de curta duração;
- heartbeat, versão do worker, capacidades declaradas e estado de saúde;
- tarefas assinadas/identificadas, prazo de validade, deduplicação e confirmação de resultado;
- lista de comandos permitidos, sem shell genérico por padrão;
- botão de revogação e isolamento remoto;
- testes de perda de rede, reinício, tarefa repetida e dispositivo comprometido.

Não expor a API central diretamente à internet sem autenticação, rate limiting e política de rede. Não armazenar tokens permanentes em arquivos compartilhados ou no frontend móvel.

## 9. Plano de implementação por gates

### Gate 0 — Recuperar e importar a fonte
1. Obter a cópia local mais recente e preservar uma cópia de segurança.
2. Confirmar hash do ZIP, listar conteúdo e verificar que não contém segredos.
3. Executar o script de importação numa branch de trabalho.
4. Revisar `git status`, `git diff --stat`, diff completo e arquivos excluídos.
5. Remover a duplicata do ZIP somente após confirmar a fonte e definir onde o artefato será armazenado.
6. Não fazer deploy nem mesclar até os gates seguintes.

### Gate 1 — Reprodutibilidade e segurança básica
- Instalação limpa do frontend e build.
- Instalação limpa das dependências backend e testes.
- Lint/typecheck, verificação de dependências e busca de segredos.
- Testes negativos para autenticação, autorização, CORS, validação de entrada e exposição de erros.
- CI executa esses passos em cada PR.

### Gate 2 — Identidade e política
- Autenticação de produção e RBAC.
- Política central e aprovação humana com expiração.
- Testes: acesso anônimo negado, papel insuficiente negado, ferramenta desconhecida negada, aprovação alterada/reutilizada negada.

### Gate 3 — Tarefa ponta a ponta
- Criar tarefa pela API autenticada.
- Persistir tarefa e eventos.
- Worker recebe, executa ferramenta de teste segura, devolve resultado e evidência.
- Interface mostra estado, logs sanitizados, erros e custo.
- Reiniciar serviço durante uma tarefa e verificar recuperação.

### Gate 4 — Gateway de modelos
- Integrar um provedor primeiro, com credencial em secret manager.
- Testar credencial ausente/inválida, timeout, limite, erro do provedor e fallback.
- Só depois adicionar outros provedores.

### Gate 5 — Ferramentas reais com sandbox
- Implementar uma ferramenta não destrutiva de ponta a ponta.
- Adicionar ferramentas uma por vez, cada qual com esquema, permissões, timeout, testes e aprovação conforme risco.
- Pagamentos, exclusão, publicação e deploy ficam bloqueados até existir aprovação auditável.

### Gate 6 — Produção e nós móveis
- Configurar Render/Vercel/Supabase apenas depois de confirmar projeto, ambiente e variáveis.
- Staging primeiro, smoke tests e rollback.
- Integrar dispositivos físicos por identidade individual e canal autenticado.
- Monitoramento, alertas, backup/restauração e procedimento de revogação.

## 10. Critérios objetivos para declarar “funcionando”

O sistema só pode ser considerado pronto para o escopo aprovado quando:
1. Um usuário autenticado cria uma tarefa real no painel.
2. A tarefa é persistida e sobrevive a reinício.
3. O orquestrador chama um provedor real configurado, sem simulação.
4. O worker executa apenas uma ferramenta permitida e isolada.
5. A política bloqueia uma ferramenta proibida mesmo quando solicitada pelo modelo.
6. A aprovação humana é exigida e auditada para ações críticas.
7. O resultado, falhas, tentativas e custos ficam visíveis com dados sensíveis redigidos.
8. Testes e CI passam em instalação limpa.
9. Backup e restauração foram testados.
10. Deploy e nó móvel passam smoke tests autenticados.

## 11. Riscos prioritários

| Risco | Mitigação |
|---|---|
| Fonte não importada/versão errada | Gate 0 e revisão de diff |
| Plugin ativo interpretado como autorizado | Estados separados: instalado, habilitado, autorizado, executável |
| Saída do modelo usada como comando | Tool schemas, política central e sandbox |
| JSON concorrente corromper estado | Banco transacional e fila durável |
| Chaves vazarem em frontend/logs | Secret manager e redaction |
| Agente exceder orçamento ou entrar em loop | Limites de custo, passos, tempo e tentativas |
| Tarefa duplicada produzir efeito externo repetido | Idempotência e reconciliação |
| Dispositivo comprometido executar ação | Identidade por nó, escopos mínimos e revogação |
| “Testes passaram” sem versão rastreável | CI ligado ao commit exato e artefatos de build |
| Deploy quebrar produção | Staging, health checks e rollback |

## 12. Próxima ação prática

Importar e auditar a fonte real em branch isolada. O repositório público consultado ainda não contém os diretórios `frontend/` e `backend/` na árvore da branch `main`; portanto, a implementação do executor ou da autorização não deve ser inventada a partir de documentação. Após a importação, este plano deve ser convertido em issues verificáveis e implementado módulo a módulo, com testes no código real.
