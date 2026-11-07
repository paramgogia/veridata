"use client";
import { useEffect, useRef, useState } from "react";

/**
 * Hero animation: a sensor frame is read out row by row; each pair of rows becomes a hashed leaf,
 * leaves fold into a Merkle tree, the root lights up and lands as a block on the chain. Then a new
 * frame starts. Canvas-drawn, colours from the theme tokens, paused off-screen, static when the
 * viewer prefers reduced motion.
 */
const COLS = 22;
const ROWS = 16; // 2 rows per leaf -> 8 leaves
const LEAVES = ROWS / 2;
const SCAN_S = 3.4; // readout time for the whole frame
const FLY_S = 0.75; // row hash travel time
const JOIN_DELAY = 0.22;
const JOIN_S = 0.32;
const HOLD_S = 1.6; // root visible before the next frame
const FADE_S = 0.5;

type RGB = [number, number, number];
const rgba = (c: RGB, a: number) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
const clamp = (v: number, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const ease = (t: number) => 1 - Math.pow(1 - clamp(t), 3);

function mulberry(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const hex = (rnd: () => number, n: number) => Array.from({ length: n }, () => "0123456789abcdef"[Math.floor(rnd() * 16)]).join("");

function token(name: string, fallback: RGB): RGB {
  if (typeof window === "undefined") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim().split(/\s+/).map(Number);
  return v.length === 3 && v.every((x) => !Number.isNaN(x)) ? (v as RGB) : fallback;
}

type Cycle = {
  seed: number;
  start: number;
  blobs: { x: number; y: number; r: number; vx: number; vy: number; k: number }[];
  leafHash: string[];
  root: string;
  packets: { row: number; t0: number; done: boolean }[];
  spawned: number;
  hits: number[];
  done: number[][]; // [level][node] -> time done (Infinity = not yet)
  rootAt: number;
};

function newCycle(seed: number, start: number): Cycle {
  const rnd = mulberry(seed);
  const blobs = Array.from({ length: 3 }, () => ({
    x: rnd(), y: rnd(), r: 0.18 + rnd() * 0.22, vx: (rnd() - 0.5) * 0.06, vy: (rnd() - 0.5) * 0.06, k: 0.6 + rnd() * 0.5,
  }));
  return {
    seed, start, blobs,
    leafHash: Array.from({ length: LEAVES }, () => hex(rnd, 6)),
    root: hex(rnd, 8),
    packets: [], spawned: 0,
    hits: Array(LEAVES).fill(0),
    done: [Array(8).fill(Infinity), Array(4).fill(Infinity), Array(2).fill(Infinity), [Infinity]],
    rootAt: Infinity,
  };
}

export function CaptureFlow({ className }: { className?: string }) {
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [readout, setReadout] = useState({ frame: 142, root: "6d1fa903", block: 7814203 });

  useEffect(() => {
    const cv = canvas.current!;
    const box = wrap.current!;
    const ctx = cv.getContext("2d")!;
    const C = {
      fg: token("--fg", [232, 234, 237]), muted: token("--muted", [140, 147, 158]), faint: token("--faint", [92, 99, 110]),
      line: token("--line", [34, 38, 44]), accent: token("--accent", [140, 156, 255]), ok: token("--ok", [61, 214, 140]),
      chain: token("--chain", [120, 200, 255]),
    };
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let W = 0, H = 0, dpr = 1;
    let raf = 0, running = true, visible = true;
    let frameNo = 142, blockNo = 7814203;
    let cyc = newCycle(frameNo, 0);
    let chainShift = 0; // animates the newest block sliding in
    let lastRootPulse = -10;
    const t0 = performance.now();

    const resize = () => {
      const r = box.getBoundingClientRect();
      dpr = Math.min(2, window.devicePixelRatio || 1);
      W = Math.max(280, r.width);
      H = Math.max(240, r.height);
      cv.width = Math.round(W * dpr);
      cv.height = Math.round(H * dpr);
      cv.style.width = `${W}px`;
      cv.style.height = `${H}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (reduced) draw(1e6);
    };

    // geometry derived from size
    const geo = () => {
      const pad = 18;
      const chainW = Math.max(46, W * 0.09);
      const frameW = Math.min(W * 0.4, (H - pad * 2 - 18) * (COLS / ROWS));
      const cw = Math.floor(frameW / COLS);
      const ch = Math.floor(Math.min((H - pad * 2 - 30) / ROWS, cw * 1.5));  // slightly tall cells fill the panel
      const fw = cw * COLS, fh = ch * ROWS;
      const fx = pad, fy = Math.round((H - fh) / 2) + 6;
      const tx0 = fx + fw + Math.max(36, W * 0.08);
      const tx1 = W - pad - chainW - Math.max(26, W * 0.05);
      const levelX = [0, 1, 2, 3].map((k) => tx0 + (k * (tx1 - tx0)) / 3);
      const leafY = Array.from({ length: LEAVES }, (_, i) => fy + (i * 2 + 1) * ch);
      const nodeY: number[][] = [leafY];
      for (let k = 1; k < 4; k++) nodeY.push(nodeY[k - 1].filter((_, j) => j % 2 === 0).map((_, j) => (nodeY[k - 1][j * 2] + nodeY[k - 1][j * 2 + 1]) / 2));
      const cx = W - pad - chainW / 2;
      const labels = levelX[1] - levelX[0] > 52;  // leaf hashes only where they fit
      return { pad, cw, ch, fw, fh, fx, fy, levelX, nodeY, cx, chainW, labels };
    };

    const brightness = (c: Cycle, x: number, y: number, t: number) => {
      let v = 0.08;
      for (const b of c.blobs) {
        const bx = b.x + Math.sin(t * 0.7 + b.k * 3) * 0.08 + b.vx * t;
        const by = b.y + Math.cos(t * 0.6 + b.k * 2) * 0.08 + b.vy * t;
        const d = ((x - bx) ** 2 + (y - by) ** 2) / (b.r * b.r);
        v += b.k * Math.exp(-d * 1.4);
      }
      v += 0.06 * Math.sin(x * 19 + t * 1.7) * Math.cos(y * 13 - t);
      return clamp(v);
    };

    const step = (now: number) => {
      const c = cyc;
      const t = now - c.start;
      // spawn one packet per finished row
      const rowsRead = Math.min(ROWS, Math.floor((t / SCAN_S) * ROWS));
      while (c.spawned < rowsRead) c.packets.push({ row: c.spawned++, t0: c.start + (c.spawned / ROWS) * SCAN_S, done: false });
      for (const p of c.packets) {
        if (!p.done && now - p.t0 >= FLY_S) {
          p.done = true;
          const leaf = Math.floor(p.row / 2);
          c.hits[leaf]++;
          if (c.hits[leaf] === 2) c.done[0][leaf] = now;
        }
      }
      for (let k = 1; k < 4; k++) {
        for (let j = 0; j < c.done[k].length; j++) {
          const a = c.done[k - 1][j * 2], b = c.done[k - 1][j * 2 + 1];
          if (c.done[k][j] === Infinity && a !== Infinity && b !== Infinity) c.done[k][j] = Math.max(a, b) + JOIN_DELAY + JOIN_S;
        }
      }
      if (c.rootAt === Infinity && c.done[3][0] <= now) {
        c.rootAt = c.done[3][0];
        lastRootPulse = now;
        blockNo += 1;
        chainShift = 1;
        setReadout({ frame: frameNo, root: c.root, block: blockNo });
      }
      if (c.rootAt !== Infinity && now - c.rootAt > HOLD_S + FADE_S) {
        frameNo += 1;
        cyc = newCycle(frameNo * 7919, now);
      }
      chainShift = Math.max(0, chainShift - 0.035);
    };

    function draw(now: number) {
      const g = geo();
      const c = cyc;
      const t = reduced ? 99 : now - c.start;
      const fade = c.rootAt === Infinity ? 1 : 1 - clamp((now - c.rootAt - HOLD_S) / FADE_S);
      ctx.clearRect(0, 0, W, H);
      ctx.font = "500 10px 'JetBrains Mono', Consolas, monospace";
      ctx.textBaseline = "middle";

      // ---- sensor frame ----
      const scanRow = reduced ? ROWS : clamp(t / SCAN_S, 0, 1) * ROWS;
      ctx.fillStyle = rgba(C.faint, 0.9);
      ctx.fillText(`ESP32-CAM · frame ${String(frameNo).padStart(4, "0")}`, g.fx, g.fy - 14);
      const gap = Math.max(1, Math.round(Math.min(g.cw, g.ch) * 0.16));
      for (let r = 0; r < ROWS; r++) {
        const read = r < Math.floor(scanRow);
        for (let col = 0; col < COLS; col++) {
          const v = brightness(c, col / COLS, r / ROWS, reduced ? 2 : now * 0.35);
          const base = read ? C.ok : C.fg;
          const a = (read ? 0.18 + v * 0.55 : 0.05 + v * 0.6) * (read ? fade * 0.85 + 0.15 : 1);
          ctx.fillStyle = rgba(base, a);
          ctx.fillRect(g.fx + col * g.cw + gap / 2, g.fy + r * g.ch + gap / 2, g.cw - gap, g.ch - gap);
        }
      }
      if (!reduced && scanRow < ROWS) {
        const y = g.fy + scanRow * g.ch;
        const grad = ctx.createLinearGradient(0, y - g.ch * 3, 0, y);
        grad.addColorStop(0, rgba(C.accent, 0));
        grad.addColorStop(1, rgba(C.accent, 0.28));
        ctx.fillStyle = grad;
        ctx.fillRect(g.fx, y - g.ch * 3, g.fw, g.ch * 3);
        ctx.fillStyle = rgba(C.accent, 0.95);
        ctx.fillRect(g.fx - 3, y - 1, g.fw + 6, 2);
      }
      ctx.strokeStyle = rgba(C.line, 1);
      ctx.lineWidth = 1;
      ctx.strokeRect(g.fx - 4.5, g.fy - 4.5, g.fw + 9, g.fh + 9);

      // ---- tree edges ----
      const node = (k: number, j: number) => ({ x: g.levelX[k], y: g.nodeY[k][j] });
      const doneAt = (k: number, j: number) => (reduced ? -1 : c.done[k][j]);
      for (let k = 1; k < 4; k++) {
        for (let j = 0; j < g.nodeY[k].length; j++) {
          const p = node(k, j);
          for (const ch of [j * 2, j * 2 + 1]) {
            const q = node(k - 1, ch);
            const parentDone = doneAt(k, j);
            const startJoin = parentDone - JOIN_S;
            const prog = reduced ? 1 : parentDone === Infinity ? 0 : ease((now - startJoin) / JOIN_S);
            const mx = (q.x + p.x) / 2;
            // base (unlit) edge
            ctx.strokeStyle = rgba(C.line, 1);
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(q.x, q.y);
            ctx.bezierCurveTo(mx, q.y, mx, p.y, p.x, p.y);
            ctx.stroke();
            if (prog > 0) {
              ctx.strokeStyle = rgba(k === 3 ? C.chain : C.accent, 0.85 * fade + 0.1);
              ctx.lineWidth = 1.5;
              ctx.setLineDash([400]);
              ctx.lineDashOffset = 400 * (1 - prog);
              ctx.beginPath();
              ctx.moveTo(q.x, q.y);
              ctx.bezierCurveTo(mx, q.y, mx, p.y, p.x, p.y);
              ctx.stroke();
              ctx.setLineDash([]);
            }
          }
        }
      }

      // ---- packets: row hash flying to its leaf ----
      if (!reduced) {
        for (const p of c.packets) {
          const u = (now - p.t0) / FLY_S;
          if (u < 0 || u > 1) continue;
          const sx = g.fx + g.fw + 6, sy = g.fy + (p.row + 0.5) * g.ch;
          const ex = g.levelX[0] - 7, ey = g.nodeY[0][Math.floor(p.row / 2)];
          const mx = (sx + ex) / 2;
          const at = (s: number) => {
            const e = ease(s);
            const x = (1 - e) ** 2 * sx + 2 * (1 - e) * e * mx + e * e * ex;
            const y = (1 - e) ** 2 * sy + 2 * (1 - e) * e * sy + e * e * ey;
            return [x, y];
          };
          for (let k = 6; k >= 0; k--) {
            const [x, y] = at(u - k * 0.035);
            ctx.fillStyle = rgba(C.ok, (1 - k / 7) * 0.8);
            ctx.beginPath();
            ctx.arc(x, y, 2.2 - k * 0.22, 0, Math.PI * 2);
            ctx.fill();
          }
        }
      }

      // ---- nodes ----
      for (let k = 0; k < 4; k++) {
        for (let j = 0; j < g.nodeY[k].length; j++) {
          const { x, y } = node(k, j);
          const d = doneAt(k, j);
          const lit = d <= now || reduced;
          const flash = lit && !reduced ? clamp(1 - (now - d) / 0.6) : 0;
          const col = k === 3 ? C.chain : k === 0 ? C.ok : C.accent;
          const r = k === 3 ? 7 : 4.5;
          if (flash > 0) {
            ctx.fillStyle = rgba(col, 0.25 * flash);
            ctx.beginPath();
            ctx.arc(x, y, r + 10 * (1 - flash) + 4, 0, Math.PI * 2);
            ctx.fill();
          }
          ctx.fillStyle = lit ? rgba(col, 0.9 * fade + 0.1) : rgba(C.line, 1);
          ctx.strokeStyle = lit ? rgba(col, 1) : rgba(C.faint, 0.6);
          ctx.lineWidth = 1;
          ctx.beginPath();
          if (k === 0) ctx.rect(x - r, y - r, r * 2, r * 2);
          else ctx.arc(x, y, r, 0, Math.PI * 2);
          ctx.fill();
          ctx.stroke();
          if (k === 0 && g.labels) {
            const label = lit ? c.leafHash[j] : c.hits[j] > 0 && !reduced ? hex(Math.random, 6) : "······";
            ctx.fillStyle = lit ? rgba(C.muted, fade * 0.9 + 0.1) : rgba(C.faint, 0.7);
            ctx.textAlign = "left";
            ctx.fillText(label, x + 10, y);
          }
        }
      }
      // root label + pulse ring
      const root = node(3, 0);
      const rootLit = reduced || c.rootAt <= now;
      ctx.textAlign = "center";
      ctx.fillStyle = rgba(rootLit ? C.chain : C.faint, rootLit ? fade * 0.9 + 0.1 : 0.7);
      ctx.fillText(rootLit ? `root 0x${c.root.slice(0, 6)}…` : "merkle root", root.x, root.y - 20);
      if (!reduced) {
        const pr = (now - lastRootPulse) / 1.1;
        if (pr >= 0 && pr < 1) {
          ctx.strokeStyle = rgba(C.chain, (1 - pr) * 0.7);
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.arc(root.x, root.y, 8 + pr * 34, 0, Math.PI * 2);
          ctx.stroke();
        }
      }

      // ---- chain: blocks stacking, newest slides in ----
      const bw = Math.min(g.chainW - 8, 40), bh = Math.min(22, g.fh / 6.5);
      const gapB = 8;
      ctx.fillStyle = rgba(C.faint, 0.9);
      ctx.textAlign = "center";
      ctx.fillText("SEPOLIA", g.cx, g.fy - 14);
      const midY = root.y;
      for (let i = -2; i <= 2; i++) {
        const y = midY + i * (bh + gapB) - chainShift * (bh + gapB);
        if (y < g.fy - 6 || y > g.fy + g.fh + 6 - bh) continue;
        const newest = i === 0;
        ctx.fillStyle = newest && rootLit ? rgba(C.chain, 0.16) : rgba(C.line, 0.6);
        ctx.strokeStyle = newest && rootLit ? rgba(C.chain, 0.9) : rgba(C.line, 1);
        ctx.lineWidth = 1;
        ctx.fillRect(g.cx - bw / 2, y - bh / 2, bw, bh);
        ctx.strokeRect(g.cx - bw / 2 + 0.5, y - bh / 2 + 0.5, bw - 1, bh - 1);
        ctx.fillStyle = newest && rootLit ? rgba(C.chain, 1) : rgba(C.faint, 0.8);
        ctx.font = "500 8px 'JetBrains Mono', Consolas, monospace";
        ctx.fillText(String((blockNo + i) % 10000).padStart(4, "0"), g.cx, y);
        ctx.font = "500 10px 'JetBrains Mono', Consolas, monospace";
      }
      // root -> chain link
      if (rootLit) {
        const prog = reduced ? 1 : ease((now - c.rootAt) / 0.45);
        ctx.strokeStyle = rgba(C.chain, 0.8 * fade + 0.1);
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(root.x + 8, root.y);
        ctx.lineTo(root.x + 8 + (g.cx - bw / 2 - root.x - 8) * prog, root.y);
        ctx.stroke();
      }
    }

    const loop = () => {
      if (!running) return;
      const now = (performance.now() - t0) / 1000;
      if (visible) {
        step(now);
        draw(now);
      }
      raf = requestAnimationFrame(loop);
    };

    const ro = new ResizeObserver(resize);
    ro.observe(box);
    resize();
    let io: IntersectionObserver | null = null;
    if (reduced) {
      draw(1e6);
    } else {
      io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; }, { threshold: 0.05 });
      io.observe(box);
      raf = requestAnimationFrame(loop);
    }
    return () => {
      running = false;
      cancelAnimationFrame(raf);
      ro.disconnect();
      io?.disconnect();
    };
  }, []);

  return (
    <div className={className}>
      <div className="overflow-hidden rounded-2xl border border-line bg-panel">
        <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
          <span className="font-mono text-[11px] text-faint">capture → sign → merkle root → chain</span>
          <span className="flex items-center gap-1.5 font-mono text-[11px] text-ok">
            <span className="h-1.5 w-1.5 animate-pulseDot rounded-full bg-ok" /> live
          </span>
        </div>
        <div ref={wrap} className="relative h-[300px] w-full sm:h-[340px]" aria-hidden>
          <canvas ref={canvas} className="absolute inset-0" />
        </div>
        <div className="grid grid-cols-3 border-t border-line font-mono text-[10.5px] text-muted">
          <div className="border-r border-line px-4 py-2.5"><div className="text-faint">frame</div>#{String(readout.frame).padStart(4, "0")}</div>
          <div className="border-r border-line px-4 py-2.5"><div className="text-faint">root</div>0x{readout.root.slice(0, 8)}</div>
          <div className="px-4 py-2.5"><div className="text-faint">block</div>{readout.block.toLocaleString("en-US")}</div>
        </div>
      </div>
      <p className="sr-only">
        Animation: a camera frame is read out row by row, each row is hashed into a Merkle tree, and the root is anchored as a block on Ethereum Sepolia.
      </p>
    </div>
  );
}
