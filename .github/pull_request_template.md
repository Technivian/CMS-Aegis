## Summary

- What changed:
- Why:

## Risk and Scope

- Tenant isolation impact: `none | low | medium | high`
- RBAC/permissions impact: `none | low | medium | high`
- Migration impact: `none | backward-compatible | breaking`
- Data/privacy impact: `none | low | medium | high`

## Verification

- [ ] `python manage.py check`
- [ ] `python manage.py test tests.test_cross_tenant_isolation -v 1`
- [ ] `python manage.py audit_null_organizations`
- [ ] Manual smoke paths validated (if UI behavior changed)

## Release and Rollback

- Deploy steps:
- Rollback steps:
- Feature flag / kill switch (if any):

## Evidence

- Screenshots / logs / links:
