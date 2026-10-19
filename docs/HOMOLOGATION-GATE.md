# VÉRTICE — Gate de homologação

Este checklist é deliberadamente conservador. O repositório remoto ainda não contém o código-fonte da versão local `7996d60`; não considerar os ZIPs atualmente versionados como a versão final.

## 1. Integridade da origem
- [ ] Recuperar a versão exata `7996d60` do ambiente em que foi criada.
- [ ] Confirmar a presença da migração `0008_human_tasks`, do módulo `human_tasks` e da interface “Minhas tarefas”.
- [ ] Inspecionar o ZIP e excluir credenciais, arquivos `.env`, bancos locais, artefatos de build e dependências instaladas.
- [ ] Importar em branch de homologação, nunca diretamente em `main`.
- [ ] Revisar o diff completo e verificar a cadeia de migrações antes do commit.

## 2. Qualidade automatizada
- [ ] CI aprovada: testes backend e build frontend.
- [ ] Teste de migração: upgrade, downgrade e upgrade novamente em PostgreSQL descartável.
- [ ] Teste de API: persistência, autenticação, autorização, idempotência e trilha de auditoria.
- [ ] Testes de segurança para tarefas que tentem disfarçar Pix, transferências, saques ou pagamentos de saída em campos indiretos.
- [ ] E2E visual da aba “Minhas tarefas” em desktop e mobile.
- [ ] Verificação de segredos e dependências vulneráveis.

## 3. Infraestrutura — sem ativação automática
- [ ] Confirmar custo total e limites de uso antes de qualquer provisionamento.
- [ ] Manter PostgreSQL suspenso e Supabase inativo até haver autorização explícita de custo e plano de recuperação.
- [ ] Não reutilizar serviços Render ligados ao repositório `objetivoemandamento/Vertice` sem validar destino, configuração e impacto.
- [ ] Preparar ambiente isolado de homologação com secrets fora do código.
- [ ] Validar health check, logs, backups e restauração.

## 4. IA e pagamentos
- [ ] Manter gasto com IA em R$ 0/mês; não habilitar API paga.
- [ ] Confirmar suporte e forma real de execução do GLM-5.2 antes de declarar inferência funcional.
- [ ] Implementar Mercado Pago somente em sandbox primeiro.
- [ ] Testar assinatura/verificação de webhooks, idempotência e conciliação.
- [ ] Não habilitar transferências de saída, Pix, saques ou pagamentos financeiros.

## 5. Critério de liberação
- [ ] Todos os gates automatizados aprovados.
- [ ] Nenhum segredo ou permissão excessiva identificado.
- [ ] Smoke tests remotos concluídos em infraestrutura saudável.
- [ ] Revisão humana da PR e plano de rollback registrados.
- [ ] Só então avaliar exposição pública.

**Estado atual:** bloqueado por ausência do código-fonte mais recente no remoto e infraestrutura hospedada indisponível. Não marcar como pronto até que as evidências acima existam.
