# Modelo de segurança

## Ativos
- Chaves de API, dados de conversas, arquivos ZIP e artefatos de skills.
- Integridade do processo backend e do host.
- Isolamento entre utilizadores/tenants.

## Fronteiras
1. Browser -> API: CORS restrito, limites de corpo, validação Pydantic.
2. Upload -> arquivo temporário: tamanho máximo durante streaming, não confiar em Content-Type.
3. ZIP -> diretório: validação de nomes, rejeição de links/especiais, entradas duplicadas, limites de número/tamanho/razão, extração controlada.
4. Skill -> catálogo: manifesto estrito, versão e ID validados, estado pending_review, aprovação administrativa.
5. Skill -> modelo: templates são contexto não confiável; não executam código nem recebem segredo.
6. Áudio -> provedor: limite de tamanho, idioma enumerado, arquivo temporário eliminado em finally.

## ZIP hardening
- Não extrair usando `extractall`.
- Rejeitar caminhos absolutos, `..`, separadores invertidos, hidden paths except the narrow allowlist of harmless GitHub metadata (`.github`, `.gitignore`, `.gitattributes`, `.editorconfig`), symlinks e tipos especiais.
- Limitar bytes comprimidos no endpoint, quantidade de entradas, bytes descomprimidos e razão de compressão.
- Validar containment após resolver destino.
- Em produção, fazer inspeção em processo/contêiner separado com CPU, memória e tempo limitados; arquivos de entrada podem explorar parsers mesmo sem traversal.

## Código arbitrário
O catálogo de skills desta versão só suporta `prompt_template`. Não importa módulos Python nem avalia JavaScript de um ZIP. Para ferramentas executáveis, exigir aprovação explícita e usar executor separado com usuário sem privilégios, filesystem read-only exceto diretório temporário, rede desligada por padrão, seccomp/AppArmor, quotas, timeout, lista de capacidades e logs de auditoria.

## Produção
- O token administrativo de desenvolvimento não substitui autenticação.
- Usar OIDC, RBAC, rate limits, quotas por usuário, proteção CSRF quando aplicável, gestão de segredos e auditoria.
- PostgreSQL com transações e armazenamento de objetos para multi-instância.
- Não expor o daemon Docker ao serviço web.
- Definir política de retenção e consentimento para gravações de áudio.
- O conteúdo de repositórios e transcrições é input não confiável para prompt injection.
