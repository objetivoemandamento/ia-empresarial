# IA Empresarial

Repositório de desenvolvimento do **IA Empresarial**, uma plataforma modular de IA com interface web, backend FastAPI, chat, recursos de voz e instalação controlada de capacidades.

## Estrutura
- `frontend/`: React, TypeScript e Vite.
- `backend/`: FastAPI, endpoints e controles de segurança.
- `skills/`: exemplos de capacidades declarativas.
- `docs/`: arquitetura, segurança e plano de testes.

## Requisitos
- Node.js 20 ou superior
- Python 3.11 ou superior

## Executar
Na raiz do repositório:

```bash
npm install
npm run verify
npm run dev
```

Consulte `README.md`, `docs/ARCHITECTURE.md` e `docs/SECURITY.md` antes de publicar em produção. Configure as variáveis de ambiente usando os arquivos `.env.example`; não versione segredos.

## Estado de validação
O build de produção do pacote foi relatado como concluído em ambiente Codespaces para outro workspace, mas este ZIP ainda precisa ser validado após ser importado no repositório de destino. A integração real com dispositivos móveis não está implementada/confirmada neste pacote.
