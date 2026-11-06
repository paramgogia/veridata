"""Seed realistic DEMO data (all flagged is_demo / mode 'demo-seed', synthetic imagery only).

    python -m app.seed            # seed if empty
    python -m app.seed --reset    # wipe backend/data DB + blobs and reseed
"""
from __future__ import annotations

import shutil
import sys
import time

from . import config, crypto, ledger, provenance, quality, synth
from .db import Base, DataRequest, Dataset, Device, License, RfidTag, Sample, Submission, SessionLocal, User, engine, init_db

DAY = 86400
G = 10**9  # gwei per ETH


def eth(x: float) -> int:
    return int(x * G)


def mk_user(db, name, address, bio, persona="", rep=4.0, faucet=5.0):
    u = User(address=address.lower(), name=name, bio=bio, persona=persona, reputation=rep)
    db.add(u)
    db.flush()
    ledger.record(db, "faucet", eth(faucet), to=u.id, memo="demo-ledger starting balance")
    return u


def mk_device(db, owner, dev_id, name, simulated=True):
    k, pub = crypto.gen_p256()
    d = Device(id=dev_id, owner_id=owner.id, name=name, pubkey_hex=pub, signing_mode="dev-software", simulated=simulated,
               privkey_wrapped=crypto.wrap(crypto.priv_to_bytes(k), f"device:{dev_id}"),
               sensors=["esp32-cam", "ir obstacle", "rc522 rfid", "dht temp/humidity"],
               registration_mode="local", created_at=time.time() - 40 * DAY, last_seen=time.time() - 3600)
    db.add(d)
    db.flush()
    return d


def add_samples(db, owner, dev, kind, labels, n_per, base_t, desc, cats, rfid_fn=None, sensors_fn=None, seed0=0, phashes=None):
    out = []
    i = 0
    for label in labels:
        for j in range(n_per):
            seed = seed0 + i * 1000 + j
            img = synth.generate(kind, label, seed)
            st = quality.image_stats(img)
            rfid = rfid_fn(j) if rfid_fn else []
            sensors = sensors_fn(j, label) if sensors_fn else {}
            t = base_t + (i * n_per + j) * 1800
            man = provenance.build_manifest(dev, img, st["width"], st["height"], sensors, rfid, {"fw": "seed", "simulated": True, "source": "demo-seed"}, captured_at=t)
            sig = provenance.sign_manifest_dev(dev, man)
            s = provenance.store_sample(db, owner_id=owner.id, media=img, manifest=man, signature=sig, dev=dev, label=label,
                                        description=f"{desc} — {label.replace('_', ' ')}", categories=cats, rfid=rfid, sensors=sensors,
                                        is_demo=True, phash=st["phash"], blur_preview=False)
            q = quality.assess(img, s.description, cats, label, [], use_model=False)
            q.pop("img", None)
            q["provenance"] = {"valid": True, "signer_mode": "dev-software"}
            s.quality, s.status = q, "published"
            out.append(s)
        i += 1
    return out


def mk_dataset(db, owner, title, desc, samples, cats, tags, location, price, sensor_types, fmt="JPEG 128×128"):
    leaves = [s.manifest_hash or s.media_sha256 for s in samples]
    d = Dataset(title=title, description=desc, owner_id=owner.id, categories=cats, tags=tags, location=location, price=price,
                content_root=crypto.merkle_root(leaves), sample_count=len(samples), format=fmt, mode="demo-seed", status="listed",
                quality_score=round(sum(s.quality["quality_score"] for s in samples) / len(samples), 1), sensor_types=sensor_types,
                capture_start=min(s.captured_at for s in samples), capture_end=max(s.captured_at for s in samples), is_demo=True,
                created_at=max(s.captured_at for s in samples))
    db.add(d)
    db.flush()
    for s in samples:
        s.dataset_id = d.id
    return d


def mk_request(db, buyer, contributors, title, desc, cat, qty, price, accepted, days, spec, created_days_ago=5):
    now = time.time()
    r = DataRequest(buyer_id=buyer.id, title=title, description=desc, category=cat, quantity=qty, price_per_sample=price,
                    accepted=accepted, deadline=now + days * DAY, spec=spec, mode="local", status="open" if accepted < qty else "filled",
                    deposited=qty * price, released=accepted * price, is_demo=True, created_at=now - created_days_ago * DAY)
    r.spec_hash = crypto.sha256_hex(crypto.canonical({"title": title, **spec}))
    db.add(r)
    db.flush()
    ledger.record(db, "escrow_deposit", qty * price, frm=buyer.id, ref=f"request:{r.id}", memo="demo ledger escrow (seed)")
    if accepted:
        per = accepted // len(contributors)
        for k, c in enumerate(contributors):
            n = per + (accepted - per * len(contributors) if k == 0 else 0)
            payout = n * (price - ledger.fee(price))
            ledger.record(db, "payout", payout, to=c.id, ref=f"request:{r.id}", memo=f"buyer:{buyer.id}",
                          )
            db.add(Submission(request_id=r.id, sample_id=None, contributor_id=c.id, status="accepted", payout=payout,
                              reasons=[f"seed aggregate: {n} accepted samples"], mode="local", created_at=now - k * 3 * 3600))
    return r


def seed(reset: bool = False) -> None:
    if reset:
        engine.dispose()
        for sub in ("blobs", "previews", "weights"):
            shutil.rmtree(config.DATA / sub, ignore_errors=True)
            (config.DATA / sub).mkdir(exist_ok=True)
        Base.metadata.drop_all(engine)
    init_db()
    db = SessionLocal()
    if db.query(User).count():
        print("database already seeded (use --reset)")
        return
    from .routers.core import DEMO_PERSONAS
    t0 = time.time() - 30 * DAY
    asha = mk_user(db, DEMO_PERSONAS["contributor"]["name"], DEMO_PERSONAS["contributor"]["address"], DEMO_PERSONAS["contributor"]["bio"], "contributor", 4.7)
    north = mk_user(db, DEMO_PERSONAS["buyer"]["name"], DEMO_PERSONAS["buyer"]["address"], DEMO_PERSONAS["buyer"]["bio"], "buyer", 4.3, faucet=60)
    garage = mk_user(db, "Konkan Motors Garage", "0x9a7a000000000000000000000000000000000c01", "Independent repair shop documenting vehicle damage.", rep=4.4)
    retail = mk_user(db, "Pune Retail Labs", "0x9a7a000000000000000000000000000000000c02", "Store-ops team instrumenting shelves with ESP32 + RFID.", rep=4.5)
    fleet = mk_user(db, "Western Ghats Fleet", "0x9a7a000000000000000000000000000000000c03", "Rural delivery fleet with dashcam rigs.", rep=4.1)
    insurer = mk_user(db, "Suraksha General Insurance", "0x9a7a000000000000000000000000000000000b02", "Claims-fraud analytics team.", rep=4.0, faucet=40)

    d_asha = mk_device(db, asha, "vd-asha-field-01", "Orchard rig · Ratnagiri (simulated)")
    d_garage = mk_device(db, garage, "vd-garage-bay-02", "Inspection bay cam")
    d_retail = mk_device(db, retail, "vd-retail-aisle-04", "Aisle 4 shelf monitor")
    d_fleet = mk_device(db, fleet, "vd-fleet-dash-07", "Dashcam · truck 07")

    for uid, label, typ in [("04A1B2C3", "SKU-1182 · Basmati rice 5 kg", "product"), ("04D4E5F6", "SKU-2044 · Alphonso pulp 850 g", "product"),
                            ("0477AA19", "Pallet P-17 · inbound", "pallet"), ("04C0FFEE", "Aisle 4 · bay marker", "location")]:
        db.add(RfidTag(uid=uid, label=label, asset_type=typ, owner_id=retail.id))

    leaf = add_samples(db, asha, d_asha, "leaf", ["healthy", "pest_damage", "fungal_spot"], 40, t0, "Alphonso mango leaf, orchard row capture",
                       ["agriculture", "crop-disease", "pest-damage"], sensors_fn=lambda j, l: {"ir": False, "temp_c": 29.0 + (j % 6) * 0.3, "humidity_pct": 71 + j % 9}, seed0=1)
    dmg = add_samples(db, garage, d_garage, "damage", ["dent", "scratch", "cracked_glass"], 32, t0 + 2 * DAY, "Vehicle panel inspection photo",
                      ["insurance", "vehicle-damage"], sensors_fn=lambda j, l: {"ir": True, "temp_c": 31.0 + (j % 5) * 0.4, "humidity_pct": 55 + j % 12}, seed0=50_000)
    road = add_samples(db, fleet, d_fleet, "road", ["rain_night", "clear_night"], 36, t0 + 4 * DAY, "Rural two-lane road, dashcam frame",
                       ["autonomous-driving", "night", "weather"], seed0=90_000)
    tags = ["04A1B2C3", "04D4E5F6", "0477AA19"]
    shelf = add_samples(db, retail, d_retail, "shelf", ["shelf_stocked", "shelf_empty"], 36, t0 + 6 * DAY, "Retail shelf bay, aisle 4",
                        ["retail", "inventory", "rfid-tagged"],
                        rfid_fn=lambda j: [{"uid": tags[j % 3], "seen_ms_ago": 400 + j * 7}],
                        sensors_fn=lambda j, l: {"ir": l == "shelf_stocked", "temp_c": 24.5 + (j % 4) * 0.2, "humidity_pct": 48 + j % 6}, seed0=130_000)
    occ = add_samples(db, retail, d_retail, "ir", ["empty", "occupied_1", "occupied_many"], 30, t0 + 8 * DAY, "Anonymous 8×8 IR occupancy grid, warehouse aisle",
                      ["warehouse", "occupancy", "ir-sensing"], sensors_fn=lambda j, l: {"ir": l != "empty", "temp_c": 30.5 + (j % 7) * 0.3, "humidity_pct": 62 + j % 10}, seed0=170_000)

    ds_leaf = mk_dataset(db, asha, "Alphonso mango leaf condition — Ratnagiri orchards", "Device-signed close-ups of mango leaves labelled healthy, pest damage (chewed lamina) and fungal leaf spot. Captured on ESP32 orchard rigs with temperature and humidity metadata.", leaf,
                         ["agriculture", "crop-disease", "pest-damage"], ["mango", "leaf", "pest", "fungal", "orchard"], "Ratnagiri, Maharashtra", eth(0.002), ["camera", "temp_c", "humidity_pct"])
    ds_dmg = mk_dataset(db, garage, "Vehicle damage evidence — dents, scratches, cracked glass", "Inspection-bay photos of panel dents, paint scratches and cracked glass. Each frame carries a signed capture manifest for claims-fraud model training.", dmg,
                        ["insurance", "vehicle-damage"], ["dent", "scratch", "windshield", "claims"], "Kolhapur, Maharashtra", eth(0.003), ["camera", "ir", "temp_c"])
    ds_road = mk_dataset(db, fleet, "Rural night driving — rain vs clear", "Night dashcam frames on rural two-lane roads, labelled heavy rain vs clear conditions.", road,
                         ["autonomous-driving", "night", "weather"], ["rain", "night", "rural", "dashcam"], "Western Ghats", eth(0.0025), ["camera"])
    ds_shelf = mk_dataset(db, retail, "Retail shelf stock levels with RFID-tagged SKUs", "Shelf-bay captures labelled stocked vs stock-out, each associated with RFID SKU tags read during capture, with IR presence readings.", shelf,
                          ["retail", "inventory", "rfid-tagged"], ["shelf", "stock-out", "rfid", "sku"], "Pune, Maharashtra", eth(0.0015), ["camera", "rfid", "ir"])
    ds_occ = mk_dataset(db, retail, "Anonymous warehouse occupancy — IR grids", "Privacy-preserving 8×8 IR occupancy grids (no imagery of people) labelled empty / one person / crowded.", occ,
                        ["warehouse", "occupancy", "ir-sensing"], ["occupancy", "infrared", "anonymous"], "Bhiwandi, Maharashtra", eth(0.001), ["ir-grid", "ir"], fmt="IR grid 8×8 → 128×128")

    # Buyer already licenses the occupancy set so the Training Room has data immediately.
    db.add(License(dataset_id=ds_occ.id, buyer_id=north.id, price=ds_occ.price, mode="local", via="direct", created_at=time.time() - 2 * DAY))
    ledger.record(db, "purchase", ds_occ.price - ledger.fee(ds_occ.price), frm=north.id, to=retail.id, ref=f"dataset:{ds_occ.id}")
    ledger.record(db, "platform_fee", ledger.fee(ds_occ.price), frm=north.id, ref=f"dataset:{ds_occ.id}")

    # Insurance tamper demo: 6 photos. 3 valid device signatures; 3 lacking valid provenance.
    ins = []
    for k, label in enumerate(["dent", "scratch", "cracked_glass"]):
        img = synth.generate("damage", label, 777_000 + k)
        st = quality.image_stats(img)
        man = provenance.build_manifest(d_garage, img, st["width"], st["height"], {"ir": True, "temp_c": 30.2, "humidity_pct": 60.0}, [], {"source": "insurance-demo"})
        ins.append(provenance.store_sample(db, owner_id=garage.id, media=img, manifest=man, signature=provenance.sign_manifest_dev(d_garage, man), dev=d_garage,
                                           label=label, description=f"Claim photo #{k + 1} — {label}", categories=["insurance"], is_demo=True, blur_preview=False))
    img = synth.generate("damage", "dent", 778_001)  # 4: no manifest at all
    ins.append(provenance.store_sample(db, owner_id=garage.id, media=img, manifest=None, signature="", dev=None, label="dent",
                                       description="Claim photo #4 — emailed by claimant (no device provenance)", categories=["insurance"], is_demo=True, blur_preview=False))
    rogue, _ = crypto.gen_p256()  # 5: signed by a key that is NOT the registered device key
    img = synth.generate("damage", "scratch", 778_002)
    st = quality.image_stats(img)
    man = provenance.build_manifest(d_garage, img, st["width"], st["height"], {}, [], {"source": "insurance-demo"})
    ins.append(provenance.store_sample(db, owner_id=garage.id, media=img, manifest=man, signature=crypto.sign_digest_hex(rogue, crypto.canonical(man)), dev=d_garage,
                                       label="scratch", description="Claim photo #5 — signature from unregistered key", categories=["insurance"], is_demo=True, blur_preview=False))
    img = synth.generate("damage", "cracked_glass", 778_003)  # 6: media edited after signing
    st = quality.image_stats(img)
    man = provenance.build_manifest(d_garage, img, st["width"], st["height"], {}, [], {"source": "insurance-demo"})
    sig = provenance.sign_manifest_dev(d_garage, man)
    edited = synth.generate("damage", "cracked_glass", 778_004)
    s6 = provenance.store_sample(db, owner_id=garage.id, media=edited, manifest=man, signature=sig, dev=d_garage, label="cracked_glass",
                                 description="Claim photo #6 — image edited after capture", categories=["insurance"], is_demo=True, blur_preview=False)
    ins.append(s6)
    for s in ins:
        s.keywords = ["insurance-demo"]
        s.status = "verified"

    spec = lambda **kw: {"media_format": "image/jpeg", "min_resolution": "128x128", "require_device_signature": True, "min_quality": 50, **kw}
    mk_request(db, north, [fleet], "Heavy rain at night — rural driving footage", "Frames from rural two-lane roads at night in heavy rain. Headlights on, wipers visible acceptable. No identifiable people or licence plates.",
               "autonomous-driving", 2000, eth(0.0005), 640, 14, spec(conditions="night, heavy rain, rural road", sensors=["camera"], labels=["rain_night"], location="India, rural"))
    mk_request(db, north, [asha], "500 mango leaves showing visible pest damage", "Close-up images of mango leaves with visible insect feeding damage. One leaf per frame, 10–30 cm distance.",
               "pest-damage", 500, eth(0.0008), 120, 21, spec(labels=["pest_damage"], required_metadata=["description"], location="Konkan belt"))
    mk_request(db, retail, [retail], "Shelf stock-out captures with RFID-tagged SKUs", "Shelf bays photographed at stock-out and restock moments. The SKU's RFID tag must be read during the capture session; IR presence reading required.",
               "retail", 1000, eth(0.0004), 85, 10, spec(labels=["shelf_empty", "shelf_stocked"], required_metadata=["rfid", "ir"], sensors=["camera", "rfid", "ir"]))
    mk_request(db, insurer, [garage], "Genuine vehicle damage photos for fraud detection", "Device-signed photos of real panel damage. Unsigned or edited images are rejected automatically.",
               "insurance", 300, eth(0.0015), 41, 30, spec(labels=["dent", "scratch", "cracked_glass"], min_quality=60))
    mk_request(db, north, [retail], "Anonymous IR occupancy grids — warehouse aisles", "8×8 thermal occupancy grids only. No camera imagery of people.",
               "occupancy", 800, eth(0.0003), 300, 18, spec(sensors=["ir"], labels=["empty", "occupied_1", "occupied_many"]))
    mk_request(db, insurer, [garage], "Cracked windshield close-ups", "Windshield cracks and chips, 30–60 cm.", "vehicle-damage", 200, eth(0.002), 190, 4,
               spec(labels=["cracked_glass"]), created_days_ago=20)
    db.commit()
    print(f"seeded: {db.query(Dataset).count()} datasets, {db.query(Sample).count()} samples, {db.query(DataRequest).count()} requests")
    db.close()


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv)
