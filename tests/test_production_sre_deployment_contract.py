"""Historical SRE build remains traceable; new deployment delegates to one CLI."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_completed_sre_overlay_keeps_certified_base_and_four_owned_files():
    lines = (ROOT / 'infra/production/Dockerfile.sre-v2-overlay').read_text().splitlines()
    assert lines[0].endswith('@sha256:d57f44d3f1af85d6a6eddfcf29c8b99198a63cd5de58ae21408d7fae90594816')
    assert len([line for line in lines if line.startswith('COPY ')]) == 4


def test_old_entrypoint_delegates_to_canonical_release_cli():
    result = subprocess.run(['python3', str(ROOT / 'scripts/deploy-production-sre-v2.py'), '--help'], capture_output=True, text=True)
    assert result.returncode == 0
    assert 'certify-image' in result.stdout and 'verify' in result.stdout
