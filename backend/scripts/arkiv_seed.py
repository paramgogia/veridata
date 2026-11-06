"""Seed VeriData entities directly into Arkiv Testnet (Rabdi).

Usage:
    cd backend
    python -m scripts.arkiv_seed

Requires ARKIV_ACCESS_KEY and ARKIV_PRIVATE_KEY in .env or environment.
"""
from __future__ import annotations

import os
import sys
import time

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import arkiv, config
from app.db import DataRequest, Dataset, Device, SessionLocal, User


def seed_to_arkiv():
    if not arkiv.enabled():
        print("ERROR: Arkiv is not enabled. Set ARKIV_ACCESS_KEY and ARKIV_PRIVATE_KEY in .env")
        sys.exit(1)

    print("=" * 60)
    print("VeriData -> Arkiv Rabdi Testnet Seeder")
    print("RPC:", config.ARKIV_RPC_URL)
    print("=" * 60)

    db = SessionLocal()
    try:
        # 1. Seed Contributors
        users = db.query(User).all()
        print(f"\n[1/4] Seeding {len(users)} Contributors to Arkiv...")
        for u in users:
            res = arkiv.write_contributor(
                address=u.address,
                name=u.name,
                bio=u.bio,
                roles=u.roles or ["contributor"],
                reputation=u.reputation or 4.5,
                sample_count=50,
                created_at=u.created_at,
            )
            print(f"  * Contributor '{u.name}' ({u.address[:10]}...):", "OK" if res.get("ok") else res.get("error"))

        # 2. Seed Devices
        devices = db.query(Device).all()
        print(f"\n[2/4] Seeding {len(devices)} Devices to Arkiv...")
        for d in devices:
            owner = db.get(User, d.owner_id)
            res = arkiv.write_device(
                device_id=d.id,
                owner_address=owner.address if owner else "0x0000000000000000000000000000000000000000",
                name=d.name,
                kind="simulated" if d.simulated else d.kind,
                pubkey_hex=d.pubkey_hex or "",
                signing_mode=d.signing_mode or "dev-software",
                registration_tx=d.registration_tx or "",
                registration_mode=d.registration_mode or "local",
                status=d.status or "registered",
                created_at=d.created_at,
            )
            print(f"  * Device '{d.name}' ({d.id}):", "OK" if res.get("ok") else res.get("error"))

        # 3. Seed Buyer Requests (Demands with native TTL)
        requests = db.query(DataRequest).all()
        print(f"\n[3/4] Seeding {len(requests)} Buyer Demands to Arkiv...")
        for r in requests:
            buyer = db.get(User, r.buyer_id)
            res = arkiv.write_request(
                request_id=r.id,
                buyer_address=buyer.address if buyer else "0x0000000000000000000000000000000000000000",
                title=r.title,
                category=r.category,
                quantity=r.quantity,
                accepted=r.accepted,
                price_per_sample=r.price_per_sample,
                status=r.status,
                spec=r.spec or {},
                spec_hash=r.spec_hash or "",
                chain_request_id=r.chain_request_id,
                fund_tx=r.fund_tx or "",
                mode=r.mode or "local",
                deadline=r.deadline or (time.time() + 86400 * 30),
                created_at=r.created_at,
            )
            print(f"  * Request #{r.id} '{r.title[:30]}...' (TTL: {int(r.deadline)}):", "OK" if res.get("ok") else res.get("error"))

        # 4. Seed Datasets
        datasets = db.query(Dataset).all()
        print(f"\n[4/4] Seeding {len(datasets)} Datasets to Arkiv...")
        for d in datasets:
            owner = db.get(User, d.owner_id)
            res = arkiv.write_dataset(
                dataset_id=d.id,
                owner_address=owner.address if owner else "0x0000000000000000000000000000000000000000",
                title=d.title,
                categories=d.categories or [],
                sensor_types=d.sensor_types or [],
                location=d.location or "",
                quality_score=d.quality_score or 0.0,
                sample_count=d.sample_count or 0,
                price=d.price or 0,
                content_root=d.content_root or "",
                chain_dataset_id=d.chain_dataset_id,
                publish_tx=d.publish_tx or "",
                mode=d.mode or "local",
                status=d.status or "listed",
                created_at=d.created_at,
            )
            print(f"  * Dataset #{d.id} '{d.title[:30]}...':", "OK" if res.get("ok") else res.get("error"))

        print("\n" + "=" * 60)
        print("Arkiv Seeding Complete!")
        print("=" * 60)
    finally:
        db.close()


if __name__ == "__main__":
    seed_to_arkiv()

