FROM python:3.12-bookworm

ARG DEBIAN_FRONTEND=noninteractive
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=${USER_UID}
ARG NODE_VERSION=v24.19.0

# Linux prerequisites for course tooling
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    ca-certificates \
    xz-utils \
    zstd \
    gnupg \
    lsb-release \
    apt-transport-https \
    sudo \
  && rm -rf /var/lib/apt/lists/*

# Devcontainer non-root user
RUN groupadd --gid ${USER_GID} ${USERNAME} \
  && useradd --uid ${USER_UID} --gid ${USER_GID} -m ${USERNAME} \
  && echo "${USERNAME} ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/${USERNAME} \
  && chmod 0440 /etc/sudoers.d/${USERNAME}

# uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
  && install -m 0755 /root/.local/bin/uv /usr/local/bin/uv \
  && install -m 0755 /root/.local/bin/uvx /usr/local/bin/uvx

# Node.js 24 LTS (Promptfoo)
RUN set -eux; \
  case "$(uname -m)" in \
    aarch64|arm64) NODE_ARCH=arm64 ;; \
    x86_64|amd64) NODE_ARCH=x64 ;; \
    *) echo "Unsupported architecture"; exit 1 ;; \
  esac; \
  curl -fsSLO "https://nodejs.org/dist/${NODE_VERSION}/node-${NODE_VERSION}-linux-${NODE_ARCH}.tar.xz"; \
  tar -xJf "node-${NODE_VERSION}-linux-${NODE_ARCH}.tar.xz" -C /usr/local --strip-components=1; \
  rm "node-${NODE_VERSION}-linux-${NODE_ARCH}.tar.xz"

# Claude Code
RUN install -d -m 0755 /etc/apt/keyrings \
  && curl -fsSL https://downloads.claude.ai/keys/claude-code.asc \
    -o /etc/apt/keyrings/claude-code.asc \
  && echo "deb [signed-by=/etc/apt/keyrings/claude-code.asc] https://downloads.claude.ai/claude-code/apt/stable stable main" \
    > /etc/apt/sources.list.d/claude-code.list \
  && apt-get update \
  && apt-get install -y --no-install-recommends claude-code \
  && rm -rf /var/lib/apt/lists/*

# Azure CLI
RUN curl -sL https://aka.ms/InstallAzureCLIDeb | bash \
  && rm -rf /var/lib/apt/lists/*

# kubectl
RUN set -eux; \
  case "$(uname -m)" in \
    aarch64|arm64) KUBE_ARCH=arm64 ;; \
    x86_64|amd64) KUBE_ARCH=amd64 ;; \
    *) echo "Unsupported architecture"; exit 1 ;; \
  esac; \
  KUBE_VERSION="$(curl -L -s https://dl.k8s.io/release/stable.txt)"; \
  curl -fsSLO "https://dl.k8s.io/release/${KUBE_VERSION}/bin/linux/${KUBE_ARCH}/kubectl"; \
  install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl; \
  rm kubectl

# Ollama (CPU-only runtime for on-prem simulation)
RUN set -eux; \
  case "$(uname -m)" in \
    aarch64|arm64) OLLAMA_ARCH=arm64 ;; \
    x86_64|amd64) OLLAMA_ARCH=amd64 ;; \
    *) echo "Unsupported architecture"; exit 1 ;; \
  esac; \
  curl -fsSL "https://ollama.com/download/ollama-linux-${OLLAMA_ARCH}.tar.zst" \
    | tar --zstd -x -C /usr

RUN npm install -g promptfoo

# Course Python packages (system-wide; project deps installed via uv sync in postCreate)
RUN uv pip install --system \
    "pydantic>=2" \
    fastapi \
    langchain \
    langgraph \
    "mcp[cli]" \
    opentelemetry-api \
    opentelemetry-sdk \
    tenacity \
    pybreaker \
    pytest \
    ruff \
    mypy \
    pip-audit \
    deepeval \
    inspect-ai

WORKDIR /workspaces/claims-intake
USER ${USERNAME}

ENV PATH="/home/${USERNAME}/.local/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    SERVICE_ENV=local
