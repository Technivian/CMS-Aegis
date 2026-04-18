from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from contracts.models import ApprovalRequest, Contract, Notification, OrganizationMembership, SignatureRequest
from contracts.observability import record_scheduler_heartbeat


class Command(BaseCommand):
    help = 'Send renewal and expiration reminder notifications for contracts.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--scheduler-interval-minutes',
            type=int,
            default=None,
            help='Expected scheduler interval in minutes for heartbeat staleness evaluation.',
        )

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

        created_count += self._process_overdue_approval_requests(today)
        created_count += self._process_stale_signature_requests(today)

        record_scheduler_heartbeat(
            created_count=created_count,
            interval_minutes=options.get('scheduler_interval_minutes'),
        )
        self.stdout.write(self.style.SUCCESS(f'Created {created_count} reminder notification(s).'))

    @staticmethod
    def _organization_admin_recipients(organization):
        if not organization:
            return []
        return list(
            OrganizationMembership.objects.filter(
                organization=organization,
                is_active=True,
                role__in=[OrganizationMembership.Role.OWNER, OrganizationMembership.Role.ADMIN],
            ).select_related('user')
        )

    def _notification_exists(self, recipient, notification_type, title, link, today):
        return Notification.objects.filter(
            recipient=recipient,
            notification_type=notification_type,
            title=title,
            link=link,
            created_at__date=today,
        ).exists()

    def _process_overdue_approval_requests(self, today):
        created_count = 0
        now = timezone.now()
        approval_requests = ApprovalRequest.objects.select_related('contract', 'organization', 'assigned_to', 'delegated_to', 'contract__created_by').filter(
            status=ApprovalRequest.Status.PENDING,
            due_date__isnull=False,
            due_date__lt=now,
        )

        for request in approval_requests:
            escalation_after_hours = int(getattr(request.rule, 'escalation_after_hours', 0) or 0)
            escalation_time = request.due_date + timedelta(hours=max(0, escalation_after_hours))
            if now < escalation_time:
                continue
            recipients = set()
            if request.assigned_to_id:
                recipients.add(request.assigned_to)
            if getattr(request, 'delegated_to_id', None):
                recipients.add(request.delegated_to)
            if request.contract and request.contract.created_by_id:
                recipients.add(request.contract.created_by)
            for membership in self._organization_admin_recipients(request.organization):
                recipients.add(membership.user)

            link = reverse('contracts:contract_detail', kwargs={'pk': request.contract_id})
            title = f'Approval overdue: {request.contract.title} ({request.approval_step})'
            for recipient in recipients:
                if self._notification_exists(recipient, Notification.NotificationType.APPROVAL, title, link, today):
                    continue
                Notification.objects.create(
                    recipient=recipient,
                    notification_type=Notification.NotificationType.APPROVAL,
                    title=title,
                    message=(
                        f'{request.contract.title} has an overdue approval step "{request.approval_step}". '
                        f'It was due on {request.due_date.isoformat()}.'
                    ),
                    link=link,
                )
                created_count += 1

            request.status = ApprovalRequest.Status.ESCALATED
            update_fields = ['status']
            if getattr(request, 'escalated_at', None) is None:
                request.escalated_at = now
                update_fields.append('escalated_at')
            request.save(update_fields=update_fields)

        return created_count

    def _process_stale_signature_requests(self, today):
        created_count = 0
        threshold_days = int(getattr(self, 'signature_escalation_days', 7))
        stale_before = timezone.now() - timedelta(days=threshold_days)
        signature_requests = SignatureRequest.objects.select_related('contract', 'organization', 'created_by').filter(
            status__in=[SignatureRequest.Status.PENDING, SignatureRequest.Status.SENT, SignatureRequest.Status.VIEWED],
            sent_at__isnull=False,
            sent_at__lt=stale_before,
        )

        for request in signature_requests:
            recipients = set()
            if request.created_by_id:
                recipients.add(request.created_by)
            for membership in self._organization_admin_recipients(request.organization):
                recipients.add(membership.user)

            link = reverse('contracts:contract_detail', kwargs={'pk': request.contract_id})
            title = f'Signature overdue: {request.contract.title} ({request.signer_name})'
            for recipient in recipients:
                if self._notification_exists(recipient, Notification.NotificationType.APPROVAL, title, link, today):
                    continue
                Notification.objects.create(
                    recipient=recipient,
                    notification_type=Notification.NotificationType.APPROVAL,
                    title=title,
                    message=(
                        f'{request.contract.title} is waiting on signature from {request.signer_name}. '
                        f'The request was sent on {request.sent_at.date().isoformat()}.'
                    ),
                    link=link,
                )
                created_count += 1

            request.status = SignatureRequest.Status.EXPIRED
            request.save(update_fields=['status'])

        return created_count
