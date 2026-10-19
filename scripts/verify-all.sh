#!/usr/bin/env bash
# Validação completa do Modular AI Workspace para Codespaces/Linux.
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail() { echo "ERRO: $*" >&2; exit 1; }
command -v node >/dev/null 2>&1 || fail "Node.js não encontrado. Use um Codespace com Node.js instalado."
command -v npm >/dev/null 2>&1 || fail "npm não encontrado."
command -v python >/dev/null 2>&1 || fail "Python não encontrado."

[[ -f frontend/package.json ]] || fail "frontend/package.json não encontrado."
[[ -f backend/requirements.txt ]] || fail "backend/requirements.txt não encontrado."

printf '\n[1/4] Instalando dependências do frontend...\n'
npm --prefix frontend install

printf '\n[2/4] Compilando frontend...\n'
npm --prefix frontend run build

printf '\n[3/4] Instalando dependências do backend...\n'
python -m pip install -r backend/requirements.txt

printf '\n[4/4] Executando testes do backend...\n'
python -m compileall -q backend/app backend/tests
python -m pytest -q backend

printf '\nSUCESSO: instalação, build do frontend e testes do backend concluídos.\n'
printf 'Para iniciar os dois serviços, execute: npm run dev\n'
