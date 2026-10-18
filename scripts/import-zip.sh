#!/usr/bin/env bash
set -Eeuo pipefail

ARCHIVE="${1:-ia-empresarial.zip}"
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

if [[ ! -f "$ARCHIVE" ]]; then
  echo "ERRO: não encontrei '$ARCHIVE'. Coloque o ZIP na raiz do repositório ou informe o caminho." >&2
  exit 1
fi
if ! command -v unzip >/dev/null 2>&1; then
  echo "ERRO: o comando unzip não está instalado." >&2
  exit 1
fi
if ! command -v rsync >/dev/null 2>&1; then
  echo "ERRO: o comando rsync não está instalado." >&2
  exit 1
fi

unzip -q "$ARCHIVE" -d "$TMP"
SOURCE="$TMP/ia-empresarial"
if [[ ! -d "$SOURCE" ]]; then
  SOURCE="$TMP"
fi
if [[ ! -f "$SOURCE/package.json" || ! -d "$SOURCE/frontend" || ! -d "$SOURCE/backend" ]]; then
  echo "ERRO: o ZIP não contém a estrutura esperada (package.json, frontend/, backend/)." >&2
  exit 1
fi

echo "Importando arquivos do pacote para: $ROOT"
# Não copia segredos, dependências instaladas ou artefatos de compilação.
# Não usa --delete: arquivos existentes no repositório não serão apagados automaticamente.
rsync -a \
  --exclude='.git/' \
  --exclude='node_modules/' \
  --exclude='.env' \
  --exclude='**/.env' \
  --exclude='.output/' \
  --exclude='dist/' \
  --exclude='.wrangler/' \
  --exclude='__pycache__/' \
  --exclude='.pytest_cache/' \
  "$SOURCE/" "$ROOT/"

echo
echo "Importação concluída. Nenhum commit ou push foi feito automaticamente."
echo "Revise antes de publicar:"
echo "  git status --short"
echo "  git diff --stat"
echo "  git add -A && git commit -m 'Importa Modular AI Workspace' && git push origin main'"
