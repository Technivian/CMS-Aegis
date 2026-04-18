from __future__ import annotations

import hashlib
import hmac
import json
import tarfile
from dataclasses import dataclass
from pathlib import Path

from django.utils import timezone


@dataclass
class EvidenceBundleResult:
    bundle_path: Path
    manifest_path: Path
    sha256_path: Path
    signature_path: Path
    file_count: int


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _sign_hash(hash_hex: str, signing_key: str) -> str:
    return hmac.new(signing_key.encode('utf-8'), hash_hex.encode('utf-8'), hashlib.sha256).hexdigest()


def export_evidence_bundle(include_paths: list[str], output_dir: str, signing_key: str) -> EvidenceBundleResult:
    files: list[Path] = []
    for item in include_paths:
        path = Path(item).expanduser().resolve()
        if path.exists() and path.is_file():
            files.append(path)

    if not files:
        raise ValueError('No valid evidence files were provided.')

    out_dir = Path(output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = timezone.now().strftime('%Y%m%dT%H%M%SZ')
    base = f'compliance-evidence-{stamp}'
    manifest_path = out_dir / f'{base}.manifest.json'
    bundle_path = out_dir / f'{base}.tar.gz'
    sha256_path = out_dir / f'{base}.sha256'
    signature_path = out_dir / f'{base}.sig'

    manifest = {
        'generated_at': timezone.now().isoformat(),
        'files': [],
    }
    for index, path in enumerate(files):
        arcname = f'evidence/{index}_{path.name}'
        manifest['files'].append(
            {
                'original_path': str(path),
                'archive_path': arcname,
                'size': path.stat().st_size,
                'sha256': _sha256_file(path),
            }
        )
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding='utf-8')

    with tarfile.open(bundle_path, 'w:gz') as tar:
        tar.add(manifest_path, arcname='manifest.json')
        for entry in manifest['files']:
            tar.add(entry['original_path'], arcname=entry['archive_path'])

    bundle_hash = _sha256_file(bundle_path)
    sha256_path.write_text(f'{bundle_hash}  {bundle_path.name}\n', encoding='utf-8')
    signature_path.write_text(_sign_hash(bundle_hash, signing_key) + '\n', encoding='utf-8')
    return EvidenceBundleResult(
        bundle_path=bundle_path,
        manifest_path=manifest_path,
        sha256_path=sha256_path,
        signature_path=signature_path,
        file_count=len(files),
    )


def verify_evidence_bundle(bundle_path: str, sha256_path: str, signature_path: str, signing_key: str) -> dict:
    bundle = Path(bundle_path).expanduser().resolve()
    sha_file = Path(sha256_path).expanduser().resolve()
    sig_file = Path(signature_path).expanduser().resolve()

    if not bundle.exists():
        raise ValueError(f'Bundle not found: {bundle}')
    if not sha_file.exists():
        raise ValueError(f'SHA file not found: {sha_file}')
    if not sig_file.exists():
        raise ValueError(f'Signature file not found: {sig_file}')

    expected_hash = sha_file.read_text(encoding='utf-8').strip().split()[0]
    computed_hash = _sha256_file(bundle)
    if expected_hash != computed_hash:
        raise ValueError('Bundle SHA256 mismatch.')

    expected_sig = sig_file.read_text(encoding='utf-8').strip()
    computed_sig = _sign_hash(computed_hash, signing_key)
    if expected_sig != computed_sig:
        raise ValueError('Bundle signature mismatch.')

    with tarfile.open(bundle, 'r:gz') as tar:
        manifest_member = tar.extractfile('manifest.json')
        if manifest_member is None:
            raise ValueError('Manifest not found in bundle.')
        manifest = json.loads(manifest_member.read().decode('utf-8'))
        files = manifest.get('files') or []
        for entry in files:
            archive_path = str(entry.get('archive_path') or '')
            expected_file_hash = str(entry.get('sha256') or '')
            member = tar.extractfile(archive_path)
            if member is None:
                raise ValueError(f'Missing archive member: {archive_path}')
            payload = member.read()
            if _sha256_bytes(payload) != expected_file_hash:
                raise ValueError(f'Archive member hash mismatch: {archive_path}')

    return {
        'status': 'verified',
        'bundle_path': str(bundle),
        'sha256': computed_hash,
        'files_verified': len(files),
    }
