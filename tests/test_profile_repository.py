from pathlib import Path

from cv_generator.domain.models import MasterProfile
from cv_generator.infrastructure.persistence.sqlite_profile_repository import SQLiteProfileRepository


def test_sqlite_profile_repository_roundtrip(tmp_path: Path) -> None:
    repo = SQLiteProfileRepository(tmp_path / "master.db")
    profile = MasterProfile.empty("p1")
    profile.basics = {"name": "Test User"}
    repo.save(profile, event_type="test")

    loaded = repo.get("p1")
    assert loaded is not None
    assert loaded.basics["name"] == "Test User"

    exported = repo.export_json("p1", tmp_path / "master_profile.json")
    assert exported.exists()
