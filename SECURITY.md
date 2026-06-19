# Security Policy

## Reporting Security Issues

**DO NOT open public GitHub issues for security vulnerabilities.**

Please email security concerns to: **security@neraium.com**

Response time: 48 hours

## Security Practices

### Dependencies
- Core backend and frontend dependencies are version-pinned in-repo
- Automated dependency vulnerability scanning is not yet enforced in CI
- Manual audit commands may be run during release prep, but they are not yet a standing control

### Authentication & Authorization
- CORS is restricted to approved origins
- Request IDs are emitted for audit correlation
- Shared-token header auth still exists for non-browser tooling and smoke checks
- Login/session storage is file-backed and not yet production-grade
- Rate limiting is not yet configured in application code

### Data Protection
- HTTPS is enforced in production through HSTS headers
- CSP headers reduce basic XSS exposure
- Browser clients no longer source a shared access token from frontend build-time env
- Secrets should still be injected at deploy time and managed outside the repo

### Headers
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Content-Security-Policy: default-src 'self'`
- `Strict-Transport-Security` in HTTPS production

## Pre-Deployment Security Checklist

- [ ] All environment variables properly configured
- [ ] Secrets injected at deployment time (not in code)
- [ ] CORS origins set to production domain
- [ ] Database backups enabled and tested
- [ ] SSL/TLS certificates valid
- [ ] Rate limiting thresholds configured
- [ ] Monitoring and alerting active
- [ ] Incident response plan documented
- [ ] Security audit completed
- [ ] Penetration testing scheduled (optional)

## Compliance

- Some OWASP-style mitigations are in place, but the platform is not yet fully hardened
- Data retention and privacy controls still require environment-specific review before broader production use

## Version History

- **v1.1** - Documentation aligned with currently implemented controls (2026-06-19)
- **v1.0** - Initial security policy (2026-05-16)
