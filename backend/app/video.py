"""Short video clips as samples.

A video sample keeps the clip itself as its signed, encrypted media (also stored on 0G) plus a
keyframe JPEG whose SHA-256 is signed in the same manifest. Quality, privacy, duplicate checks,
previews and training run on the keyframe, so the rest of the pipeline is unchanged.

Encoding is WebM/VP8 (plays in every browser); OpenCV's bundled FFmpeg writes and reads it.
"""
from __future__ import annotations

import os
import tempfile

import numpy as np

MAX_VIDEO_BYTES = 25 * 1024 * 1024
WEBM_MAGIC = b"\x1a\x45\xdf\xa3"  # EBML header (WebM / Matroska)


def is_supported(data: bytes) -> str | None:
    """Return the MIME type for a clip we accept, else None."""
    if data[:4] == WEBM_MAGIC:
        return "video/webm"
    if data[4:8] == b"ftyp":
        return "video/mp4"
    return None


def frames_to_webm(jpegs: list[bytes], fps: float) -> bytes:
    """Encode JPEG frames (all the same size) into a WebM/VP8 clip."""
    import cv2

    frames = [cv2.imdecode(np.frombuffer(j, np.uint8), cv2.IMREAD_COLOR) for j in jpegs]
    frames = [f for f in frames if f is not None]
    if not frames:
        raise ValueError("no decodable frames")
    h, w = frames[0].shape[:2]
    fd, path = tempfile.mkstemp(suffix=".webm")
    os.close(fd)
    try:
        out = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"VP80"), max(1.0, min(30.0, fps)), (w, h))
        if not out.isOpened():
            raise RuntimeError("WebM encoder unavailable in this OpenCV build")
        for f in frames:
            out.write(f if f.shape[:2] == (h, w) else cv2.resize(f, (w, h)))
        out.release()
        with open(path, "rb") as fh:
            return fh.read()
    finally:
        os.unlink(path)


def keyframe_and_probe(data: bytes, suffix: str = ".webm") -> tuple[bytes | None, int]:
    """Decode a clip; return (middle frame as JPEG, frame count). (None, 0) if undecodable."""
    import cv2

    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        with open(path, "wb") as fh:
            fh.write(data)
        cap = cv2.VideoCapture(path)
        frames = []
        while len(frames) < 900:  # hard cap (~30 s at 30 fps)
            ok, f = cap.read()
            if not ok:
                break
            frames.append(f)
        cap.release()
        if not frames:
            return None, 0
        ok, buf = cv2.imencode(".jpg", frames[len(frames) // 2], [cv2.IMWRITE_JPEG_QUALITY, 90])
        return (buf.tobytes() if ok else None), len(frames)
    except Exception:
        return None, 0
    finally:
        os.unlink(path)
