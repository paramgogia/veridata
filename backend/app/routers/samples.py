"""Sample import, metadata, AI quality/privacy assessment, verification and the tamper demo.
There is deliberately NO endpoint that returns decrypted original media to buyers."""
from __future__ import annotations

import io
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import auth, crypto, provenance, quality, storage
from ..config import DATA
from ..db import Sample, User, audit, get_db
from ..serialize import sample_view

router = APIRouter(prefix="/api")
MAX_UPLOAD = 8 * 1024 * 1024


@router.get("/previews/{name}")
def preview(name: str):
    if not re.fullmatch(r"[A-Za-z0-9\-_.]+\.jpg", name):
        raise HTTPException(400, "bad name")
    p = DATA / "previews" / name
    if not p.exists():
        raise HTTPException(404, "not found")
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


@router.post("/samples/import")
async def import_sample(request: Request, file: UploadFile = File(...), label: str = Form(""), description: str = Form(""),
                        user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    """Imported media has no device signature: it is stored encrypted but marked 'unsigned'
    (no provenance) and cannot satisfy requests that require device signatures."""
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "file too large (8 MB max)")
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
    except Exception:
        raise HTTPException(415, "only valid JPEG/PNG images are accepted")
    if not data.startswith(b"\xff\xd8"):
        buf = io.BytesIO()
        Image.open(io.BytesIO(data)).convert("RGB").save(buf, "JPEG", quality=92)
        data = buf.getvalue()
    s = provenance.store_sample(db, owner_id=user.id, media=data, manifest=None, signature="", dev=None,
                                label=label[:80], description=description[:2000])
    audit(db, user.address, "sample.import", s.id, {"sha256": s.media_sha256}, auth.client_ip(request))
    db.commit()
    return sample_view(s)


@router.get("/samples")
def my_samples(user: User = Depends(auth.current_user), db: Session = Depends(get_db), status: str = ""):
    q = db.query(Sample).filter(Sample.owner_id == user.id)
    if status:
        q = q.filter(Sample.status == status)
    return [sample_view(s) for s in q.order_by(Sample.created_at.desc()).limit(200).all()]


@router.get("/samples/{sid}")
def get_sample(sid: str, db: Session = Depends(get_db)):
    s = db.get(Sample, sid)
    if not s:
        raise HTTPException(404, "sample not found")
    return sample_view(s, full=True)


class MetaBody(BaseModel):
    label: str | None = None
    description: str | None = None
    keywords: list[str] | None = None
    categories: list[str] | None = None
    rfid_uids: list[str] | None = None


@router.patch("/samples/{sid}")
def update_meta(sid: str, body: MetaBody, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    s = db.get(Sample, sid)
    if not s or s.owner_id != user.id:
        raise HTTPException(404, "sample not found")
    if s.dataset_id:
        raise HTTPException(409, "published samples are immutable")
    # Descriptive metadata is editable; signed manifest fields (hash, sensors, RFID at capture) are not.
    if body.label is not None:
        s.label = body.label[:80]
    if body.description is not None:
        s.description = body.description[:2000]
    if body.keywords is not None:
        s.keywords = [k[:40] for k in body.keywords][:30]
    if body.categories is not None:
        s.categories = [c for c in body.categories if c in quality.CATEGORIES]
    if body.rfid_uids is not None and not s.manifest:
        s.rfid = [{"uid": u, "associated_after_capture": True} for u in body.rfid_uids]
    s.status = "draft"
    s.quality = None
    db.commit()
    return sample_view(s)


@router.post("/samples/{sid}/assess")
def assess(sid: str, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    s = db.get(Sample, sid)
    if not s or s.owner_id != user.id:
        raise HTTPException(404, "sample not found")
    data = storage.get_decrypted(s.storage_ref, s.key_wrapped, s.id)
    others = [p for (p,) in db.query(Sample.phash).filter(Sample.id != s.id, Sample.phash != "").all()]
    res = quality.assess(data, s.description, s.categories, s.label, others)
    ver = provenance.verify_sample(db, s, media_override=data)
    res["provenance"] = {"valid": ver["valid"], "signer_mode": ver.get("signer_mode")}
    s.quality = {k: v for k, v in res.items() if k != "img"}
    s.status = "verified" if res["approved"] else "rejected"
    audit(db, user.address, "sample.assess", s.id, {"approved": res["approved"], "score": res["quality_score"], "engine": res["engine"]})
    db.commit()
    return s.quality | {"status": s.status}


@router.post("/samples/{sid}/verify")
def verify(sid: str, db: Session = Depends(get_db)):
    s = db.get(Sample, sid)
    if not s:
        raise HTTPException(404, "sample not found")
    return provenance.verify_sample(db, s)


@router.post("/demo/tamper/{sid}")
def tamper(sid: str, db: Session = Depends(get_db)):
    """Insurance demo: flip ONE pixel of the decrypted image (in memory, the stored original is
    untouched) and re-run verification to show the hash mismatch."""
    s = db.get(Sample, sid)
    if not s:
        raise HTTPException(404, "sample not found")
    original = storage.get_decrypted(s.storage_ref, s.key_wrapped, s.id)
    img = Image.open(io.BytesIO(original)).convert("RGB")
    r, g, b = img.getpixel((0, 0))
    img.putpixel((0, 0), ((r + 1) % 256, g, b))
    buf = io.BytesIO()
    img.save(buf, "PNG")  # lossless so exactly one pixel differs from the decoded original
    tampered = buf.getvalue()
    return {
        "original": provenance.verify_sample(db, s),
        "tampered": provenance.verify_sample(db, s, media_override=tampered),
        "pixel": {"x": 0, "y": 0, "from": [r, g, b], "to": [(r + 1) % 256, g, b]},
        "tampered_sha256": crypto.sha256_hex(tampered),
    }


@router.get("/samples/{sid}/original")
def original(sid: str, user: User | None = Depends(auth.optional_user), db: Session = Depends(get_db)):
    """Original media is never served to buyers. Only the contributor (owner) may view their own capture."""
    s = db.get(Sample, sid)
    if not s:
        raise HTTPException(404, "sample not found")
    if not user or user.id != s.owner_id:
        audit(db, user.address if user else "anonymous", "access.denied.raw_media", sid)
        db.commit()
        raise HTTPException(403, "Raw media is not downloadable. Licensed data can only be used inside the Training Room.")
    from fastapi.responses import Response
    return Response(storage.get_decrypted(s.storage_ref, s.key_wrapped, s.id), media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})


@router.get("/demo/insurance")
def insurance_demo(db: Session = Depends(get_db)):
    rows = [s for s in db.query(Sample).filter(Sample.is_demo == True).all() if "insurance-demo" in (s.keywords or [])]  # noqa: E712
    rows.sort(key=lambda s: s.description)
    return [sample_view(s) for s in rows]
