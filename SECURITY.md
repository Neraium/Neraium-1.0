# Security Policy

## Reporting Security Issues

**DO NOT open public GitHub issues for security vulnerabilities.**

Please email security concerns to: **security@neraium.com**

Response time: 48 hours

## Security Practices

### Dependencies
- ✅ All dependencies pinned to prevent supply chain attacks
- ✅ Weekly security audits via `pip-audit` and `npm audit`
- ✅ Automated dependency checks in CI/CD

### Authentication & Authorization
- ✅ CORS restricted to approved origins
- ✅ Request ID correlation for audit trails
- ✅ Rate limiting configured per endpoint

### Data Protection
- ✅ HTTPS enforced in production (HSTS headers)
- ✅ CSP headers prevent XSS attacks
- ✅ Secrets never committed to repository

### Headers
- ✅ X-Content-Type-Options: nosniff
- ✅ X-Frame-Options: DENY
- ✅ Referrer-Policy: strict-origin-when-cross-origin
- ✅ Content-Security-Policy: default-src 'self'
- ✅ Strict-Transport-Security (production)

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

- OWASP Top 10 mitigations in place
- CWE-listed vulnerabilities addressed
- Data retention policies documented
- Privacy/GDPR considerations reviewed

## Version History

- **v1.0** - Initial security policy (2026-05-16)
