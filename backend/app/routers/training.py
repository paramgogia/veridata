"""Training Room: licensed-dataset search, workspaces, runs, metrics and weight export.
No raw dataset download, no file browser, no shell — only the guided pipeline."""
from __future__ import annotations

import io
import json
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import auth, training
from ..config import DATA
from ..db import Dataset, Sample, TrainingRun, User, Workspace, audit, get_db
from ..serialize import dataset_view

router = APIRouter(prefix="/api")


@router.get("/training/models")
def models():
    return training.BASE_MODELS


@router.get("/training/datasets")
def licensed(user: User = Depends(auth.current_user), db: Session = Depends(get_db), q: str = ""):
    out = []
    for did in training.licensed_dataset_ids(db, user):
        d = db.get(Dataset, did)
        if not d or d.status == "pending":
            continue
        if q and q.lower() not in f"{d.title} {' '.join(d.tags or [])} {' '.join(d.categories or [])}".lower():
            continue
        labels: dict[str, int] = {}
        for (lbl,) in db.query(Sample.label).filter(Sample.dataset_id == d.id).all():
            labels[lbl or "unlabelled"] = labels.get(lbl or "unlabelled", 0) + 1
        out.append(dataset_view(db, d) | {"label_counts": labels, "access": "owner" if d.owner_id == user.id else "license"})
    return out


class WorkspaceBody(BaseModel):
    name: str
    dataset_ids: list[int] = []


def _ws(db: Session, wid: int, user: User) -> Workspace:
    w = db.get(Workspace, wid)
    if not w or w.owner_id != user.id:
        raise HTTPException(404, "workspace not found")
    return w


def ws_view(db: Session, w: Workspace) -> dict:
    runs = db.query(TrainingRun).filter(TrainingRun.workspace_id == w.id).order_by(TrainingRun.id.desc()).all()
    return {"id": w.id, "name": w.name, "dataset_ids": w.dataset_ids, "created_at": w.created_at,
            "datasets": [dataset_view(db, db.get(Dataset, i)) for i in w.dataset_ids if db.get(Dataset, i)],
            "runs": [run_view(r, brief=True) for r in runs]}


def run_view(r: TrainingRun, brief: bool = False) -> dict:
    d = {"id": r.id, "workspace_id": r.workspace_id, "base_model": r.base_model, "params": r.params, "dataset_ids": r.dataset_ids,
         "status": r.status, "progress": r.progress, "before": r.before, "after": r.after, "classes": r.classes,
         "weights_sha256": r.weights_sha256, "error": r.error, "created_at": r.created_at, "finished_at": r.finished_at}
    if not brief:
        d.update({"logs": r.logs, "history": r.history, "card": r.card})
    return d


@router.get("/workspaces")
def list_ws(user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    return [ws_view(db, w) for w in db.query(Workspace).filter(Workspace.owner_id == user.id).order_by(Workspace.id.desc()).all()]


@router.post("/workspaces")
def create_ws(body: WorkspaceBody, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    allowed = set(training.licensed_dataset_ids(db, user))
    if any(d not in allowed for d in body.dataset_ids):
        raise HTTPException(403, "you can only add datasets you have licensed")
    w = Workspace(owner_id=user.id, name=body.name[:120] or "Untitled workspace", dataset_ids=body.dataset_ids)
    db.add(w)
    db.commit()
    return ws_view(db, w)


@router.get("/workspaces/{wid}")
def get_ws(wid: int, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    return ws_view(db, _ws(db, wid, user))


@router.patch("/workspaces/{wid}")
def update_ws(wid: int, body: WorkspaceBody, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    w = _ws(db, wid, user)
    allowed = set(training.licensed_dataset_ids(db, user))
    if any(d not in allowed for d in body.dataset_ids):
        raise HTTPException(403, "you can only add datasets you have licensed")
    w.name, w.dataset_ids = body.name[:120] or w.name, body.dataset_ids
    db.commit()
    return ws_view(db, w)


class RunBody(BaseModel):
    base_model: str
    epochs: int = 8
    learning_rate: float = 0.003
    batch_size: int = 32
    val_split: float = 0.25
    augment: bool = True


@router.post("/workspaces/{wid}/runs")
def start_run(wid: int, body: RunBody, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    w = _ws(db, wid, user)
    if body.base_model not in {m["id"] for m in training.BASE_MODELS}:
        raise HTTPException(400, "unknown base model")
    if not w.dataset_ids:
        raise HTTPException(400, "add at least one licensed dataset")
    if db.query(TrainingRun).filter(TrainingRun.owner_id == user.id, TrainingRun.status.in_(["queued", "running"])).count():
        raise HTTPException(429, "one training run at a time")
    r = TrainingRun(workspace_id=w.id, owner_id=user.id, base_model=body.base_model, dataset_ids=list(w.dataset_ids),
                    params=body.model_dump(exclude={"base_model"}), logs=[])
    db.add(r)
    audit(db, user.address, "training.start", str(w.id), {"model": body.base_model, "datasets": w.dataset_ids})
    db.commit()
    training.start(r.id)
    return run_view(r)


@router.get("/runs/{rid}")
def get_run(rid: int, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    r = db.get(TrainingRun, rid)
    if not r or r.owner_id != user.id:
        raise HTTPException(404, "run not found")
    return run_view(r)


@router.get("/runs/{rid}/weights")
def weights(rid: int, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    r = db.get(TrainingRun, rid)
    if not r or r.owner_id != user.id or r.status != "completed" or not re.fullmatch(r"run_\d+\.pt", r.weights_file or ""):
        raise HTTPException(404, "weights not available")
    audit(db, user.address, "training.export_weights", str(rid), {"sha256": r.weights_sha256})
    db.commit()
    return FileResponse(DATA / "weights" / r.weights_file, media_type="application/octet-stream",
                        filename=f"veridata-run{rid}-{r.base_model}.pt")


@router.get("/runs/{rid}/card")
def card(rid: int, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    r = db.get(TrainingRun, rid)
    if not r or r.owner_id != user.id or not r.card:
        raise HTTPException(404, "model card not available")
    return Response(json.dumps(r.card, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="veridata-run{rid}-model-card.json"'})


@router.get("/datasets/{ds_id}/download")
def raw_download(ds_id: int, user: User | None = Depends(auth.optional_user), db: Session = Depends(get_db)):
    """Exists only to make the restriction explicit and auditable."""
    audit(db, user.address if user else "anonymous", "access.denied.dataset_export", str(ds_id))
    db.commit()
    raise HTTPException(403, "Dataset export is disabled. Licenses grant in-platform training access only; export trained weights instead.")
