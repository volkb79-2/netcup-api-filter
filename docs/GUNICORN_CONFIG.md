# Gunicorn Worker Configuration

Dynamic resource regulation for CPU, network, and I/O concurrency.

## Quick Reference

| Setting | Default | Description |
|---------|---------|-------------|
| `GUNICORN_WORKER_CLASS` | `gthread` | Worker type (sync/gthread/gevent/eventlet) |
| `GUNICORN_WORKERS` | auto | Number of worker processes |
| `GUNICORN_THREADS` | 4 | Threads per worker (gthread only) |
| `GUNICORN_WORKER_CONNECTIONS` | 1000 | Concurrent connections (async workers) |
| `GUNICORN_TIMEOUT` | 120 | Request timeout (seconds) |
| `GUNICORN_MAX_REQUESTS` | 1000 | Requests before worker restart |

## Worker Classes

### `sync` (Default, Simple)
```
One request at a time per worker.
Workers = CPU cores
Concurrency = workers
```
Best for: CPU-bound tasks, simple deployments

### `gthread` (Recommended for API Proxy)
```
Multiple threads per worker for I/O-bound tasks.
Workers = CPU cores
Threads = 4 per worker
Concurrency = workers × threads
```
Best for: **This app** (API proxy with I/O waits)

### `gevent` / `eventlet` (High Concurrency)
```
Async I/O via greenlets.
Workers = 1-2
Connections = 1000+ per worker
Concurrency = workers × connections
```
Best for: WebSockets, long-polling, 10K+ concurrent connections

## Resource Scaling Formulas

### CPU-bound workloads
```bash
GUNICORN_WORKERS=$(nproc)          # 1 worker per CPU
GUNICORN_WORKER_CLASS=sync
```

### I/O-bound (API proxy, database)
```bash
GUNICORN_WORKERS=$(($(nproc) * 2 + 1))  # 2*CPU+1
GUNICORN_WORKER_CLASS=gthread
GUNICORN_THREADS=4
```

### High concurrency (10K+ connections)
```bash
GUNICORN_WORKERS=2
GUNICORN_WORKER_CLASS=gevent
GUNICORN_WORKER_CONNECTIONS=2000
```

## Memory Management

### Prevent memory leaks
```bash
GUNICORN_MAX_REQUESTS=1000      # Restart after 1000 requests
GUNICORN_MAX_REQUESTS_JITTER=50 # Stagger restarts (±50 requests)
```

Workers restart after handling `max_requests ± jitter` to prevent memory accumulation.

### Memory per worker (estimates)
| Worker Class | Memory/Worker |
|--------------|---------------|
| sync | ~50-100 MB |
| gthread | ~100-200 MB |
| gevent | ~50-150 MB |

## Network Tuning

### Connection handling
```bash
GUNICORN_BACKLOG=2048      # Queue size for pending connections
GUNICORN_KEEPALIVE=5       # HTTP keep-alive (seconds)
GUNICORN_REUSE_PORT=true   # SO_REUSEPORT for load balancing
```

### Behind reverse proxy (nginx)
```bash
GUNICORN_FORWARDED_ALLOW_IPS="*"  # Trust X-Forwarded-* headers
```

## Timeout Configuration

```bash
GUNICORN_TIMEOUT=120           # Kill worker if request exceeds this
GUNICORN_GRACEFUL_TIMEOUT=30   # Time for graceful shutdown
```

**Important**: `GUNICORN_TIMEOUT` must be longer than your slowest API call. Netcup API can take 30-60 seconds for large zone operations.

## Environment Profiles

### Development (local testing)
```bash
GUNICORN_WORKERS=2
GUNICORN_THREADS=4
GUNICORN_RELOAD=true           # Auto-reload on code changes
GUNICORN_LOGLEVEL=debug
```

### Production (webhosting)
```bash
GUNICORN_WORKERS=4
GUNICORN_THREADS=4
GUNICORN_RELOAD=false
GUNICORN_LOGLEVEL=warning
GUNICORN_MAX_REQUESTS=1000
```

### High-availability
```bash
GUNICORN_WORKERS=8
GUNICORN_WORKER_CLASS=gevent
GUNICORN_WORKER_CONNECTIONS=2000
GUNICORN_BACKLOG=4096
```

## Monitoring Hooks

The config includes hooks for observability:

```python
def on_starting(server):     # Master process starting
def worker_int(worker):      # Worker interrupted (SIGINT)
def worker_abort(worker):    # Worker timed out (SIGABRT)
def child_exit(server, worker):  # Worker exited
```

These log to gunicorn's logger for debugging worker lifecycle issues.

## Usage

### With config file (recommended)
```bash
gunicorn -c gunicorn.conf.py passenger_wsgi:application
```

### Override specific settings
```bash
GUNICORN_WORKERS=8 GUNICORN_THREADS=8 gunicorn -c gunicorn.conf.py app:app
```

### Without config file (explicit flags)
```bash
gunicorn --workers=4 --threads=4 --worker-class=gthread --timeout=120 app:app
```

## Webhosting Considerations

On shared hosting (Passenger), these settings may be overridden by the host. The config file is primarily for:

1. **Local development** - Full control via `deploy.sh local`
2. **Dedicated servers** - Direct gunicorn deployment
3. **Containers** - Docker/Kubernetes deployments

For Passenger (netcup webhosting), worker management is handled by Passenger itself.
