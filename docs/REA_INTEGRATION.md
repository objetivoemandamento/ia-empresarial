# REA no ciclo de engenharia do Escritório de IAs

## Finalidade

REA (Reverse Engineer Anything) é uma ferramenta de análise local e MCP para investigar aplicações, código JavaScript/Electron, binários e comportamento de runtime. É uma ferramenta de engenharia assistida, não um modelo de linguagem e não um executor geral de tarefas de produção.

## Como usar com segurança

1. Instale a versão oficial a partir do repositório `morluto/rea` e siga as instruções da versão instalada. A versão recebida nesta sessão declara requisitos recentes de Node.js (22.19+, 24.11+ ou 26+); o Node disponível no ambiente local é 22.16.0, portanto o CLI não foi executado nesta rodada.
2. Registre REA no agente de desenvolvimento local via MCP/stdio, seguindo a configuração oficial. Não exponha o processo local por uma API pública sem autenticação, isolamento e análise de ameaças.
3. Para cada investigação, registre alvo, versão, licença, pergunta, evidências, arquivos/linhas relevantes, incertezas e testes que confirmam a implementação independente.
4. Reimplemente somente comportamentos que possam ser reproduzidos legitimamente; não copie código proprietário, credenciais, segredos, dados pessoais ou ativos não licenciados.
5. Faça a implementação em branch isolada, execute testes e revisão de segurança e só então proponha integração.

## Limite de integração

O roteador multi-modelo atual suporta endpoints OpenAI-compatible. REA ainda não está conectado como ferramenta executável do backend/Render. O processo REA é uma ferramenta de desenvolvimento local e não deve ser tratado como disponível dentro do serviço Render. A integração futura precisa de um adaptador MCP explicitamente configurado, lista de ferramentas permitidas, timeouts, limites de saída, logs de auditoria e aprovação para ações externas.

## Critérios de aceite

- [ ] Node compatível e pacote oficial REA instalado.
- [ ] Sessão MCP local iniciada sem expor portas públicas.
- [ ] Chamada de ferramenta de leitura retorna evidência e identificador de ferramenta.
- [ ] O resultado é consumido pelo fluxo CEO/revisor, preservando origem e incertezas.
- [ ] Tentativas de escrita, publicação, rede ou execução de código ficam bloqueadas ou aguardam aprovação.
- [ ] Testes cobrem timeout, processo encerrado, saída inválida e ausência do REA.

**Status atual:** REA foi adicionado como auditoria estática opcional do frontend no GitHub Actions, com relatório como artefato e sem bloquear o build se o CLI não puder executar. Isso não é uma conexão MCP de runtime nem prova de execução de ferramentas. Não marcar REA como conectado ao backend até passar os critérios acima.
