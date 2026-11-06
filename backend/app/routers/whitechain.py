"""x402 on Whitechain: buy a dataset license with USDT, gaslessly.

    GET /api/x402/datasets/{id}/license
      no X-PAYMENT header  -> 402 + payment requirements (price, asset, nonce to sign)
      X-PAYMENT: base64(json{x402Version, scheme, network, payload:{signature, authorization, salt}})
                           -> relayer settles on chain -> 200 + license + access token
                              (+ X-PAYMENT-RESPONSE header)

The web UI and the AI agent use the same endpoint. The payer never needs WBT.
"""
from __future__ import annotations

import base64
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .. import auth, config
from ..chain import whitechain as wc
from ..db import Dataset, License, Sample, User, WcPayment, audit, get_db
from .market import _grant

router = APIRouter(prefix="/api")


def _dataset(db: Session, ds_id: int) -> tuple[Dataset, str]:
    d = db.get(Dataset, ds_id)
    if not d or d.status != "listed":
        raise HTTPException(404, "dataset not available")
    seller = db.get(User, d.owner_id)
    if not seller or not seller.address or len(seller.address) != 42:
        raise HTTPException(409, "seller has no payout wallet")
    return d, seller.address


def _b64json(s: str) -> dict:
    try:
        return json.loads(base64.b64decode(s + "=" * (-len(s) % 4)))
    except Exception:
        raise HTTPException(400, "X-PAYMENT must be base64-encoded JSON")


@router.get("/x402/datasets/{ds_id}/license")
def x402_license(ds_id: int, request: Request, x_payment: str = Header(default=""), x_client: str = Header(default=""),
                 db: Session = Depends(get_db)):
    d, seller = _dataset(db, ds_id)
    price = wc.usdt_price(d.price)
    if not x_payment:
        try:
            req = wc.requirements(d.id, seller, price, str(request.url), d.title)
        except wc.PayError as e:
            raise HTTPException(e.status, str(e))
        return JSONResponse(status_code=402, content={
            "x402Version": 1, "error": "X-PAYMENT header is required", "accepts": [req],
            "typedData": wc.typed_data("", price, 0, int(req["extra"]["validBefore"]), req["extra"]["nonce"]),
        })

    p = _b64json(x_payment)
    if p.get("scheme") != "exact" or p.get("network") != wc.NETWORK:
        raise HTTPException(400, f"unsupported scheme/network; use exact on {wc.NETWORK}")
    try:
        r = wc.settle(db, dataset_id=d.id, seller=seller, expected_value=price, payload=p.get("payload") or {})
    except wc.PayError as e:
        raise HTTPException(e.status, str(e))

    buyer = db.query(User).filter(User.address == r["buyer"]).first()
    if not buyer:
        buyer = User(address=r["buyer"], name=f"{r['buyer'][:6]}…{r['buyer'][-4:]}")
        db.add(buyer)
        db.flush()
    via = "x402-web" if x_client == "web" else "x402-agent"
    db.add(WcPayment(dataset_id=d.id, buyer=r["buyer"], seller=r["seller"], value=r["value"], fee=r["fee"], tx_hash=r["tx_hash"],
                     gas_used=r["gas_used"], gas_cost_wei=str(r["gas_cost_wei"]), via=via))
    if not db.query(License).filter(License.dataset_id == d.id, License.buyer_id == buyer.id).first():
        _grant(db, d, buyer, "whitechain", r["tx_hash"], via="x402")
    audit(db, r["buyer"], "license.whitechain", str(d.id), {"tx": r["tx_hash"], "usdt": r["value"], "via": via}, auth.client_ip(request))
    db.commit()

    receipt = {"success": True, "transaction": r["tx_hash"], "network": wc.NETWORK, "payer": r["buyer"]}
    body = {
        "license": {"dataset_id": d.id, "title": d.title, "buyer": r["buyer"], "mode": "whitechain"},
        "payment": {**r, "asset": config.WC_USDT, "usdt": r["value"] / 1e6, "gas_paid_by": wc.relayer_address()},
        # session token for the paying wallet: lets an agent fetch what it bought
        "access_token": auth.make_token(buyer.id),
        "manifests_url": f"/api/datasets/{d.id}/manifests",
        "sample_count": db.query(Sample).filter(Sample.dataset_id == d.id).count(),
    }
    return JSONResponse(body, headers={"X-PAYMENT-RESPONSE": base64.b64encode(json.dumps(receipt).encode()).decode(),
                                       "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"})


@router.get("/whitechain/status")
def wc_status(db: Session = Depends(get_db)):
    """Business view: relayer health, gas spent, USDT volume, every party's payments."""
    st = wc.status()
    rows = db.query(WcPayment).order_by(WcPayment.created_at.desc()).limit(50).all()
    titles = {d.id: d.title for d in db.query(Dataset).filter(Dataset.id.in_({r.dataset_id for r in rows})).all()} if rows else {}
    all_rows = db.query(WcPayment).all()
    st["totals"] = {
        "payments": len(all_rows),
        "volumeUsdt": sum(r.value for r in all_rows) / 1e6,
        "feesUsdt": sum(r.fee for r in all_rows) / 1e6,
        "sellerPayoutsUsdt": sum(r.value - r.fee for r in all_rows) / 1e6,
        "gasSpentWbt": sum(int(r.gas_cost_wei or 0) for r in all_rows) / 1e18,
        "agentPayments": sum(1 for r in all_rows if r.via == "x402-agent"),
    }
    st["payments"] = [{"dataset_id": r.dataset_id, "title": titles.get(r.dataset_id, ""), "buyer": r.buyer, "seller": r.seller,
                       "usdt": r.value / 1e6, "fee": r.fee / 1e6, "gasWbt": int(r.gas_cost_wei or 0) / 1e18, "via": r.via,
                       "tx_hash": r.tx_hash, "tx_url": wc.explorer_tx(r.tx_hash), "at": r.created_at} for r in rows]
    return st


@router.get("/whitechain/price/{ds_id}")
def wc_price(ds_id: int, db: Session = Depends(get_db)):
    d, seller = _dataset(db, ds_id)
    return {"dataset_id": d.id, "usdt_units": wc.usdt_price(d.price), "usdt": wc.usdt_price(d.price) / 1e6, "seller": seller,
            "enabled": wc.enabled()}
