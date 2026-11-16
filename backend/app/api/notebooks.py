"""The server's copy of the notebooks (SPEC 5, 7: `/api/backup`).

The iPad writes; the server keeps. Each notebook is stored as the same
`.paso.json` the app exports, so a copy can be opened by hand, imported into
another install, or read by a future app. Upload only, no merging: there is
one device (SPEC 3), and the last upload is the notebook.

Two safeguards against a bad upload replacing a good copy: the previous
version is kept beside the new one, and the daily backup of the whole data
directory (app/backup.py) keeps older ones.
"""

# No "from __future__ import annotations": FastAPI resolves the endpoint
# annotations at runtime, and `Db` below is local to create_app().

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import select

from app.db import NotebookBackup

#: A whole semester of dense notes is a few MB; this is room to spare.
MAX_NOTEBOOK_BYTES = 64 * 1024 * 1024
MAX_NAME_CHARS = 120
#: Ids are minted by the app with crypto.randomUUID(). Anything else never
#: reaches a file name.
NOTEBOOK_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class BackupOut(BaseModel):
    id: str
    title: str
    subject_name: str
    semester_name: str
    pages: int
    strokes: int
    size_bytes: int
    updated_at: datetime


class BackupList(BaseModel):
    notebooks: list[BackupOut]


def describe(row: NotebookBackup) -> BackupOut:
    updated = row.updated_at
    return BackupOut(
        id=row.id,
        title=row.title,
        subject_name=row.subject_name,
        semester_name=row.semester_name,
        pages=row.pages,
        strokes=row.strokes,
        size_bytes=row.size_bytes,
        updated_at=updated if updated.tzinfo else updated.replace(tzinfo=UTC),
    )


def _name(value: Any) -> str:
    return str(value).strip()[:MAX_NAME_CHARS] if isinstance(value, str) else ""


def add_notebook_routes(app: FastAPI, Db, auth: list, folder: Path) -> None:
    """Register the notebook backups. They live as files under `folder`."""
    folder.mkdir(parents=True, exist_ok=True)

    def path_of(notebook_id: str) -> Path:
        if not NOTEBOOK_ID.fullmatch(notebook_id):
            raise HTTPException(404, "Ese cuaderno no existe en el servidor.")
        return folder / f"{notebook_id}.paso.json"

    @app.get("/api/notebooks", dependencies=auth)
    def list_notebooks(db: Db) -> BackupList:
        rows = db.exec(select(NotebookBackup).order_by(NotebookBackup.updated_at.desc())).all()
        return BackupList(notebooks=[describe(row) for row in rows])

    @app.put("/api/notebooks/{notebook_id}", dependencies=auth)
    def put_notebook(
        db: Db,
        notebook_id: str,
        export: Annotated[dict[str, Any], Body()],
        semester: str = "",
    ) -> BackupOut:
        """Keep this version of a notebook. `export` is the app's `.paso.json`."""
        path = path_of(notebook_id)
        pages = export.get("pages")
        notebook = export.get("notebook")
        if export.get("format") != "paso-notebook" or not isinstance(pages, list):
            raise HTTPException(422, "Eso no es un respaldo de cuaderno de Write.")
        if not isinstance(notebook, dict) or notebook.get("id") != notebook_id:
            raise HTTPException(422, "El respaldo es de otro cuaderno.")
        if not all(isinstance(p, dict) and isinstance(p.get("strokes"), list) for p in pages):
            raise HTTPException(422, "El respaldo trae una página que no se puede leer.")
        data = json.dumps(export, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(data) > MAX_NOTEBOOK_BYTES:
            raise HTTPException(413, "El cuaderno es demasiado grande para respaldarlo de una vez.")

        # Written beside the old copy and swapped in, so a cut connection or a
        # full disk can never leave half a notebook where a whole one was.
        fresh = path.with_suffix(".tmp")
        fresh.write_bytes(data)
        if path.exists():
            os.replace(path, path.with_suffix(".prev"))
        os.replace(fresh, path)

        subject = export.get("subject")
        row = db.get(NotebookBackup, notebook_id) or NotebookBackup(id=notebook_id, title="")
        row.title = _name(notebook.get("title")) or "Cuaderno"
        row.subject_name = _name(subject.get("name")) if isinstance(subject, dict) else ""
        row.semester_name = _name(semester)
        row.pages = len(pages)
        row.strokes = sum(len(p["strokes"]) for p in pages)
        row.size_bytes = len(data)
        row.updated_at = datetime.now(UTC)
        db.add(row)
        db.commit()
        db.refresh(row)
        return describe(row)

    @app.get("/api/notebooks/{notebook_id}", dependencies=auth)
    def get_notebook(db: Db, notebook_id: str) -> FileResponse:
        path = path_of(notebook_id)
        if db.get(NotebookBackup, notebook_id) is None or not path.is_file():
            raise HTTPException(404, "Ese cuaderno no existe en el servidor.")
        return FileResponse(path, media_type="application/json")

    @app.delete("/api/notebooks/{notebook_id}", dependencies=auth)
    def delete_notebook(db: Db, notebook_id: str) -> dict[str, bool]:
        """Drop the server's copy. Never called on its own: deleting a notebook
        on the iPad leaves this one alone."""
        path = path_of(notebook_id)
        row = db.get(NotebookBackup, notebook_id)
        if row is None:
            raise HTTPException(404, "Ese cuaderno no existe en el servidor.")
        db.delete(row)
        db.commit()
        for stale in (path, path.with_suffix(".prev")):
            stale.unlink(missing_ok=True)
        return {"ok": True}
