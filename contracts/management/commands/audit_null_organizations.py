from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.db.migrations.executor import MigrationExecutor

from contracts.models import (
    ApprovalRequest,
    ApprovalRule,
    ClauseCategory,
    ClauseTemplate,
    Counterparty,
    DSARRequest,
    DataInventoryRecord,
    EthicalWall,
    LegalHold,
    OrganizationMembership,
    RetentionPolicy,
    SignatureRequest,
    Subprocessor,
    TransferRecord,
    Workflow,
)


MODEL_CONFIGS = [
    (Workflow, 'title'),
    (Counterparty, 'name'),
    (ClauseCategory, 'name'),
    (ClauseTemplate, 'title'),
    (EthicalWall, 'name'),
    (SignatureRequest, 'signer_email'),
    (DataInventoryRecord, 'title'),
    (DSARRequest, 'reference_number'),
    (Subprocessor, 'name'),
    (TransferRecord, 'title'),
    (RetentionPolicy, 'title'),
    (LegalHold, 'title'),
    (ApprovalRule, 'name'),
    (ApprovalRequest, 'approval_step'),
]


def _membership_orgs_for_user(user_id):
    if not user_id:
        return []
    return list(
        OrganizationMembership.objects
        .filter(user_id=user_id, is_active=True, organization__is_active=True)
        .values_list('organization__slug', flat=True)
        .distinct()
    )


class Command(BaseCommand):
    help = 'Audit records that still have NULL organization after tenant backfill.'

    @staticmethod
    def _ensure_no_unapplied_migrations():
        connection = connections['default']
        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes()
        plan = executor.migration_plan(targets)
        if not plan:
            return
        preview = ', '.join(f'{migration.app_label}.{migration.name}' for migration, _ in plan[:5])
        if len(plan) > 5:
            preview = f'{preview}, ...'
        raise CommandError(
            'Unapplied migrations detected. Run `python manage.py migrate` before auditing '
            f'(pending: {preview}).'
        )

    def handle(self, *args, **options):
        self._ensure_no_unapplied_migrations()
        self.stdout.write('NULL organization audit')
        self.stdout.write('----------------------')

        total_rows = 0
        for model, label_field in MODEL_CONFIGS:
            rows = list(model.objects.filter(organization__isnull=True))
            if not rows:
                continue

            total_rows += len(rows)
            self.stdout.write(f'\n{model.__name__}: {len(rows)} row(s)')
            for row in rows:
                label = getattr(row, label_field, '')
                owner_user_id = getattr(row, 'created_by_id', None)
                if owner_user_id is None:
                    owner_user_id = getattr(row, 'specific_approver_id', None)
                owner_orgs = _membership_orgs_for_user(owner_user_id)

                if len(owner_orgs) == 1:
                    suggestion = f'backfill to {owner_orgs[0]}'
                elif len(owner_orgs) > 1:
                    suggestion = 'manual decision: owner belongs to multiple orgs'
                else:
                    suggestion = 'manual decision: no tenant anchor; likely legacy shared seed data'

                self.stdout.write(
                    f'  id={row.id} label={label!r} owner_user_id={owner_user_id} owner_orgs={owner_orgs} suggestion={suggestion}'
                )

        if total_rows == 0:
            self.stdout.write('\nNo NULL organization rows found.')
            return

        raise CommandError(
            f'Found {total_rows} row(s) with NULL organization in tenant-owned models.'
        )
