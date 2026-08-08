from hashlib import sha256
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]
MANIFEST_PATH = PROJECT_ROOT / "docs/baselines/phase0-production-source.sha256"


def test_production_sources_match_verified_upstream_manifest():
    expected = {}
    for line in MANIFEST_PATH.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        digest, relative_path = line.split(maxsplit=1)
        expected[relative_path] = digest

    production_paths = {"acoustic_analysis.py"}
    production_paths.update(
        str(path.relative_to(PROJECT_ROOT))
        for path in (PROJECT_ROOT / "src").rglob("*.py")
    )
    assert set(expected) == production_paths

    actual = {
        relative_path: sha256((PROJECT_ROOT / relative_path).read_bytes()).hexdigest()
        for relative_path in sorted(production_paths)
    }
    assert actual == expected
