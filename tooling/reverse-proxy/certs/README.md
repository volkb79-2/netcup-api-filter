# Test Certificates (Fallback)

## Purpose

This directory contains **self-signed test certificates** for `naf.localtest.me`. These are FALLBACK certificates used when real Let's Encrypt certificates are not available.

## When to Use

**DON'T use these certificates** if you have access to real Let's Encrypt certificates on the host. Instead, use `./auto-detect-fqdn.sh` to automatically configure the proxy with production Let's Encrypt certificates.

**Use these certificates only when:**
- Let's Encrypt certificates are not available on the Docker host
- Testing TLS infrastructure without internet access
- Quick local testing where browser security warnings are acceptable

## Structure

```
certs/
├── live/
│   └── naf.localtest.me/
│       ├── fullchain.pem  (self-signed certificate)
│       └── privkey.pem    (private key)
└── archive/
    └── naf.localtest.me/
        └── (same files, no symlinks for test certs)
```

This mimics the Let's Encrypt directory structure but contains self-signed certificates instead of CA-signed ones.

## Configuration

To use these test certificates:

1. **Set `LE_CERT_BASE` to staged path:**
   ```bash
   # In proxy.env
   LE_CERT_BASE=/tmp/netcup-local-proxy/certs
   LOCAL_TLS_DOMAIN=naf.localtest.me
   ```

2. **Stage certificates to host-visible path:**
   ```bash
   ./stage-proxy-inputs.sh
   ```

3. **Update /etc/hosts (if needed):**
   ```bash
   echo "127.0.0.1 naf.localtest.me" | sudo tee -a /etc/hosts
   ```

4. **Start proxy:**
   ```bash
   docker compose --env-file proxy.env up -d
   ```

## Limitations

⚠️ **Browser Security Warnings**: Self-signed certificates trigger browser warnings:
- Chrome: "Your connection is not private" (NET::ERR_CERT_AUTHORITY_INVALID)
- Firefox: "Warning: Potential Security Risk Ahead"
- curl: Requires `-k/--insecure` flag

⚠️ **Not Production Parity**: Secure cookie behavior differs from production:
- Production: Real CA-signed certificates, no warnings
- Test certs: Browser may block cookies or require exceptions

## Recommended Workflow

**Instead of using these test certificates**, use the auto-detection workflow for 100% production parity:

```bash
# Auto-detect public FQDN and configure real Let's Encrypt certificates
./auto-detect-fqdn.sh --verify-certs

# Render and stage configuration
./render-nginx-conf.sh
./stage-proxy-inputs.sh

# Start proxy with real certificates
docker compose --env-file proxy.env up -d
```

See `HTTPS_LOCAL_TESTING.md` for complete documentation.

## Regenerating Test Certificates

If you need to regenerate these self-signed certificates:

```bash
cd certs/live/naf.localtest.me

# Generate new private key
openssl genrsa -out privkey.pem 2048

# Generate self-signed certificate (valid for 1 year)
openssl req -new -x509 -key privkey.pem -out fullchain.pem -days 365 \
  -subj "/CN=naf.localtest.me"

# Copy to archive directory (optional, for structure parity)
mkdir -p ../../archive/naf.localtest.me
cp privkey.pem ../../archive/naf.localtest.me/
cp fullchain.pem ../../archive/naf.localtest.me/
```

## See Also

- `../README.md` - Complete local proxy documentation
- `../../HTTPS_LOCAL_TESTING.md` - HTTPS testing with real Let's Encrypt certificates
- `../auto-detect-fqdn.sh` - Auto-detection script for production certificates
