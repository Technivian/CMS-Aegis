import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]

auth_json = root / 'docs' / 'AUTH_ROUTE_PROFILE_2026-04-13.json'
load_json = root / 'docs' / 'LOAD_TEST_2X_2026-04-13.json'
auth_md = root / 'docs' / 'AUTH_ROUTE_PROFILE_2026-04-13.md'
load_md = root / 'docs' / 'LOAD_TEST_2X_2026-04-13.md'

if auth_json.exists():
    data = json.loads(auth_json.read_text())
    lines = ['# Authenticated Route Profile (2026-04-13)', '', f"Iterations per route: `{data['iterations_per_route']}`", '']
    lines.append('| Route | p50 (ms) | p95 (ms) | Max (ms) | Status Codes | Success Rate |')
    lines.append('|---|---:|---:|---:|---|---:|')
    for route, metrics in data['routes'].items():
        lines.append(
            f"| `{route}` | {metrics['p50_ms']} | {metrics['p95_ms']} | {metrics['max_ms']} | "
            f"{','.join(str(s) for s in metrics['status_codes'])} | {metrics['success_rate']} |"
        )
    auth_md.write_text('\n'.join(lines) + '\n')

if load_json.exists():
    data = json.loads(load_json.read_text())
    t = data['target']
    e = data['execution']
    l = data['latency_ms']
    lines = [
        '# 2x Peak Load Test Summary (2026-04-13)',
        '',
        f"Target: `{t['target_rps']}` rps (`peak_rps={t['peak_rps']}` x `multiplier={t['multiplier']}`)",
        f"Executed requests: `{e['executed_requests']}` in `{e['wall_time_seconds']}`s (achieved `{e['achieved_rps']}` rps)",
        '',
        '| Metric | Value |',
        '|---|---:|',
        f"| p50 latency (ms) | {l['p50']} |",
        f"| p95 latency (ms) | {l['p95']} |",
        f"| max latency (ms) | {l['max']} |",
        f"| success rate | {data['success_rate']} |",
        f"| status codes | {','.join(str(s) for s in data['status_codes'])} |",
    ]
    load_md.write_text('\n'.join(lines) + '\n')
