from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from contracts.models import Contract, Notification, OrganizationMembership


class Command(BaseCommand):
    help = 'Send renewal and expiration reminder notifications for contracts.'

    def handle(self, *args, **options):
        today = timezone.localdate()
        created_count = 0

        contracts = (
            Contract.objects
            .filter(
                organization__is_active=True,
                status__in=[Contract.Status.ACTIVE, Contract.Status.APPROVED],
            )
            .filter(Q(end_date__isnull=False) | Q(renewal_date__isnull=False))
            .select_related(
                'organization',
                'created_by',
                'matter__responsible_attorney',
                'client__responsible_attorney',
            )
        )

        for contract in contracts:
            events = []
            if contract.end_date:
                days_until_end = (contract.end_date - today).days
                if 0 <= days_until_end <= 30 and days_until_end in {30, 14, 7, 3, 1, 0}:
                    events.append(('Expiration', contract.end_date, days_until_end))

            if contract.renewal_date:
                days_until_renewal = (contract.renewal_date - today).days
                if 0 <= days_until_renewal <= 45 and days_until_renewal in {45, 30, 14, 7, 3, 1, 0}:
                    events.append(('Renewal', contract.renewal_date, days_until_renewal))

            if not events:
                continue

            recipients = set()
            if contract.created_by_id:
                recipients.add(contract.created_by)
            if contract.matter and contract.matter.responsible_attorney_id:
                recipients.add(contract.matter.responsible_attorney)
            if contract.client and contract.client.responsible_attorney_id:
                recipients.add(contract.client.responsible_attorney)

            admins = (
                OrganizationMembership.objects
                .filter(
                    organization=contract.organization,
                    is_active=True,
                    role__in=[OrganizationMembership.Role.OWNER, OrganizationMembership.Role.ADMIN],
                )
                .select_related('user')
            )
            for membership in admins:
                recipients.add(membership.user)

            contract_link = reverse('contracts:contract_detail', kwargs={'pk': contract.id})

            for event_name, event_date, days_remaining in events:
                for recipient in recipients:
                    title = f'{event_name} reminder: {contract.title} ({days_remaining}d)'
                    exists = Notification.objects.filter(
                        recipient=recipient,
                        notification_type=Notification.NotificationType.DEADLINE,
                        title=title,
                        link=contract_link,
                        created_at__date=today,
                    ).exists()
                    if exists:
                        continue

                    Notification.objects.create(
                        recipient=recipient,
                        notification_type=Notification.NotificationType.DEADLINE,
                        title=title,
                        message=(
                            f'{contract.title} has an upcoming {event_name.lower()} date '
                            f'on {event_date.isoformat()} ({days_remaining} day(s) remaining).'
                        ),
                        link=contract_link,
                    )
                    created_count += 1

        self.stdout.write(self.style.SUCCESS(f'Created {created_count} reminder notification(s).'))
