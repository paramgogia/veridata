"""Procedural image generator for seed datasets and the simulated device.

All seed imagery is synthetic (no people, no real locations) and labelled as demo data.
Each class has distinct but noisy visual structure so a small model can genuinely learn it."""
from __future__ import annotations

import io
import math
import random
import time

from PIL import Image, ImageDraw, ImageFilter

S = 128


def _jpeg(img: Image.Image, q: int = 88) -> bytes:
    b = io.BytesIO()
    img.save(b, "JPEG", quality=q)
    return b.getvalue()


def _noise(img: Image.Image, r: random.Random, amt: int = 18) -> Image.Image:
    px = img.load()
    for _ in range(S * S // 6):
        x, y = r.randrange(S), r.randrange(S)
        c = px[x, y]
        d = r.randint(-amt, amt)
        px[x, y] = tuple(max(0, min(255, v + d)) for v in c)
    return img


def leaf(label: str, r: random.Random) -> Image.Image:
    bg = (r.randint(60, 110), r.randint(50, 90), r.randint(30, 60))
    img = Image.new("RGB", (S, S), bg)
    d = ImageDraw.Draw(img)
    cx, cy = S // 2 + r.randint(-10, 10), S // 2 + r.randint(-10, 10)
    w, h = r.randint(34, 46), r.randint(54, 62)
    g = (r.randint(40, 80), r.randint(130, 180), r.randint(40, 80))
    if label == "fungal_spot":
        g = (g[0] + 30, g[1] - 10, g[2])
    d.ellipse([cx - w, cy - h, cx + w, cy + h], fill=g)
    d.line([cx, cy - h, cx, cy + h], fill=(g[0] + 40, g[1] + 40, g[2] + 20), width=2)
    for i in range(5):
        yy = cy - h + 15 + i * 18
        d.line([cx, yy, cx - w + 8, yy - 10], fill=(g[0] + 30, g[1] + 30, g[2] + 10), width=1)
        d.line([cx, yy, cx + w - 8, yy - 10], fill=(g[0] + 30, g[1] + 30, g[2] + 10), width=1)
    if label == "pest_damage":
        for _ in range(r.randint(4, 9)):  # chewed holes along the edge and interior
            a = r.uniform(0, 2 * math.pi)
            rx, ry = cx + int(math.cos(a) * w * r.uniform(0.4, 1.0)), cy + int(math.sin(a) * h * r.uniform(0.4, 1.0))
            rad = r.randint(4, 9)
            d.ellipse([rx - rad, ry - rad, rx + rad, ry + rad], fill=bg)
    elif label == "fungal_spot":
        for _ in range(r.randint(8, 16)):
            rx, ry = cx + r.randint(-w + 6, w - 6), cy + r.randint(-h + 8, h - 8)
            rad = r.randint(2, 5)
            d.ellipse([rx - rad - 2, ry - rad - 2, rx + rad + 2, ry + rad + 2], fill=(170, 150, 60))
            d.ellipse([rx - rad, ry - rad, rx + rad, ry + rad], fill=(70, 45, 25))
    img = img.rotate(r.uniform(-30, 30), fillcolor=bg)
    return _noise(img, r)


def damage(label: str, r: random.Random) -> Image.Image:
    base = r.choice([(150, 30, 35), (30, 60, 140), (200, 200, 205), (30, 30, 34), (170, 140, 40)])
    img = Image.new("RGB", (S, S), base)
    d = ImageDraw.Draw(img)
    for i in range(S):  # panel shading
        shade = int(30 * math.sin(i / S * math.pi))
        d.line([0, i, S, i], fill=tuple(min(255, c + shade) for c in base))
    if label == "dent":
        cx, cy = r.randint(40, 88), r.randint(40, 88)
        for k in range(18, 0, -2):
            t = k / 18
            d.ellipse([cx - k * 2, cy - k * 1.4, cx + k * 2, cy + k * 1.4], fill=tuple(int(c * (0.55 + 0.45 * t)) for c in base))
    elif label == "scratch":
        for _ in range(r.randint(3, 7)):
            x0, y0 = r.randint(0, S), r.randint(0, S)
            x1, y1 = x0 + r.randint(-70, 70), y0 + r.randint(-25, 25)
            d.line([x0, y0, x1, y1], fill=(225, 225, 225), width=r.randint(1, 2))
    elif label == "cracked_glass":
        img = Image.new("RGB", (S, S), (70, 100, 120))
        d = ImageDraw.Draw(img)
        cx, cy = r.randint(40, 88), r.randint(40, 88)
        for _ in range(r.randint(8, 14)):
            a = r.uniform(0, 2 * math.pi)
            x, y = cx, cy
            for _ in range(5):
                a += r.uniform(-0.5, 0.5)
                nx, ny = x + math.cos(a) * 14, y + math.sin(a) * 14
                d.line([x, y, nx, ny], fill=(235, 240, 245), width=1)
                x, y = nx, ny
    return _noise(img, r, 14)


def road(label: str, r: random.Random) -> Image.Image:
    night = label in ("rain_night", "clear_night")
    sky = (8, 10, 22) if night else (150, 180, 210)
    img = Image.new("RGB", (S, S), sky)
    d = ImageDraw.Draw(img)
    d.polygon([(0, S), (S, S), (S // 2 + 8, S // 2), (S // 2 - 8, S // 2)], fill=(30, 30, 34) if night else (90, 90, 95))
    d.rectangle([0, S // 2 + 2, S, S // 2 + 6], fill=(12, 25, 12) if night else (60, 120, 60))
    for i in range(4):
        y = S // 2 + 10 + i * 16
        d.line([S // 2, y, S // 2, y + 7], fill=(200, 190, 90), width=1 + i // 2)
    if night:
        for x in (S // 2 - 30, S // 2 + 30):  # headlight glow
            d.ellipse([x - 10, S - 30, x + 10, S - 10], fill=(110, 110, 80))
    if label == "rain_night":
        for _ in range(260):
            x, y = r.randrange(S), r.randrange(S)
            d.line([x, y, x - 2, y + 6], fill=(120, 130, 150), width=1)
        img = img.filter(ImageFilter.GaussianBlur(0.8))
    return _noise(img, r, 10)


def shelf(label: str, r: random.Random) -> Image.Image:
    img = Image.new("RGB", (S, S), (210, 205, 195))
    d = ImageDraw.Draw(img)
    for row in range(3):
        y = 12 + row * 40
        d.rectangle([4, y + 30, S - 4, y + 34], fill=(120, 90, 60))
        fill_p = 0.9 if label == "shelf_stocked" else 0.15
        x = 8
        while x < S - 14:
            if r.random() < fill_p:
                c = r.choice([(200, 40, 40), (40, 120, 200), (240, 200, 40), (60, 170, 80), (120, 60, 160)])
                d.rectangle([x, y + r.randint(4, 12), x + 10, y + 30], fill=c)
            x += 13
    return _noise(img, r, 12)


def ir_occupancy(label: str, r: random.Random) -> Image.Image:
    """Anonymous thermal-style occupancy grid (8x8 upscaled) — no identifiable imagery."""
    grid = [[r.uniform(0.15, 0.3) for _ in range(8)] for _ in range(8)]
    n = {"empty": 0, "occupied_1": 1, "occupied_many": r.randint(3, 5)}[label]
    for _ in range(n):
        cx, cy = r.randint(1, 6), r.randint(1, 6)
        for y in range(8):
            for x in range(8):
                grid[y][x] += 0.85 * math.exp(-((x - cx) ** 2 + (y - cy) ** 2) / 1.6)
    img = Image.new("RGB", (8, 8))
    for y in range(8):
        for x in range(8):
            v = min(1.0, grid[y][x])
            img.putpixel((x, y), (int(255 * v), int(120 * v * v), int(255 * (1 - v) * 0.7)))
    return img.resize((S, S), Image.BICUBIC)


GENERATORS = {"leaf": leaf, "damage": damage, "road": road, "shelf": shelf, "ir": ir_occupancy}


def generate(kind: str, label: str, seed: int) -> bytes:
    return _jpeg(GENERATORS[kind](label, random.Random(seed)))


def sim_frame(t: float, servo_deg: float, distance_cm: float, ir: bool, tag: str | None) -> bytes:
    """A frame for the simulated ESP32-CAM: a warehouse shelf seen at the current servo angle."""
    W, H = 480, 320
    img = Image.new("RGB", (W, H), (28, 30, 34))
    d = ImageDraw.Draw(img)
    pan = int((servo_deg - 90) * 3)
    rr = random.Random(7)
    for row in range(4):
        y = 40 + row * 68
        d.rectangle([0, y + 52, W, y + 58], fill=(90, 70, 50))
        for i in range(-10, 40):
            x = i * 28 - pan
            if rr.random() < 0.8 and -30 < x < W:
                c = rr.choice([(180, 50, 50), (50, 110, 180), (220, 180, 50), (60, 150, 80)])
                d.rectangle([x, y + 14, x + 20, y + 52], fill=c)
    if ir:
        d.rectangle([W // 2 - 40, 60, W // 2 + 40, 300], outline=(255, 120, 40), width=2)
        d.text((W // 2 - 36, 64), "IR: presence", fill=(255, 140, 60))
    d.rectangle([0, 0, W, 22], fill=(0, 0, 0))
    ts = time.strftime("%H:%M:%S", time.localtime(t))
    d.text((8, 5), f"SIMULATED ESP32-CAM  {ts}  servo {servo_deg:.0f}°  dist {distance_cm:.0f}cm" + (f"  RFID {tag}" if tag else ""), fill=(200, 210, 220))
    for _ in range(600):
        x, y = random.randrange(W), random.randrange(H)
        v = random.randint(0, 40)
        img.putpixel((x, y), (v, v, v))
    b = io.BytesIO()
    img.save(b, "JPEG", quality=70)
    return b.getvalue()
