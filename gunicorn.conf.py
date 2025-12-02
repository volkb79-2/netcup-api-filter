"""
Gunicorn configuration for netcup-api-filter.

Dynamic resource regulation for CPU, network, and I/O concurrency.
All values are config-driven via environment variables.
"""

import os
import multiprocessing

# =============================================================================
# WORKER CONFIGURATION
# =============================================================================

# Worker class: 'sync', 'gevent', 'eventlet', 'gthread'
# - sync: Standard synchronous workers (default, simple)
# - gthread: Threaded workers (good for I/O-bound with minimal memory)
# - gevent/eventlet: Async I/O (best for high concurrency, requires extra deps)
worker_class = os.environ.get("GUNICORN_WORKER_CLASS", "gthread")

# Number of worker processes
# Default: 2 * CPU cores + 1 (optimal for mixed workloads)
# For I/O-bound (API proxy): can go higher
# For CPU-bound: stick to CPU count
def get_workers():
    env_workers = os.environ.get("GUNICORN_WORKERS")
    if env_workers:
        return int(env_workers)
    # Auto-calculate based on CPU cores
    cpu_count = multiprocessing.cpu_count()
    # Formula: 2*cores + 1 for mixed, but cap for memory constraints
    calculated = min(2 * cpu_count + 1, 8)
    return max(calculated, 2)  # Minimum 2 workers

workers = get_workers()

# Threads per worker (only for gthread worker class)
# More threads = better I/O concurrency per worker
# Rule of thumb: 2-4 threads per worker for I/O-bound apps
threads = int(os.environ.get("GUNICORN_THREADS", "4"))

# Max concurrent connections per worker (for async workers)
# gevent/eventlet can handle 1000+ concurrent connections
worker_connections = int(os.environ.get("GUNICORN_WORKER_CONNECTIONS", "1000"))


# =============================================================================
# TIMEOUTS & KEEPALIVE
# =============================================================================

# Request timeout (seconds) - kill worker if request takes longer
# Must be longer than your slowest API call (Netcup API can be slow)
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))

# Graceful shutdown timeout
graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", "30"))

# Keep-alive connections (seconds)
# Higher = fewer TCP handshakes, but more memory per connection
keepalive = int(os.environ.get("GUNICORN_KEEPALIVE", "5"))


# =============================================================================
# RESOURCE LIMITS
# =============================================================================

# Max requests per worker before restart (prevents memory leaks)
# 0 = disabled (worker never restarts)
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", "1000"))

# Jitter to prevent all workers restarting simultaneously
max_requests_jitter = int(os.environ.get("GUNICORN_MAX_REQUESTS_JITTER", "50"))

# Backlog queue size (pending connections waiting for a worker)
# Higher = better burst handling, but uses more memory
backlog = int(os.environ.get("GUNICORN_BACKLOG", "2048"))

# Limit request line size (bytes) - prevents DoS via huge URLs
limit_request_line = int(os.environ.get("GUNICORN_LIMIT_REQUEST_LINE", "4094"))

# Limit number of headers
limit_request_fields = int(os.environ.get("GUNICORN_LIMIT_REQUEST_FIELDS", "100"))

# Limit header field size (bytes)
limit_request_field_size = int(os.environ.get("GUNICORN_LIMIT_REQUEST_FIELD_SIZE", "8190"))


# =============================================================================
# NETWORK CONFIGURATION
# =============================================================================

# Bind address(es)
bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:5100")

# Reuse port (SO_REUSEPORT) - allows multiple processes to bind same port
reuse_port = os.environ.get("GUNICORN_REUSE_PORT", "true").lower() == "true"

# Forward proxy headers (when behind nginx/reverse proxy)
forwarded_allow_ips = os.environ.get("GUNICORN_FORWARDED_ALLOW_IPS", "*")

# Proxy protocol (if load balancer uses PROXY protocol)
proxy_protocol = os.environ.get("GUNICORN_PROXY_PROTOCOL", "false").lower() == "true"


# =============================================================================
# PROCESS MANAGEMENT
# =============================================================================

# Preload app before forking workers (faster startup, shared memory)
# Disable if app has issues with fork (e.g., database connections)
preload_app = os.environ.get("GUNICORN_PRELOAD_APP", "false").lower() == "true"

# Daemon mode
daemon = os.environ.get("GUNICORN_DAEMON", "false").lower() == "true"

# PID file
pidfile = os.environ.get("GUNICORN_PIDFILE", None)

# User/group (for privilege dropping)
user = os.environ.get("GUNICORN_USER", None)
group = os.environ.get("GUNICORN_GROUP", None)


# =============================================================================
# LOGGING
# =============================================================================

# Log level: debug, info, warning, error, critical
loglevel = os.environ.get("GUNICORN_LOGLEVEL", "info")

# Access log format
access_log_format = os.environ.get(
    "GUNICORN_ACCESS_LOG_FORMAT",
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'
)

# Log files (- for stdout/stderr)
accesslog = os.environ.get("GUNICORN_ACCESS_LOG", "-")
errorlog = os.environ.get("GUNICORN_ERROR_LOG", "-")

# Capture stdout/stderr from workers
capture_output = os.environ.get("GUNICORN_CAPTURE_OUTPUT", "true").lower() == "true"


# =============================================================================
# DEVELOPMENT OPTIONS
# =============================================================================

# Auto-reload on code changes (development only!)
reload = os.environ.get("GUNICORN_RELOAD", "false").lower() == "true"

# Reload engine: auto, poll, inotify
reload_engine = os.environ.get("GUNICORN_RELOAD_ENGINE", "auto")

# Check config on startup
check_config = os.environ.get("GUNICORN_CHECK_CONFIG", "false").lower() == "true"

# Spew (trace all function calls - very verbose!)
spew = os.environ.get("GUNICORN_SPEW", "false").lower() == "true"


# =============================================================================
# HOOKS (for monitoring/metrics)
# =============================================================================

def on_starting(server):
    """Called just before master process starts."""
    import logging
    logging.getLogger("gunicorn").info(
        f"Starting gunicorn with {workers} workers, "
        f"worker_class={worker_class}, threads={threads}"
    )

def worker_int(worker):
    """Called when worker receives SIGINT/SIGQUIT."""
    import logging
    logging.getLogger("gunicorn").warning(f"Worker {worker.pid} interrupted")

def worker_abort(worker):
    """Called when worker receives SIGABRT (timeout)."""
    import logging
    logging.getLogger("gunicorn").error(f"Worker {worker.pid} aborted (timeout?)")

def pre_fork(server, worker):
    """Called before worker is forked."""
    pass

def post_fork(server, worker):
    """Called after worker is forked."""
    pass

def pre_exec(server):
    """Called before exec() in worker."""
    pass

def child_exit(server, worker):
    """Called when worker exits."""
    import logging
    logging.getLogger("gunicorn").info(f"Worker {worker.pid} exited")
