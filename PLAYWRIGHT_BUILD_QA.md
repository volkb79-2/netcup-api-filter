# Playwright Container Build Management - Q&A

## Your Questions Answered

### 1. "Do we manually need to stop playwright, rebuild, and then use start-playwright.sh?"

**NO** - This is now fully automated! The `start-playwright.sh` script now:

1. **Detects changes** automatically (Dockerfile, requirements.root.txt, mcp_server.py)
2. **Rebuilds** if any inputs changed
3. **Stops old container** before rebuilding
4. **Starts fresh container** with new image

**Just run**:
```bash
cd tooling/playwright && ./start-playwright.sh
```

The script handles everything - no manual steps needed!

### 2. "What would be required to have this script detect if a new build is required and do this on demand?"

**IMPLEMENTED** ✅ - The script now uses **content-based change detection**:

#### How It Works:

1. **Hash Calculation**: Combines MD5 hashes of build inputs:
   ```bash
   calculate_build_hash() {
       {
           cat "${SCRIPT_DIR}/Dockerfile"
           cat "${SCRIPT_DIR}/requirements.root.txt"
           cat "${SCRIPT_DIR}/mcp_server.py"
       } | md5sum | cut -d' ' -f1
   }
   ```

2. **Stores Hash**: Writes hash to `.build-hash` file (gitignored)

3. **Compares on Each Run**:
   - Image doesn't exist → rebuild
   - No `.build-hash` file → rebuild
   - Hash mismatch → rebuild
   - Hash matches → skip rebuild (fast!)

4. **Automatic Rebuild**:
   ```bash
   if needs_rebuild; then
       docker stop playwright && docker rm playwright
       docker compose build --progress=plain
   fi
   ```

#### Benefits:

- ✅ **Fast** - Only rebuilds when needed (hash check is instant)
- ✅ **Accurate** - Detects any file changes via content hash
- ✅ **Automatic** - No manual intervention required
- ✅ **Transparent** - Shows which hash changed and why

#### Example Output:

```
Screenshot directory: /path/to/deploy-local/screenshots
✓ Environment configured

Build inputs changed - rebuild required
  Previous: abc123def456
  Current:  789ghi012jkl

Building Playwright container...
...
✓ Container built successfully
```

### 3. "What is the difference between `docker buildx build` and `docker buildx bake`?"

#### `docker buildx build` - Single Image Builder

**What**: Builds one Docker image with advanced features

**When**: Cross-platform builds, advanced caching, multi-stage optimizations

**Example**:
```bash
# Multi-platform build (e.g., Mac M1 + Linux AMD64)
docker buildx build \
    --platform linux/amd64,linux/arm64 \
    -t generic-playwright:latest \
    --push \
    .
```

**Features**:
- Multi-architecture support (amd64, arm64, etc.)
- Remote caching (Docker registry, S3, GitHub Actions cache)
- Parallel builds across platforms
- BuildKit optimizations

**Not needed for this project** - Single platform (Linux x86_64), local use only

---

#### `docker buildx bake` - Multi-Image Orchestrator

**What**: Builds multiple related images from a single definition file

**When**: Complex projects with multiple interconnected images

**Example** (`docker-bake.hcl`):
```hcl
group "default" {
    targets = ["frontend", "backend", "database"]
}

target "frontend" {
    dockerfile = "frontend/Dockerfile"
    tags = ["myapp/frontend:latest"]
}

target "backend" {
    dockerfile = "backend/Dockerfile"
    tags = ["myapp/backend:latest"]
}

target "database" {
    dockerfile = "database/Dockerfile"
    tags = ["myapp/database:latest"]
}
```

**Run**:
```bash
docker buildx bake
```

**Features**:
- Builds multiple images in one command
- Shares build context and layers
- Configurable via HCL/JSON files
- Dependencies between images

**Not needed for this project** - Single container, docker-compose.yml is simpler

---

#### `docker compose build` - Our Choice ✅

**What**: Builds image using docker-compose.yml configuration

**When**: **Preferred for this project** - respects compose context, networks, build args

**Example**:
```bash
docker compose build --progress=plain
```

**Why we use it**:
1. Reads `build.context` and `build.dockerfile` from compose file
2. Respects `.env` file for build args automatically
3. Consistent with `docker compose up -d` workflow
4. Simpler than buildx for single-platform, local use

**Comparison Table**:

| Feature | `docker compose build` | `docker buildx build` | `docker buildx bake` |
|---------|----------------------|---------------------|-------------------|
| **Use Case** | Single container + compose | Multi-platform builds | Multiple related images |
| **Config File** | `docker-compose.yml` | Command-line args | `docker-bake.hcl` |
| **Multi-platform** | ❌ | ✅ | ✅ |
| **Multi-image** | One at a time | One at a time | All at once |
| **Complexity** | Simple | Medium | Complex |
| **Our Fit** | ✅ Perfect | Overkill | Overkill |

### 4. "From what directory should we build tooling/playwright? To have it self-contained, best from its own directory?"

**ANSWER**: **Yes, always from `tooling/playwright/` directory** ✅

#### Why Self-Contained Matters:

The build context determines what files Docker can access during the build.

**Docker Compose Build Context**:
```yaml
# docker-compose.yml
services:
  playwright:
    build:
      context: .              # <- "." means "current directory"
      dockerfile: Dockerfile
```

**`context: .` means** "Use the directory containing docker-compose.yml as the build context"

#### Directory Structure:

```
tooling/playwright/          # <- Build context (self-contained)
├── Dockerfile              # Accessible via: COPY Dockerfile ...
├── requirements.root.txt   # Accessible via: COPY requirements.root.txt ./
├── mcp_server.py          # Accessible via: COPY mcp_server.py /app/
├── docker-compose.yml     # Defines build context
├── .build-hash            # Auto-generated (gitignored)
└── .env                   # Auto-generated (gitignored)
```

#### Self-Contained Build:

```bash
cd tooling/playwright      # Enter self-contained directory
./start-playwright.sh      # Script automatically uses correct context
```

**The script handles this**:
```bash
# Inside start-playwright.sh
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"        # Always changes to script's directory
docker compose build      # Uses correct build context
```

#### What If We Used Parent Directory?

**❌ WRONG** (would break):
```bash
cd /workspaces/netcup-api-filter   # Parent directory
docker compose -f tooling/playwright/docker-compose.yml build
# Build context would be /workspaces/netcup-api-filter (WRONG!)
# Dockerfile COPY commands would fail
```

#### Self-Contained Benefits:

✅ **Portable** - Works from any calling directory
✅ **Isolated** - Only includes necessary files
✅ **Fast** - Smaller build context = faster transfers
✅ **Secure** - Doesn't expose parent directory contents

#### Running From Anywhere:

```bash
# From project root
./tooling/playwright/start-playwright.sh  # Works!

# From tooling/
./playwright/start-playwright.sh         # Works!

# From tooling/playwright/
./start-playwright.sh                    # Works!
```

**All work** because the script changes to its own directory:
```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"
```

## Summary

1. **Automatic rebuild** - ✅ Implemented with content-based change detection
2. **Build detection** - ✅ MD5 hash of Dockerfile + requirements + mcp_server.py
3. **docker buildx build** - Multi-platform builder (not needed)
4. **docker buildx bake** - Multi-image orchestrator (not needed)
5. **docker compose build** - ✅ Our choice (simple, effective)
6. **Self-contained** - ✅ Always build from `tooling/playwright/` directory

## Quick Reference

```bash
# Just run this - everything else is automatic!
cd tooling/playwright && ./start-playwright.sh

# Force rebuild (ignore cache)
rm tooling/playwright/.build-hash
./tooling/playwright/start-playwright.sh

# Check build hash
cat tooling/playwright/.build-hash
```

## Files Changed

- `tooling/playwright/start-playwright.sh` - Added automatic rebuild detection
- `tooling/playwright/.gitignore` - Added `.build-hash`
- `PLAYWRIGHT_CONTAINER.md` - Documented auto-rebuild feature
- `PLAYWRIGHT_BUILD_QA.md` - This file (comprehensive Q&A)

## Testing

The feature was tested successfully:
- Container rebuild detected (no .build-hash file)
- Old container stopped automatically
- New image built with progress output
- Container started with new image
- Build hash stored: `997e267cbbcfc266097c69dcd11dc73a`
- Total time: ~45 seconds (full rebuild)
- Subsequent runs: <1 second (hash match, no rebuild)
