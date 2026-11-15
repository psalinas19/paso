"""Backups (phase 5): an archive must bring the server back, and old ones must go by the rules."""

from __future__ import annotations

import json
import shutil
import sqlite3
import tarfile
from datetime import UTC, datetime, timedelta

import pytest

from app import backup
from app.config import Settings

NOW = datetime(2026, 11, 15, 9, 0, tzinfo=UTC)


@pytest.fixture
def settings(tmp_path):
    return Settings(anthropic_api_key="x", app_token="t", data_dir=tmp_path / "data")


def fill(settings, reviews=("r1", "r2")):
    data = settings.data_dir
    (data / "images").mkdir(parents=True, exist_ok=True)
    (data / "notebooks").mkdir(exist_ok=True)
    (data / "images" / "r1.png").write_bytes(b"png-bytes")
    (data / "notebooks" / "n1.paso.json").write_text('{"format":"paso-notebook"}', encoding="utf-8")
    with sqlite3.connect(data / "paso.db") as db:
        db.execute("CREATE TABLE IF NOT EXISTS review (id TEXT)")
        db.executemany("INSERT INTO review VALUES (?)", [(r,) for r in reviews])


def reviews_in(settings) -> list[str]:
    with sqlite3.connect(settings.data_dir / "paso.db") as db:
        return [row[0] for row in db.execute("SELECT id FROM review ORDER BY id")]


def test_the_server_can_be_deleted_and_brought_back_from_an_archive(settings):
    fill(settings)
    # The API is mid-write while the backup runs: the copy must still be whole.
    writer = sqlite3.connect(settings.data_dir / "paso.db")
    writer.execute("INSERT INTO review VALUES ('uncommitted')")

    archive = backup.create(settings, NOW)

    writer.rollback()
    writer.close()
    assert archive.name == "paso-20261115-090000.tar.gz"
    with tarfile.open(archive) as tar:
        names = tar.getnames()
    assert {"manifest.json", "paso.db", "images/r1.png", "notebooks/n1.paso.json"} <= set(names)
    assert not list(archive.parent.glob("*.partial"))

    shutil.rmtree(settings.data_dir)  # the server is gone

    assert backup.restore(settings, archive) is None
    assert reviews_in(settings) == ["r1", "r2"]
    assert (settings.data_dir / "images" / "r1.png").read_bytes() == b"png-bytes"
    assert "paso-notebook" in (settings.data_dir / "notebooks" / "n1.paso.json").read_text()


def test_restoring_over_live_data_needs_force_and_sets_it_aside(settings):
    fill(settings)
    archive = backup.create(settings, NOW)
    fill(settings, reviews=("r3",))  # work done after the backup

    with pytest.raises(backup.BackupError, match="--force"):
        backup.restore(settings, archive)
    assert reviews_in(settings) == ["r1", "r2", "r3"]

    aside = backup.restore(settings, archive, force=True)

    assert reviews_in(settings) == ["r1", "r2"]
    # Nothing was deleted: the newer state is one folder away.
    with sqlite3.connect(aside / "paso.db") as db:
        assert db.execute("SELECT count(*) FROM review").fetchone()[0] == 3
    assert (aside / "images" / "r1.png").exists()


def test_a_file_that_is_not_a_backup_is_refused_before_touching_anything(settings, tmp_path):
    fill(settings)
    junk = tmp_path / "paso-20261115-090000.tar.gz"
    junk.write_bytes(b"not a tarball")
    with pytest.raises(backup.BackupError, match="dañado"):
        backup.restore(settings, junk, force=True)

    foreign = tmp_path / "other.tar.gz"
    (tmp_path / "x.txt").write_text("hola")
    with tarfile.open(foreign, "w:gz") as tar:
        tar.add(tmp_path / "x.txt", arcname="x.txt")
    with pytest.raises(backup.BackupError, match="manifest"):
        backup.restore(settings, foreign, force=True)

    # A path that climbs out of the archive never lands outside the data directory.
    evil = tmp_path / "evil.tar.gz"
    with tarfile.open(evil, "w:gz") as tar:
        tar.add(tmp_path / "x.txt", arcname="../../escaped.txt")
    with pytest.raises(backup.BackupError):
        backup.restore(settings, evil, force=True)
    assert not (tmp_path.parent / "escaped.txt").exists()
    with pytest.raises(backup.BackupError, match="No encuentro"):
        backup.restore(settings, tmp_path / "missing.tar.gz")
    assert reviews_in(settings) == ["r1", "r2"]


def name(days_ago: float) -> str:
    return f"paso-{(NOW - timedelta(days=days_ago)).strftime(backup.STAMP)}.tar.gz"


def test_old_archives_thin_out_to_one_a_week_then_one_a_month():
    names = [name(d) for d in range(0, 200)] + ["notes.txt", "paso-garbage.tar.gz"]

    gone = set(backup.to_delete(names, NOW, days=14, weeks=8, months=12))
    kept = sorted((n for n in names if n not in gone and backup.stamp_of(n)), reverse=True)

    # Every day of the last two weeks, untouched.
    assert kept[:15] == [name(d) for d in range(0, 15)]
    ages = [(NOW - backup.stamp_of(n)).days for n in kept[15:]]
    weekly = [a for a in ages if a <= 14 + 56]
    monthly = [a for a in ages if a > 14 + 56]
    assert 7 <= len(weekly) <= 9 and all(
        b - a >= 5 for a, b in zip(weekly, weekly[1:], strict=False)
    )
    assert 3 <= len(monthly) <= 5 and all(
        b - a >= 20 for a, b in zip(monthly, monthly[1:], strict=False)
    )
    # Files that are not ours are never proposed for deletion.
    assert "notes.txt" not in gone and "paso-garbage.tar.gz" not in gone


def test_the_newest_archive_is_never_deleted_however_old():
    assert backup.to_delete([name(900), name(1000)], NOW, days=14, weeks=8, months=12) == [
        name(1000)
    ]
    assert backup.to_delete([], NOW, 14, 8, 12) == []


def test_a_daily_run_archives_prunes_and_reports(settings):
    fill(settings)
    folder = settings.resolved_backup_dir
    folder.mkdir(parents=True)
    old = folder / name(400)
    old.write_bytes(b"old")
    (folder / name(401)).write_bytes(b"older")

    assert backup.due(settings, NOW) is True
    status = backup.run_once(settings, NOW)

    assert status["ok"] is True and status["archive"] == name(0)
    # No remote: it worked, and it says the copy is only on this disk.
    assert status["remote"] is False and "solo en este servidor" in status["detail"]
    assert backup.read_status(settings) == json.loads((folder / "status.json").read_text())
    assert not (folder / name(401)).exists()
    assert backup.due(settings, NOW + timedelta(hours=2)) is False
    assert backup.due(settings, NOW + timedelta(hours=23)) is True


def test_a_failed_run_says_so_and_is_tried_again_soon(settings, monkeypatch):
    fill(settings)
    monkeypatch.setattr(backup, "create", lambda *a: (_ for _ in ()).throw(OSError("disco lleno")))

    status = backup.run_once(settings, NOW)

    assert status["ok"] is False and "disco lleno" in status["detail"]
    assert backup.due(settings, NOW + timedelta(minutes=30)) is False
    assert backup.due(settings, NOW + timedelta(hours=1)) is True


def test_the_remote_is_pruned_from_its_own_listing_and_a_bad_upload_is_caught(
    settings, monkeypatch
):
    fill(settings)
    remote = Settings(
        anthropic_api_key="x", app_token="t", data_dir=settings.data_dir, backup_remote="r2:paso"
    )
    there = [name(1), name(300), name(301)]
    calls: list[tuple] = []

    def fake(*args):
        calls.append(args)
        if args[0] == "lsf":
            return "\n".join(there) + "\n"
        if args[0] == "copy":
            there.append(name(0))
        if args[0] == "deletefile":
            there.remove(args[1].rsplit("/", 1)[1])
        return ""

    monkeypatch.setattr(backup, "_rclone", fake)
    status = backup.run_once(remote, NOW)

    assert status == {**status, "ok": True, "remote": True, "detail": ""}
    assert ("deletefile", f"r2:paso/{name(301)}") in calls
    # This server's folder holds one archive; the remote kept its own history.
    assert sorted(there) == sorted([name(0), name(1), name(300)])

    # An upload that does not show up afterwards is a failure, not a success.
    monkeypatch.setattr(backup, "_rclone", lambda *a: "")
    failed = backup.run_once(remote, NOW + timedelta(days=1))
    assert failed["ok"] is False and "no aparece" in failed["detail"]


def test_the_command_line_reports_in_spanish_and_with_an_exit_code(settings, monkeypatch, capsys):
    fill(settings)
    monkeypatch.setattr(backup, "get_settings", lambda: settings)

    assert backup.main(["create"]) == 0
    made = capsys.readouterr().out
    assert "Respaldo hecho: paso-" in made
    assert backup.main(["list"]) == 0
    assert "paso-" in capsys.readouterr().out
    archive = next(settings.resolved_backup_dir.glob("paso-*.tar.gz"))
    assert backup.main(["restore", str(archive)]) == 1
    assert "--force" in capsys.readouterr().err
    assert backup.main(["restore", str(archive), "--force"]) == 0
    assert "apartado en" in capsys.readouterr().out
    assert backup.main(["fetch"]) == 1
    assert "BACKUP_REMOTE" in capsys.readouterr().err
