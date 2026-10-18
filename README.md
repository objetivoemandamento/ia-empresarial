# IA Empresarial — Modular AI Workspace

Plataforma modular para organizar conversas com IA, capacidades revisáveis (skills), áudio e integração futura com agentes e nós móveis.

> **Estado de importação:** o repositório foi criado, mas o código-fonte do pacote ZIP ainda precisa ser importado para esta branch. O ZIP preparado está disponível na conversa como `ia-empresarial.zip`.

## Estrutura prevista

- `frontend/`: React, TypeScript e Vite.
- `backend/`: API Python/FastAPI, segurança, provedores de IA e capacidades.
- `skills/`: capacidades declarativas com manifesto.
- `docs/`: arquitetura, segurança e plano de testes.
- `scripts/`: validação e inicialização local.
- `docker-compose.yml`, `render.yaml` e workflow CI: configurações de desenvolvimento/implantação.

## Importar o pacote fonte

1. Baixe o ZIP anexado na conversa e envie-o para a raiz deste repositório no Codespaces com o nome `ia-empresarial.zip`.
2. Execute:

```bash
bash scripts/import-zip.sh ia-empresarial.zip
```

3. Revise as alterações antes de publicar:

```bash
git status --short
git add -A
git commit -m "Importa Modular AI Workspace"
git push origin main
```

O script extrai o pacote em uma pasta temporária, verifica a estrutura e copia os arquivos para a raiz sem copiar `node_modules`, segredos ou artefatos de build.

## Validação após a importação

```bash
npm install
npm run build
python -m pip install -r backend/requirements.txt
python -m pytest -q backend
```

A execução dos testes Python exige as dependências de `backend/requirements.txt`. Build de frontend e testes do backend são validações separadas.

## Segurança

- Nunca commite chaves de provedores ou arquivos `.env` reais.
- Use `.env.example` como referência e configure credenciais nas variáveis de ambiente do ambiente de execução.
- ZIPs de capacidades devem ser validados; não execute código arbitrário de pacotes no processo principal.
- A integração com nós móveis só deve ser considerada pronta após existir endpoint específico, autenticação e testes ponta a ponta.
