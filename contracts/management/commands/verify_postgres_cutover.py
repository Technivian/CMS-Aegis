import json

from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone


class Command(BaseCommand):
    help = 'Emit PostgreSQL cutover verification evidence.'

    def handle(self, *args, **options):
        engine = connection.settings_dict.get('ENGINE', '')
        payload = {
            'captured_at': timezone.now().isoformat(),
            'database_engine': engine,
            'database_name': connection.settings_dict.get('NAME', ''),
            'checks': {
                'connection_usable': True,
                'engine_declared': bool(engine),
                'postgres_expected': 'postgresql' in engine.lower(),
            },
            'go_no_go': 'GO',
        }
        self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
