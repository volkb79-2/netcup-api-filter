# Devcontainer for DST-DNS Development
# Optimized for VSCode remote development and GitHub Actions
# Uses shared base image for consistency with other tool containers

# Note: We use mcr.microsoft.com/devcontainers base for VSCode integration
# Cannot use dstdns-base here as it conflicts with devcontainer user setup
# However, we install the same packages for consistency

FROM mcr.microsoft.com/devcontainers/python:1-3.11-bookworm

# Install system dependencies matching base image (as root)
# Binaries provided by each package:
#   gnupg: gpg, gpg2          lsb-release: lsb_release    curl: curl
#   wget: wget                git: git                    vim: vim, vi
#   less: less                netcat-traditional: nc      iputils-ping: ping
#   dnsutils: dig, nslookup   postgresql-client: psql     redis-tools: redis-cli
#   sqlite3: sqlite3          ripgrep: rg                 jq: jq
#   tree: tree                htop: htop                  bat: bat, batcat
#   fd-find: fdfind, fd       fzf: fzf                    tldr: tldr
#   httpie: http, https       mc: mc                      shellcheck: shellcheck
#   sshfs: sshfs
#
# Aliases configured in post-create.sh: cat→bat, grep→rg, find→fd, ps→htop, lt→tree
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
    sqlite3 \
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
    # Remote filesystem access
    fuse3 \
    sshfs \
    && echo "user_allow_other" >> /etc/fuse.conf \
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
