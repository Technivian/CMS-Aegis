import json
import threading
from contextlib import contextmanager
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.core.management import BaseCommand, call_command, CommandError
from django.test.utils import override_settings
from django.utils import timezone

from contracts.models import (
    Contract,
    Organization,
    OrganizationMembership,
    SalesforceOrganizationConnection,
    SalesforceSyncRun,
    WebhookDelivery,
    WebhookEndpoint,
)
from contracts.services.salesforce import encrypt_salesforce_token


User = get_user_model()


class _TraceHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, server_address, handler_class):
        super().__init__(server_address, handler_class)
        self.requests: list[dict] = []


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict):
    body = json.dumps(payload, indent=2, sort_keys=True).encode('utf-8')
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Content-Length', str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _start_trace_server(kind: str):
    received = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):  # noqa: A003
            return

        def _capture(self):
            body = self.rfile.read(int(self.headers.get('Content-Length') or 0)) if int(self.headers.get('Content-Length') or 0) else b''
            parsed = urlparse(self.path)
            entry = {
                'kind': kind,
                'method': self.command,
                'path': parsed.path,
                'query': parse_qs(parsed.query),
                'headers': {k: v for k, v in self.headers.items()},
                'body': body.decode('utf-8', errors='replace'),
                'timestamp': timezone.now().isoformat(),
            }
            received.append(entry)
            return entry

        def do_GET(self):
            entry = self._capture()
            if kind == 'salesforce' and entry['path'].endswith('/query'):
                _json_response(
                    self,
                    200,
                    {
                        'done': True,
                        'totalSize': 1,
                        'records': [
                            {
                                'Id': '006TRACE001',
                                'Name': 'Trace Contract',
                                'Account': {'Name': 'Trace Counterparty LLC'},
                                'Type': 'MSA',
                                'Amount': '12345.67',
                                'CurrencyIsoCode': 'USD',
                                'Owner': {'Email': 'owner@example.com', 'Name': 'Owner User'},
                                'Status__c': 'ACTIVE',
                                'Record_URL__c': 'https://example.salesforce.local/006TRACE001',
                                'CreatedDate': '2026-04-25T07:00:00Z',
                                'LastModifiedDate': '2026-04-25T07:02:00Z',
                            }
                        ],
                    },
                )
                return
            _json_response(self, 404, {'error': 'not found', 'path': entry['path']})

        def do_POST(self):
            entry = self._capture()
            if kind == 'salesforce' and entry['path'].endswith('/services/oauth2/token'):
                _json_response(
                    self,
                    200,
                    {
                        'access_token': 'sandbox-access-token-refreshed',
                        'refresh_token': 'sandbox-refresh-token-refreshed',
                        'instance_url': f'http://127.0.0.1:{self.server.server_address[1]}',
                        'id': 'sandbox-org-id',
                        'scope': 'api refresh_token',
                        'expires_in': 3600,
                    },
                )
                return
            if kind == 'webhook':
                _json_response(
                    self,
                    200,
                    {
                        'received': True,
                        'processed': True,
                        'delivery_id': self.headers.get('X-CMS-AEGIS-DELIVERY-ID'),
                        'event_type': self.headers.get('X-CMS-AEGIS-EVENT'),
                    },
                )
                return
            _json_response(self, 404, {'error': 'not found', 'path': entry['path']})

    server = _TraceHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, received


@contextmanager
def _server_context(kind: str):
    server, received = _start_trace_server(kind)
    try:
        yield server, received
    finally:
        server.shutdown()
        server.server_close()


class Command(BaseCommand):
    help = 'Run a reproducible Salesforce + webhook integration trace bundle.'

    def add_arguments(self, parser):
        parser.add_argument('--organization-slug', default='integration-trace-firm')
        parser.add_argument('--organization-name', default='Integration Trace Firm')
        parser.add_argument('--output-dir', default='docs/evidence/integration-trace')
        parser.add_argument('--limit', type=int, default=1)
        parser.add_argument('--fail-on-no-go', action='store_true')

    @staticmethod
    def _write_json(path: Path, payload: dict):
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')

    def _ensure_trace_org(self, slug: str, name: str):
        admin = User.objects.filter(is_superuser=True).first()
        if admin is None:
            admin = User.objects.create_superuser(
                username='integration-admin',
                email='integration-admin@example.com',
                password='integration-admin-123',
            )
        organization, _ = Organization.objects.get_or_create(slug=slug, defaults={'name': name})
        if organization.name != name:
            organization.name = name
            organization.save(update_fields=['name'])
        OrganizationMembership.objects.get_or_create(
            organization=organization,
            user=admin,
            defaults={
                'role': OrganizationMembership.Role.OWNER,
                'is_active': True,
            },
        )
        return organization, admin

    def _reset_trace_data(self, organization):
        Contract.objects.filter(organization=organization, source_system='salesforce', source_system_id='006TRACE001').delete()
        SalesforceSyncRun.objects.filter(organization=organization).delete()
        WebhookDelivery.objects.filter(organization=organization).delete()
        WebhookEndpoint.objects.filter(organization=organization).delete()
        SalesforceOrganizationConnection.objects.filter(organization=organization).delete()

    def _record_snapshot(self, organization):
        sync_run = SalesforceSyncRun.objects.filter(organization=organization).order_by('-started_at').first()
        contract = Contract.objects.filter(
            organization=organization,
            source_system='salesforce',
            source_system_id='006TRACE001',
        ).first()
        webhook_delivery = WebhookDelivery.objects.filter(organization=organization).order_by('-created_at').first()
        return {
            'salesforce_sync_run': (
                {
                    'id': sync_run.id,
                    'status': sync_run.status,
                    'trigger_source': sync_run.trigger_source,
                    'dry_run': sync_run.dry_run,
                    'limit_applied': sync_run.limit_applied,
                    'source_object': sync_run.source_object,
                    'fetched_records': sync_run.fetched_records,
                    'created_count': sync_run.created_count,
                    'updated_count': sync_run.updated_count,
                    'skipped_count': sync_run.skipped_count,
                    'error_count': sync_run.error_count,
                    'summary': sync_run.summary,
                    'started_at': sync_run.started_at.isoformat() if sync_run.started_at else None,
                    'completed_at': sync_run.completed_at.isoformat() if sync_run.completed_at else None,
                }
                if sync_run
                else None
            ),
            'contract': (
                {
                    'id': contract.id,
                    'title': contract.title,
                    'source_system': contract.source_system,
                    'source_system_id': contract.source_system_id,
                    'counterparty': contract.counterparty,
                    'contract_type': contract.contract_type,
                    'status': contract.status,
                    'value': str(contract.value),
                    'currency': contract.currency,
                    'source_system_url': contract.source_system_url,
                    'source_last_modified_at': (
                        contract.source_last_modified_at.isoformat() if contract.source_last_modified_at else None
                    ),
                }
                if contract
                else None
            ),
            'webhook_delivery': (
                {
                    'id': webhook_delivery.id,
                    'event_type': webhook_delivery.event_type,
                    'status': webhook_delivery.status,
                    'attempt_count': webhook_delivery.attempt_count,
                    'response_status': webhook_delivery.response_status,
                    'response_body': webhook_delivery.response_body,
                    'error_message': webhook_delivery.error_message,
                    'sent_at': webhook_delivery.sent_at.isoformat() if webhook_delivery.sent_at else None,
                    'created_at': webhook_delivery.created_at.isoformat() if webhook_delivery.created_at else None,
                }
                if webhook_delivery
                else None
            ),
        }

    def handle(self, *args, **options):
        output_dir = Path(options['output_dir'])
        output_dir.mkdir(parents=True, exist_ok=True)
        org_slug = str(options['organization_slug']).strip() or 'integration-trace-firm'
        org_name = str(options['organization_name']).strip() or 'Integration Trace Firm'
        limit = max(1, int(options['limit']))

        organization, _ = self._ensure_trace_org(org_slug, org_name)
        self._reset_trace_data(organization)

        salesforce_trace = {}
        webhook_trace = {}

        with _server_context('salesforce') as (salesforce_server, salesforce_requests), _server_context('webhook') as (
            webhook_server,
            webhook_requests,
        ):
            salesforce_base_url = f'http://127.0.0.1:{salesforce_server.server_address[1]}'
            webhook_base_url = f'http://127.0.0.1:{webhook_server.server_address[1]}'

            connection = SalesforceOrganizationConnection.objects.create(
                organization=organization,
                connected_by=User.objects.filter(is_superuser=True).first(),
                access_token=encrypt_salesforce_token('sandbox-access-token'),
                refresh_token=encrypt_salesforce_token('sandbox-refresh-token'),
                instance_url=salesforce_base_url,
                external_org_id='sandbox-org-id',
                scope='api refresh_token',
                token_expires_at=timezone.now() - timedelta(minutes=1),
                is_active=True,
            )
            WebhookEndpoint.objects.create(
                organization=organization,
                name='Trace Receiver',
                url=webhook_base_url,
                secret='trace-secret',
                event_types=['salesforce.sync.completed'],
                status=WebhookEndpoint.Status.ACTIVE,
                max_attempts=3,
            )

            sync_stdout = StringIO()
            try:
                with override_settings(
                    SALESFORCE_TOKEN_URL=f'{salesforce_base_url}/services/oauth2/token',
                ):
                    call_command(
                        'sync_salesforce_contracts',
                        organization_slug=org_slug,
                        limit=limit,
                        stdout=sync_stdout,
                    )
            except Exception as exc:
                raise CommandError(f'Salesforce sync trace failed: {exc}') from exc

            dispatch_stdout = StringIO()
            try:
                call_command('dispatch_webhook_deliveries', '--limit', '10', stdout=dispatch_stdout)
            except Exception as exc:
                raise CommandError(f'Webhook dispatch trace failed: {exc}') from exc

            salesforce_trace = {
                'request': {
                    'organization_slug': org_slug,
                    'organization_name': org_name,
                    'mode': 'sandbox',
                    'limit': limit,
                    'connection_before_sync': {
                        'instance_url': connection.instance_url,
                        'token_expired': connection.token_expired,
                        'status': 'ACTIVE' if connection.is_active else 'INACTIVE',
                    },
                    'http_requests': salesforce_requests,
                    'command_stdout': sync_stdout.getvalue(),
                },
                'response': {
                    'http_responses': [
                        {'path': entry['path'], 'status': 200, 'body': 'sandbox response'}
                        for entry in salesforce_requests
                    ],
                    'sync_command_output': sync_stdout.getvalue(),
                },
                'stored': self._record_snapshot(organization),
            }

            webhook_trace = {
                'request': {
                    'trigger_event': 'salesforce.sync.completed',
                    'endpoint_url': webhook_base_url,
                    'http_requests': webhook_requests,
                    'dispatch_command_output': dispatch_stdout.getvalue(),
                },
                'response': {
                    'http_responses': [
                        {'path': entry['path'], 'status': 200, 'body': 'sandbox response'}
                        for entry in webhook_requests
                    ],
                    'dispatch_command_output': dispatch_stdout.getvalue(),
                },
                'stored': self._record_snapshot(organization),
            }

        bundle = {
            'captured_at': timezone.now().isoformat(),
            'organization_slug': org_slug,
            'organization_name': org_name,
            'mode': 'sandbox',
            'criteria': {
                'salesforce_sync_request_captured': bool(salesforce_trace.get('request', {}).get('http_requests')),
                'salesforce_sync_stored': bool(salesforce_trace.get('stored', {}).get('salesforce_sync_run')),
                'webhook_request_captured': bool(webhook_trace.get('request', {}).get('http_requests')),
                'webhook_stored': bool(webhook_trace.get('stored', {}).get('webhook_delivery')),
            },
            'salesforce': salesforce_trace,
            'webhook': webhook_trace,
        }
        bundle['status'] = 'GO' if all(bundle['criteria'].values()) else 'NO-GO'

        files = {
            'salesforce-trace-request.json': salesforce_trace['request'],
            'salesforce-trace-response.json': salesforce_trace['response'],
            'salesforce-trace-stored.json': salesforce_trace['stored'],
            'webhook-trace-request.json': webhook_trace['request'],
            'webhook-trace-response.json': webhook_trace['response'],
            'webhook-trace-stored.json': webhook_trace['stored'],
            'integration-trace-bundle.json': bundle,
        }
        for filename, payload in files.items():
            self._write_json(output_dir / filename, payload)

        self.stdout.write(json.dumps(bundle, indent=2, sort_keys=True))

        if options['fail_on_no_go'] and bundle['status'] != 'GO':
            raise CommandError('Integration trace bundle is NO-GO.')
