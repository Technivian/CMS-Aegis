import json
import os
import sqlite3
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


class Command(BaseCommand):
    help = 'Verify production Postgres cutover readiness and emit machine-readable evidence.'

    def handle(self, *args, **options):
        engine = connection.settings_dict.get('ENGINE', '')
        env = os.getenv('DJANGO_ENV', '').strip().lower()
        if env == 'production' and engine != 'django.db.backends.postgresql':
            raise CommandError('Production cutover check failed: default DB is not PostgreSQL.')

        started = time.perf_counter()
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        latency_ms = round((time.perf_counter() - started) * 1000, 2)

        if connection.vendor == 'postgresql':
            with connection.cursor() as cursor:
                cursor.execute('SELECT version()')
                version = cursor.fetchone()[0]
                cursor.execute('SELECT current_database()')
                database_name = cursor.fetchone()[0]
                cursor.execute('SELECT current_user')
                db_user = cursor.fetchone()[0]
        else:
            version = f"SQLite {sqlite3.sqlite_version}" if connection.vendor == 'sqlite' else connection.vendor
            database_name = connection.settings_dict.get('NAME') or 'unknown'
            db_user = connection.settings_dict.get('USER') or 'n/a'

        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes()
        unapplied = executor.migration_plan(targets)

        payload = {
            'captured_at': timezone.now().isoformat(),
            'environment': env or 'unknown',
            'database': {
                'engine': engine,
                'name': database_name,
                'user': db_user,
                'version': version,
                'connectivity_latency_ms': latency_ms,
            },
            'migrations': {
                'unapplied_count': len(unapplied),
                'status': 'clean' if not unapplied else 'pending',
            },
            'cutover_ready': bool(engine == 'django.db.backends.postgresql' and len(unapplied) == 0),
        }

        self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
        if not payload['cutover_ready']:
            raise CommandError('Postgres cutover is not ready. See output for details.')
