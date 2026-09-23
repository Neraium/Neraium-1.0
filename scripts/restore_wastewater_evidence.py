#!/usr/bin/env python3
"""Verify or restore losslessly archived validation evidence; never execute Neraium."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile


def file_sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, default=Path(__file__).resolve().parents[1] / 'docs/validation/wastewater-real-2026')
    parser.add_argument('--verify-only', action='store_true', help='Check archive contents without writing restored files')
    args = parser.parse_args()
    package = args.package.resolve()
    manifest = json.loads((package / 'ARCHIVE_MANIFEST.json').read_text())
    expected = manifest['members_sha256']
    seen = set()
    with tempfile.TemporaryFile() as joined:
        for part in manifest['parts']:
            path = package / part['path']
            if file_sha256(path) != part['sha256']:
                raise ValueError(f'Archive part hash mismatch: {path}')
            with path.open('rb') as stream:
                shutil.copyfileobj(stream, joined)
        joined.seek(0)
        with tarfile.open(fileobj=joined, mode='r|gz') as archive:
            for member in archive:
                relative = PurePosixPath(member.name)
                if (not member.isfile() or relative.is_absolute() or '..' in relative.parts
                        or not relative.parts or relative.parts[0] != 'raw'
                        or member.name not in expected or member.name in seen):
                    raise ValueError(f'Unexpected archive member: {member.name}')
                stream = archive.extractfile(member)
                if stream is None:
                    raise ValueError(f'Unreadable member: {member.name}')
                content = stream.read()
                if hashlib.sha256(content).hexdigest() != expected[member.name]:
                    raise ValueError(f'Member hash mismatch: {member.name}')
                seen.add(member.name)
                destination = package.joinpath(*relative.parts)
                if not destination.resolve().is_relative_to(package):
                    raise ValueError(f'Unsafe destination: {destination}')
                if destination.exists():
                    if file_sha256(destination) != expected[member.name]:
                        raise ValueError(f'Refusing to overwrite differing evidence: {destination}')
                elif not args.verify_only:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with destination.open('xb') as output:
                        output.write(content)
        if seen != set(expected):
            raise ValueError('Archive member coverage mismatch')
    print(f'Verified {len(seen)} original raw artifacts; ' + ('no files restored.' if args.verify_only else 'missing artifacts restored without overwrites.'))


if __name__ == '__main__':
    main()
