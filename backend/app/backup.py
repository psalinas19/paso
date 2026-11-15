"""Backups of everything the server holds, and the way back (SPEC 10, phase 5).

One archive is one moment of the whole data directory: the database (copied
with SQLite's own backup API, so it is consistent even while the API is
answering), the images of the reviews and the server's copies of the
notebooks. Archives are plain .tar.gz files that open without this program.

    python -m app.backup create            # make one now (and upload it, if a remote is set)
    python -m app.backup list              # what exists here and on the remote
    python -m app.backup fetch [NAME]      # bring one back from the remote (the newest by default)
    python -m app.backup restore ARCHIVE   # put the server back to that moment

The daily run is `run_once`, called from the API process when BACKUP_ENABLED
is on. Uploading goes through rclone, so "somewhere that is not this server"
can be Cloudflare R2, a Nextcloud, Google Drive or another disk without a line
of code changing.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.config import Settings, get_settings

PREFIX = "paso-"
SUFFIX = ".tar.gz"
STAMP = "%Y%m%d-%H%M%S"
STATUS_FILE = "status.json"
#: What an archive holds besides the database, relative to the data directory.
FOLDERS = ("images", "notebooks")
MANIFEST = "manifest.json"
DATABASE = "paso.db"


class BackupError(RuntimeError):
    """Something a person has to look at. The message is in Spanish."""


def stamp_of(name: str) -> datetime | None:
    """When an archive was made, read from its name; None if it is not one of ours."""
    if not (name.startswith(PREFIX) and name.endswith(SUFFIX)):
        return None
    try:
        return datetime.strptime(name[len(PREFIX) : -len(SUFFIX)], STAMP).replace(tzinfo=UTC)
    except ValueError:
        return None


def _database_file(settings: Settings) -> Path:
    url = settings.resolved_database_url
    if not url.startswith("sqlite:///"):
        raise BackupError("El respaldo solo sabe copiar una base de datos SQLite.")
    return Path(url.removeprefix("sqlite:///"))


def create(settings: Settings, now: datetime | None = None) -> Path:
    """Write one archive of the data directory into the backup folder."""
    now = now or datetime.now(UTC)
    source = _database_file(settings)
    target_dir = settings.resolved_backup_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    archive = target_dir / f"{PREFIX}{now.strftime(STAMP)}{SUFFIX}"
    with tempfile.TemporaryDirectory(dir=target_dir) as work:
        copy = Path(work) / DATABASE
        if source.exists():
            # SQLite's backup API: a consistent copy even with the API writing.
            with (
                contextlib.closing(sqlite3.connect(source)) as live,
                contextlib.closing(sqlite3.connect(copy)) as out,
            ):
                live.backup(out)
        counts = {
            folder: sum(1 for f in (settings.data_dir / folder).rglob("*") if f.is_file())
            for folder in FOLDERS
            if (settings.data_dir / folder).is_dir()
        }
        manifest = Path(work) / MANIFEST
        manifest.write_text(
            json.dumps({"created_at": now.isoformat(), "files": counts, "format": 1}, indent=2),
            encoding="utf-8",
        )
        partial = archive.with_suffix(".partial")
        with tarfile.open(partial, "w:gz") as tar:
            tar.add(manifest, arcname=MANIFEST)
            if copy.exists():
                tar.add(copy, arcname=DATABASE)
            for folder in counts:
                tar.add(settings.data_dir / folder, arcname=folder)
        partial.replace(archive)  # a half-written archive never carries the real name
    return archive


def to_delete(names: list[str], now: datetime, days: int, weeks: int, months: int) -> list[str]:
    """Which archives the retention policy lets go.

    Kept: everything from the last `days` days; beyond that the newest of each
    week for `weeks` weeks; beyond that the newest of each month for `months`
    months. The newest archive is always kept, whatever its age. Names that are
    not archives of ours are never touched.
    """
    dated = sorted(((stamp_of(n), n) for n in names if stamp_of(n)), reverse=True)
    keep: set[str] = set()
    seen_weeks: set[tuple[int, int]] = set()
    seen_months: set[tuple[int, int]] = set()
    for index, (when, name) in enumerate(dated):
        age = now - when
        week, month = when.isocalendar()[:2], (when.year, when.month)
        # Each archive falls in exactly one tier, by its age.
        if index == 0 or age <= timedelta(days=days):
            wanted = True
        elif age <= timedelta(days=days + 7 * weeks):
            wanted = week not in seen_weeks
        elif age <= timedelta(days=days + 7 * weeks + 31 * months):
            wanted = month not in seen_months
        else:
            wanted = False
        if wanted:
            keep.add(name)
        # A kept archive speaks for its week and its month: no second one for them.
        if name in keep:
            seen_weeks.add(week)
            seen_months.add(month)
    return [name for _, name in dated if name not in keep]


def _rclone(*args: str) -> str:
    try:
        done = subprocess.run(["rclone", *args], capture_output=True, text=True, timeout=1800)
    except FileNotFoundError as exc:
        raise BackupError(
            "rclone no está instalado: no puedo usar el almacenamiento externo."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise BackupError("rclone tardó demasiado y lo detuve.") from exc
    if done.returncode != 0:
        raise BackupError(f"rclone falló: {done.stderr.strip()[-400:] or 'sin mensaje'}")
    return done.stdout


def remote_names(remote: str) -> list[str]:
    return [line.strip() for line in _rclone("lsf", remote).splitlines() if stamp_of(line.strip())]


def prune(settings: Settings, now: datetime | None = None) -> list[str]:
    """Apply the retention policy here and on the remote. Returns what was removed here."""
    now = now or datetime.now(UTC)
    policy = (settings.backup_keep_days, settings.backup_keep_weeks, settings.backup_keep_months)
    folder = settings.resolved_backup_dir
    local = [p.name for p in folder.glob(f"{PREFIX}*{SUFFIX}")] if folder.is_dir() else []
    gone = to_delete(local, now, *policy)
    for name in gone:
        (folder / name).unlink(missing_ok=True)
    if settings.backup_remote:
        # Decided from the remote's own listing, never by mirroring this disk:
        # a fresh server with an empty folder must not empty the remote.
        for name in to_delete(remote_names(settings.backup_remote), now, *policy):
            _rclone("deletefile", f"{settings.backup_remote.rstrip('/')}/{name}")
    return gone


def push(settings: Settings, archive: Path) -> None:
    _rclone("copy", str(archive), settings.backup_remote)
    if archive.name not in remote_names(settings.backup_remote):
        raise BackupError("Subí el respaldo pero no aparece en el almacenamiento externo.")


def fetch(settings: Settings, name: str | None = None) -> Path:
    """Bring an archive back from the remote (the newest when no name is given)."""
    if not settings.backup_remote:
        raise BackupError("No hay almacenamiento externo configurado (BACKUP_REMOTE).")
    names = sorted(remote_names(settings.backup_remote))
    if not names:
        raise BackupError("El almacenamiento externo no tiene ningún respaldo.")
    wanted = name or names[-1]
    if wanted not in names:
        raise BackupError(f"No existe el respaldo '{wanted}' en el almacenamiento externo.")
    folder = settings.resolved_backup_dir
    folder.mkdir(parents=True, exist_ok=True)
    _rclone("copy", f"{settings.backup_remote.rstrip('/')}/{wanted}", str(folder))
    return folder / wanted


def restore(settings: Settings, archive: Path, force: bool = False) -> Path | None:
    """Put the data directory back to what `archive` holds.

    Refuses to write over existing data unless `force`; with it, what was
    there is moved aside, never deleted. Returns where it was moved to.
    Stop the API first: it holds the database open.
    """
    if not archive.is_file():
        raise BackupError(f"No encuentro el respaldo {archive}.")
    data = settings.data_dir
    database = _database_file(settings)
    # Unpacked, and the old data set aside, inside the backup folder: in a
    # container that and the data directory are the only places we may write.
    scratch = settings.resolved_backup_dir
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as work:
        try:
            with tarfile.open(archive, "r:gz") as tar:
                # "data": no absolute paths, no "..", no links out, no devices.
                tar.extractall(work, filter="data")
        except (tarfile.TarError, OSError) as exc:
            raise BackupError(f"El respaldo está dañado o no es de Paso: {exc}") from exc
        unpacked = Path(work)
        if not (unpacked / MANIFEST).is_file():
            raise BackupError("El archivo no es un respaldo de Paso (no trae manifest.json).")
        if (unpacked / DATABASE).exists():
            with contextlib.closing(sqlite3.connect(unpacked / DATABASE)) as check:
                if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise BackupError("La base de datos del respaldo no pasó la comprobación.")

        occupied = database.exists() or any((data / f).is_dir() for f in FOLDERS)
        aside: Path | None = None
        if occupied:
            if not force:
                raise BackupError(
                    f"Ya hay datos en {data}. Usa --force para reemplazarlos: lo que hay "
                    "se aparta a una carpeta, no se borra."
                )
            aside = scratch / f"antes-de-restaurar-{datetime.now(UTC):{STAMP}}"
            aside.mkdir(parents=True)
            for item in [database, *(data / f for f in FOLDERS)]:
                if item.exists():
                    shutil.move(str(item), aside / item.name)
            # SQLite's side files belong to the database that just left.
            for side in (database.with_name(database.name + s) for s in ("-wal", "-shm")):
                side.unlink(missing_ok=True)
        data.mkdir(parents=True, exist_ok=True)
        database.parent.mkdir(parents=True, exist_ok=True)
        if (unpacked / DATABASE).exists():
            shutil.move(str(unpacked / DATABASE), database)
        for folder in FOLDERS:
            if (unpacked / folder).is_dir():
                shutil.move(str(unpacked / folder), data / folder)
    return aside


def read_status(settings: Settings) -> dict:
    """What the last daily run left behind: {"ok", "at", "archive", "remote", "detail"}."""
    try:
        return json.loads((settings.resolved_backup_dir / STATUS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def run_once(settings: Settings, now: datetime | None = None) -> dict:
    """One full backup: archive, upload, prune. Never raises: the outcome is the status."""
    now = now or datetime.now(UTC)
    status = {"ok": False, "at": now.isoformat(), "archive": "", "remote": False, "detail": ""}
    try:
        archive = create(settings, now)
        status["archive"] = archive.name
        if settings.backup_remote:
            push(settings, archive)
            status["remote"] = True
        prune(settings, now)
        status["ok"] = True
        if not settings.backup_remote:
            status["detail"] = "Sin almacenamiento externo: el respaldo está solo en este servidor."
    except (BackupError, OSError, sqlite3.Error) as exc:
        status["detail"] = str(exc)
    folder = settings.resolved_backup_dir
    folder.mkdir(parents=True, exist_ok=True)
    (folder / STATUS_FILE).write_text(json.dumps(status, indent=2), encoding="utf-8")
    return status


def due(settings: Settings, now: datetime | None = None) -> bool:
    """True when the last good backup is a day old or there is none."""
    now = now or datetime.now(UTC)
    status = read_status(settings)
    try:
        last = datetime.fromisoformat(status["at"])
    except (KeyError, ValueError, TypeError):
        return True
    # A failed run is tried again within the hour instead of waiting a whole day.
    return now - last >= (timedelta(hours=23) if status.get("ok") else timedelta(minutes=55))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.backup", description=__doc__.split("\n")[0]
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create", help="hace un respaldo ahora")
    commands.add_parser("list", help="lista los respaldos de aquí y del almacenamiento externo")
    fetching = commands.add_parser("fetch", help="trae un respaldo del almacenamiento externo")
    fetching.add_argument("name", nargs="?", help="nombre del respaldo; por omisión, el más nuevo")
    restoring = commands.add_parser("restore", help="deja el servidor como estaba en un respaldo")
    restoring.add_argument("archive", type=Path)
    restoring.add_argument("--force", action="store_true", help="reemplaza los datos que haya")
    args = parser.parse_args(argv)
    settings = get_settings()
    try:
        if args.command == "create":
            status = run_once(settings)
            print(
                ("Respaldo hecho: " if status["ok"] else "El respaldo FALLÓ: ") + status["archive"]
            )
            if status["detail"]:
                print(status["detail"])
            return 0 if status["ok"] else 1
        if args.command == "list":
            folder = settings.resolved_backup_dir
            here = (
                sorted(p.name for p in folder.glob(f"{PREFIX}*{SUFFIX}")) if folder.is_dir() else []
            )
            print(f"En este servidor ({folder}):", *(here or ["  (ninguno)"]), sep="\n  ")
            if settings.backup_remote:
                there = sorted(remote_names(settings.backup_remote))
                print(f"En {settings.backup_remote}:", *(there or ["  (ninguno)"]), sep="\n  ")
            else:
                print("No hay almacenamiento externo configurado (BACKUP_REMOTE).")
            return 0
        if args.command == "fetch":
            print(f"Traído: {fetch(settings, args.name)}")
            return 0
        aside = restore(settings, args.archive, args.force)
        print(f"Restaurado desde {args.archive.name}.")
        if aside:
            print(f"Lo que había quedó apartado en {aside}.")
        print("Arranca el API: al iniciar pone la base de datos al día.")
        return 0
    except BackupError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
