# Devcontainer for DST-DNS Development
# Optimized for VSCode remote development and GitHub Actions
# Uses shared base image for consistency with other tool containers

# Note: We use mcr.microsoft.com/devcontainers base for VSCode integration
# Cannot use dstdns-base here as it conflicts with devcontainer user setup
# However, we install the same packages for consistency

FROM mcr.microsoft.com/devcontainers/python:1-3.11-bookworm

# Install system dependencies matching base image (as root)
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Core utilities (matching base)
    ca-certificates \
    gnupg \
    lsb-release \
    curl \
    wget \
    git \
    vim \
    less \
    bash-completion \
    # Network tools (matching base)
    netcat-traditional \
    iputils-ping \
    dnsutils \
    # Database clients (matching base)
    postgresql-client \
    redis-tools \
    # Additional development tools
    ripgrep \
    jq \
    tree \
    htop \
    bat \
    fd-find \
    fzf \
    tldr \
    httpie \
    mc \
    shellcheck \
    && rm -rf /var/lib/apt/lists/*

# Install yq (YAML processor)
RUN wget -qO /usr/local/bin/yq https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 \
    && chmod +x /usr/local/bin/yq

# Switch to vscode user for Poetry installation
USER vscode

# # Install Poetry
# RUN curl -sSL https://install.python-poetry.org | python3 - \
#     && echo 'export PATH="/home/vscode/.local/bin:$PATH"' >> /home/vscode/.bashrc

# # Configure Poetry
# RUN /home/vscode/.local/bin/poetry config virtualenvs.create false

# # Set PATH for Poetry
# ENV PATH="/home/vscode/.local/bin:$PATH"

# NOTE: Python dependencies are installed via post-create.sh
# This prevents build failures from requirements.txt issues
# and allows for more flexible dependency management
# Python packages will match those in dstdns-base for consistency

# Switch back to root for any final setup, then container will run as vscode
USER root
