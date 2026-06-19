# Security Policy

## Reporting Security Issues

**DO NOT open public GitHub issues for security vulnerabilities.**

Please email security concerns to: **security@neraium.com**

Response time: 48 hours

## Security Practices

### Dependencies
- Core backend and frontend dependencies are version-pinned in-repo
- Automated dependency vulnerability scanning runs in CI for backend and frontend dependencies
- Current CI policy blocks on reported backend vulnerabilities and critical production-frontend vulnerabilities

### Authentication & Authorization
- CORS is restricted to approved origins
- Request IDs are emitted for audit correlation
- Protected write routes require an authenticated session or configured service token in production
- Role boundaries are enforced in production for operator and admin surfaces
- Login/session storage persists in a dedicated auth database, with local SQLite for tests/dev and Postgres in production
- Admin controls can create users, activate or deactivate accounts, and revoke sessions
- Production login attempts are rate-limited in application code
- Set `NERAIUM_AUTH_DATABASE_URL` to a shared Postgres database before multi-instance rollout

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

- **v1.2** - Dedicated auth database storage and CI dependency scanning documented (2026-06-19)
- **v1.1** - Documentation aligned with currently implemented controls (2026-06-19)
- **v1.0** - Initial security policy (2026-05-16)
