from django.core.management.base import BaseCommand
from django.db import transaction

from contracts.models import Budget, DueDiligenceProcess, OrganizationMembership


class Command(BaseCommand):
    help = (
        'Backfill organization FK for Budget and DueDiligenceProcess rows where '
        'organization is NULL using owner-user memberships.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Persist updates. Without this flag the command runs in dry-run mode.',
        )

    @staticmethod
    def _resolve_single_org_for_user(user):
        if not user:
            return None, 'no user on row'

        memberships = list(
            OrganizationMembership.objects
            .filter(user=user, is_active=True, organization__is_active=True)
            .select_related('organization')
            .order_by('id')
        )
        if len(memberships) == 1:
            return memberships[0].organization, None
        if len(memberships) == 0:
            return None, f'user {user.username} has no active memberships'
        return None, f'user {user.username} has multiple active memberships'

    def _backfill_queryset(self, queryset, user_attr_name, apply_changes):
        updated = 0
        skipped = 0

        for obj in queryset.iterator():
            user = getattr(obj, user_attr_name, None)
            org, reason = self._resolve_single_org_for_user(user)
            if not org:
                skipped += 1
                self.stdout.write(
                    self.style.WARNING(f'skip {obj.__class__.__name__}:{obj.id} - {reason}')
                )
                continue

            updated += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"assign {obj.__class__.__name__}:{obj.id} -> organization={org.id} ({org.slug})"
                )
            )
            if apply_changes:
                obj.organization = org
                obj.save(update_fields=['organization'])

        return updated, skipped

    def handle(self, *args, **options):
        apply_changes = options['apply']
        mode = 'APPLY' if apply_changes else 'DRY-RUN'
        self.stdout.write(self.style.NOTICE(f'Running in {mode} mode'))

        budget_qs = Budget.objects.filter(organization__isnull=True)
        dd_qs = DueDiligenceProcess.objects.filter(organization__isnull=True)

        self.stdout.write(f'Budget rows with NULL organization: {budget_qs.count()}')
        self.stdout.write(f'DueDiligenceProcess rows with NULL organization: {dd_qs.count()}')

        with transaction.atomic():
            budget_updated, budget_skipped = self._backfill_queryset(
                budget_qs,
                user_attr_name='created_by',
                apply_changes=apply_changes,
            )
            dd_updated, dd_skipped = self._backfill_queryset(
                dd_qs,
                user_attr_name='lead_attorney',
                apply_changes=apply_changes,
            )

            if not apply_changes:
                transaction.set_rollback(True)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Backfill summary'))
        self.stdout.write(f'- Budget: updated={budget_updated}, skipped={budget_skipped}')
        self.stdout.write(f'- DueDiligenceProcess: updated={dd_updated}, skipped={dd_skipped}')
        if not apply_changes:
            self.stdout.write(self.style.WARNING('Dry-run only. Re-run with --apply to persist changes.'))
