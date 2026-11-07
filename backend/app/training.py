"""Controlled fine-tuning pipeline (real PyTorch training, CPU-friendly).

The trainer runs inside the platform process: licensed media is decrypted in memory only,
never written to disk or returned by any API. The buyer receives metrics, logs and the
trained weights. Exported weights can still leak information about training data
(memorization / membership inference) — we report a generalization-gap indicator, not a guarantee.
"""
from __future__ import annotations

import hashlib
import io
import json
import random
import threading
import time
import traceback
from typing import Any

from .config import DATA
from .db import Dataset, License, Sample, SessionLocal, TrainingRun, User

BASE_MODELS = [
    {"id": "veri-cnn-s", "name": "Veri-CNN Small", "params": "0.1M", "input": "64×64 RGB", "task": "image classification",
     "desc": "Compact 3-block CNN trained from scratch. Fast on CPU; best for small, distinctive datasets.", "pretrained": False},
    {"id": "resnet18", "name": "ResNet-18 (ImageNet)", "params": "11.2M", "input": "96×96 RGB", "task": "image classification",
     "desc": "Transfer learning from ImageNet weights (downloaded on first use); falls back to random init offline.", "pretrained": True},
]


def _build(model_id: str, n_classes: int, log):
    import torch.nn as nn
    if model_id == "resnet18":
        import torchvision
        try:
            m = torchvision.models.resnet18(weights=torchvision.models.ResNet18_Weights.DEFAULT)
            log("loaded ResNet-18 ImageNet weights")
        except Exception as e:
            m = torchvision.models.resnet18(weights=None)
            log(f"WARNING: ImageNet weights unavailable ({type(e).__name__}); using random init")
        m.fc = nn.Linear(m.fc.in_features, n_classes)
        return m, 96
    m = nn.Sequential(
        nn.Conv2d(3, 16, 3, padding=1), nn.GroupNorm(4, 16), nn.ReLU(), nn.MaxPool2d(2),
        nn.Conv2d(16, 32, 3, padding=1), nn.GroupNorm(8, 32), nn.ReLU(), nn.MaxPool2d(2),
        nn.Conv2d(32, 64, 3, padding=1), nn.GroupNorm(8, 64), nn.ReLU(), nn.AdaptiveAvgPool2d(1),
        nn.Flatten(), nn.Dropout(0.2), nn.Linear(64, n_classes))
    return m, 64


def licensed_dataset_ids(db, user: User) -> list[int]:
    owned = [d.id for d in db.query(Dataset).filter(Dataset.owner_id == user.id).all()]
    lic = [l.dataset_id for l in db.query(License).filter(License.buyer_id == user.id).all()]
    return sorted(set(owned + lic))


def _evaluate(model, X, y):
    import torch
    model.eval()
    with torch.no_grad():
        out = model(X)
        loss = torch.nn.functional.cross_entropy(out, y).item()
        pred = out.argmax(1)
        acc = (pred == y).float().mean().item()
    n = int(out.shape[1])
    per = {}
    for c in range(n):
        m = y == c
        if m.any():
            per[c] = round((pred[m] == c).float().mean().item(), 3)
    return {"loss": round(loss, 4), "accuracy": round(acc, 4), "per_class": per}


def _variant(img: "Image.Image", rng: random.Random) -> "Image.Image":
    """One random, label-preserving variant: crop, small rotation, flip, brightness/contrast."""
    from PIL import Image, ImageEnhance
    w, h = img.size
    f = rng.uniform(0.78, 0.95)
    cw, ch = int(w * f), int(h * f)
    x0, y0 = rng.randint(0, w - cw), rng.randint(0, h - ch)
    out = img.crop((x0, y0, x0 + cw, y0 + ch)).rotate(rng.uniform(-14, 14), resample=Image.BILINEAR)
    if rng.random() < 0.5:
        out = out.transpose(Image.FLIP_LEFT_RIGHT)
    out = ImageEnhance.Brightness(out).enhance(rng.uniform(0.75, 1.25))
    return ImageEnhance.Contrast(out).enhance(rng.uniform(0.8, 1.2))


def run_training(run_id: int) -> None:
    db = SessionLocal()
    run = db.get(TrainingRun, run_id)

    def log(msg: str):
        run.logs = (run.logs or []) + [f"[{time.strftime('%H:%M:%S')}] {msg}"]
        db.commit()

    try:
        import numpy as np
        import torch
        from PIL import Image
        from . import storage

        torch.manual_seed(0)
        random.seed(0)
        run.status = "running"
        log(f"controlled environment: run #{run.id}, base model {run.base_model}")
        user = db.get(User, run.owner_id)
        allowed = set(licensed_dataset_ids(db, user))
        bad = [d for d in run.dataset_ids if d not in allowed]
        if bad:
            raise PermissionError(f"no training license for dataset(s) {bad}")
        samples = db.query(Sample).filter(Sample.dataset_id.in_(run.dataset_ids), Sample.label != "").all()
        samples = [s for s in samples if s.label.strip()]  # ignore whitespace-only labels
        classes = sorted({s.label.strip() for s in samples if s.label.strip()})
        if len(classes) < 2:
            raise ValueError("need at least 2 labelled classes across the selected datasets")
        counts = {c: sum(1 for s in samples if s.label.strip() == c) for c in classes}
        thin = {c: n for c, n in counts.items() if n < 2}
        few_shot = bool(thin)  # too few samples for an honest held-out split
        log(f"license check passed · {len(samples)} samples · classes: {', '.join(classes)}")
        if few_shot:
            log("few-shot mode: " + ", ".join(f"'{c}' has {n}" for c, n in thin.items())
                + " sample(s). Training on augmented copies (crop/rotate/flip/colour) and validating on different "
                  "augmented copies; accuracy is optimistic. Capture 5+ samples per label for a real evaluation.")
        p = run.params or {}
        epochs = max(1, min(40, int(p.get("epochs", 8))))
        lr = float(p.get("learning_rate", 0.003))
        bs = max(4, min(128, int(p.get("batch_size", 32))))
        val_split = min(0.5, max(0.1, float(p.get("val_split", 0.25))))
        augment = bool(p.get("augment", True))
        model, size = _build(run.base_model, len(classes), log)

        imgs, ys = [], []
        for s in samples:  # decrypt in memory only
            from .provenance import sample_image
            raw = sample_image(s)  # photo bytes, or the signed keyframe of a video
            imgs.append(Image.open(io.BytesIO(raw)).convert("RGB"))
            ys.append(classes.index(s.label.strip()))
            del raw
        log(f"decrypted {len(imgs)} samples in memory (AES-256-GCM); no plaintext written to disk")
        mean = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
        std = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)

        def to_tensor(pils: list) -> torch.Tensor:
            arr = np.stack([np.asarray(im.resize((size, size)), dtype=np.float32) / 255.0 for im in pils])
            return (torch.tensor(arr).permute(0, 3, 1, 2) - mean) / std

        if few_shot:
            # train: original + 5 variants; validate: 2 variants from a different random stream
            tr_rng, va_rng = random.Random(1), random.Random(2)
            t_imgs, t_ys, v_imgs, v_ys = [], [], [], []
            for im, y in zip(imgs, ys):
                t_imgs += [im] + [_variant(im, tr_rng) for _ in range(5)]
                t_ys += [y] * 6
                v_imgs += [_variant(im, va_rng) for _ in range(2)]
                v_ys += [y] * 2
            Xt, Yt = to_tensor(t_imgs), torch.tensor(t_ys, dtype=torch.long)
            Xv, Yv = to_tensor(v_imgs), torch.tensor(v_ys, dtype=torch.long)
            log(f"split (few-shot): {len(Yt)} augmented train / {len(Yv)} augmented validation from {len(imgs)} originals · "
                f"epochs={epochs} lr={lr} batch={bs} augment={augment}")
        else:
            X, Y = to_tensor(imgs), torch.tensor(ys, dtype=torch.long)
            idx = list(range(len(Y)))
            random.shuffle(idx)
            # at least one validation sample per class, but always leave training samples
            nv = min(max(len(classes), int(len(idx) * val_split)), len(idx) - len(classes))
            vi = torch.tensor(idx[:nv], dtype=torch.long)
            ti = torch.tensor(idx[nv:], dtype=torch.long)
            Xt, Yt, Xv, Yv = X[ti], Y[ti], X[vi], Y[vi]
            log(f"split: {len(ti)} train / {len(vi)} validation · epochs={epochs} lr={lr} batch={bs} augment={augment}")

        before = _evaluate(model, Xv, Yv)
        run.before = before
        log(f"baseline (base model, untrained task head): val acc {before['accuracy']:.3f}, loss {before['loss']:.3f}")
        opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
        sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
        history = []
        for ep in range(1, epochs + 1):
            model.train()
            perm = torch.randperm(len(Yt))
            tot, correct, lsum = 0, 0, 0.0
            for i in range(0, len(perm), bs):
                b = perm[i:i + bs]
                xb, yb = Xt[b], Yt[b]
                if augment:
                    if random.random() < 0.5:
                        xb = xb.flip(3)
                    xb = xb + 0.03 * torch.randn_like(xb)
                opt.zero_grad()
                out = model(xb)
                loss = torch.nn.functional.cross_entropy(out, yb)
                loss.backward()
                opt.step()
                lsum += loss.item() * len(b)
                correct += (out.argmax(1) == yb).sum().item()
                tot += len(b)
            sched.step()
            v = _evaluate(model, Xv, Yv)
            h = {"epoch": ep, "train_loss": round(lsum / tot, 4), "train_acc": round(correct / tot, 4),
                 "val_loss": v["loss"], "val_acc": v["accuracy"]}
            history.append(h)
            run.history = list(history)
            run.progress = ep / epochs
            log(f"epoch {ep}/{epochs} · train loss {h['train_loss']:.3f} acc {h['train_acc']:.3f} · val loss {h['val_loss']:.3f} acc {h['val_acc']:.3f}")

        after = _evaluate(model, Xv, Yv)
        train_eval = _evaluate(model, Xt, Yt)
        gap = round(train_eval["accuracy"] - after["accuracy"], 4)
        after["train_accuracy"] = train_eval["accuracy"]
        after["generalization_gap"] = gap
        after["memorization_risk"] = "elevated" if gap > 0.15 else "low"
        after["evaluation"] = "few-shot: augmented copies of the same originals (optimistic)" if few_shot else "held-out samples"
        run.after = after
        run.classes = classes

        buf = io.BytesIO()
        torch.save({"state_dict": model.state_dict(), "classes": classes, "base_model": run.base_model,
                    "input_size": size, "normalize": {"mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225]}}, buf)
        wbytes = buf.getvalue()
        fname = f"run_{run.id}.pt"
        (DATA / "weights" / fname).write_bytes(wbytes)
        run.weights_file = fname
        run.weights_sha256 = hashlib.sha256(wbytes).hexdigest()
        dss = db.query(Dataset).filter(Dataset.id.in_(run.dataset_ids)).all()
        lic = {l.dataset_id: l for l in db.query(License).filter(License.buyer_id == user.id).all()}
        run.card = {
            "model": run.base_model, "classes": classes, "params": {"epochs": epochs, "learning_rate": lr, "batch_size": bs, "val_split": val_split, "augment": augment, "few_shot": few_shot},
            "metrics": {"before": before, "after": after}, "weights_sha256": run.weights_sha256, "weights_bytes": len(wbytes),
            "trained_by": user.address, "trained_at": time.time(),
            "provenance": [{"dataset_id": d.id, "title": d.title, "content_root": d.content_root, "samples": d.sample_count,
                            "license_tx": (lic.get(d.id).tx_hash if lic.get(d.id) else "owner"), "license_mode": (lic.get(d.id).mode if lic.get(d.id) else "owner")} for d in dss],
            "privacy_notice": "Weights were trained on licensed data inside Veridata. Model weights can memorize and leak "
                              "information about training samples; the generalization gap is a coarse indicator only.",
        }
        run.status = "completed"
        run.progress = 1.0
        run.finished_at = time.time()
        log(f"done · val acc {before['accuracy']:.3f} → {after['accuracy']:.3f} · weights sha256 {run.weights_sha256[:16]}… ({len(wbytes)//1024} KB)")
    except Exception as e:
        run.status = "failed"
        run.error = str(e)
        log(f"ERROR: {e}")
        traceback.print_exc()
    finally:
        db.commit()
        db.close()


def start(run_id: int) -> None:
    threading.Thread(target=run_training, args=(run_id,), daemon=True).start()
