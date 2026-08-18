#!/usr/bin/env bash
# Start Ollama and optionally pull course models (llama3.2:3b, mistral).
set -euo pipefail

OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"
OLLAMA_MODELS="${OLLAMA_MODELS:-llama3.2:3b mistral}"
LOG="/tmp/ollama.log"
MODE="${1:-all}"

ensure_ollama_home() {
  local home="${HOME}/.ollama"
  mkdir -p "${home}"
  if [[ ! -w "${home}" ]]; then
    sudo chown -R "$(id -un):$(id -gn)" "${home}"
  fi
}

api_ready() {
  curl -sf "http://${OLLAMA_HOST}/api/version" >/dev/null 2>&1
}

start_server() {
  ensure_ollama_home

  if api_ready; then
    return 0
  fi

  if pgrep -x ollama >/dev/null 2>&1; then
    for _ in $(seq 1 30); do
      api_ready && return 0
      sleep 1
    done
    echo "Ollama process running but API not ready; see ${LOG}" >&2
    return 1
  fi

  ollama serve >"${LOG}" 2>&1 &
  for _ in $(seq 1 60); do
    if api_ready; then
      return 0
    fi
    sleep 1
  done

  echo "Ollama failed to start; see ${LOG}" >&2
  return 1
}

pull_models() {
  for model in ${OLLAMA_MODELS}; do
    echo "Pulling ${model}..."
    ollama pull "${model}"
  done
}

case "${MODE}" in
  serve)
    start_server
    ;;
  pull)
    start_server
    pull_models
    ;;
  all)
    start_server
    pull_models
    ;;
  *)
    echo "Usage: $0 [serve|pull|all]" >&2
    exit 1
    ;;
esac
