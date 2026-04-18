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
- [ ] `python manage.py test tests.test_permission_matrix -v 1`
- [ ] `python manage.py audit_null_organizations`
- [ ] Manual smoke paths validated (if UI behavior changed)
- [ ] Manual smoke not required (no UI/UX change)

## Release and Rollback

- Deploy steps:
- Rollback steps:
- Feature flag / kill switch (if any):
- [ ] Rollback steps tested on staging or drill link added below

## Evidence

- Screenshots / logs / links:
- Smoke evidence:
- Rollback evidence:
