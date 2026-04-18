#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT_FILE="$ROOT_DIR/docs/QUERY_PLAN_2026-04-13.md"

cd "$ROOT_DIR"

.venv/bin/python manage.py shell <<'PY' > "$OUT_FILE"
from contracts.models import Contract
from contracts.tenancy import get_user_organization
from django.contrib.auth import get_user_model

print('# Query Plan Report (2026-04-13)')
print('')
print('Generated via `QuerySet.explain()` for core contract repository/list paths.')
print('')

User = get_user_model()
user = User.objects.filter(is_superuser=True).first() or User.objects.first()
org = get_user_organization(user) if user else None

if org is None:
    print('No organization/user available; report could not evaluate tenant-scoped queries.')
else:
    qs1 = Contract.objects.filter(organization=org).order_by('-updated_at')
    qs2 = Contract.objects.filter(organization=org, status='ACTIVE').order_by('-updated_at')
    qs3 = Contract.objects.filter(organization=org, end_date__isnull=False).order_by('end_date')
    qs4 = Contract.objects.filter(organization=org, renewal_date__isnull=False).order_by('renewal_date')

    plans = [
        ('org ordered by updated_at desc', qs1),
        ('org + status ordered by updated_at desc', qs2),
        ('org + end_date ordered by end_date', qs3),
        ('org + renewal_date ordered by renewal_date', qs4),
    ]

    for title, qs in plans:
        print(f'## {title}')
        print('')
        print('```')
        print(qs.explain())
        print('```')
        print('')
PY

echo "Wrote $OUT_FILE"
