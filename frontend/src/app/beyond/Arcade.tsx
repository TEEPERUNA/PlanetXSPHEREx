// Flight simulator: a small arcade game to fly while a long search downloads.
// Your ship (from the hangar) shoots asteroids and drones; shield cells repair the hull.
// The real download progress runs along the top, and the game ends when the data arrives.
import { useEffect, useRef, useState } from "react";
import { describeStage } from "../../viewer/lib/stage";
import { drawShip, type ShipDesign } from "./ships";

export interface LinkProgress {
  stage: string;
  done: number;
  total: number;
}

interface Props {
  ship: ShipDesign;
  link: LinkProgress | null; // download progress while the ship is in warp
  dataReady: boolean; // the result arrived
  onExit: (score: number, duringWarp: boolean) => void;
  sfx?: { shoot: () => void; boom: () => void; hurt: () => void; pickup: () => void };
}

type Phase = "play" | "over" | "acquired";

interface Body {
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
  kind: "rock" | "drone" | "cell";
  hp: number;
  rot: number;
  vr: number;
  shape: number[]; // rock outline radii
}

interface Shot {
  x: number;
  y: number;
  vy: number;
}

interface Bit {
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number;
  color: string;
}

export function Arcade({ ship, link, dataReady, onExit, sfx }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [phase, setPhase] = useState<Phase>("play");
  const [score, setScore] = useState(0);
  const [run, setRun] = useState(0); // restart counter
  const linkRef = useRef(link);
  linkRef.current = link;
  const sfxRef = useRef(sfx);
  sfxRef.current = sfx;
  const scoreRef = useRef(0);
  const warpAtStart = useRef(link !== null);

  // Data arrived: stop the game and celebrate.
  useEffect(() => {
    if (dataReady && phase === "play") setPhase("acquired");
  }, [dataReady, phase]);

  useEffect(() => {
    if (phase !== "acquired") return;
    const t = setTimeout(() => onExit(scoreRef.current, warpAtStart.current), 1800);
    return () => clearTimeout(t);
  }, [phase, onExit]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onExit(scoreRef.current, warpAtStart.current);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onExit]);

  // The game loop. Restarts when `run` changes.
  useEffect(() => {
    if (phase !== "play") return;
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    let w = 0;
    let h = 0;
    function resize() {
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      w = window.innerWidth;
      h = window.innerHeight;
      canvas!.width = Math.round(w * dpr);
      canvas!.height = Math.round(h * dpr);
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    resize();

    const maxHull = 2 + ship.stats.hull;
    const speed = 0.12 + ship.stats.speed * 0.035; // how fast the ship follows the pointer
    const cooldownMs = 330 - ship.stats.fireRate * 45;
    const player = { x: w / 2, y: h * 0.82, tx: w / 2, ty: h * 0.82, hull: maxHull, hurtUntil: 0 };
    const keys = new Set<string>();
    let firing = false;
    let lastShot = 0;
    let points = 0;
    let started = performance.now();
    let nextSpawn = started + 600;
    let last = started;
    let raf = 0;
    const bodies: Body[] = [];
    const shots: Shot[] = [];
    const bits: Bit[] = [];
    const stars = Array.from({ length: 140 }, () => ({ x: Math.random(), y: Math.random(), s: Math.random() }));
    scoreRef.current = 0;
    setScore(0);

    function boom(x: number, y: number, color: string, n = 24) {
      for (let i = 0; i < n; i++) {
        const a = Math.random() * Math.PI * 2;
        const v = 1 + Math.random() * 5;
        bits.push({ x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, life: 1, color });
      }
    }

    function spawn(t: number) {
      const age = (t - started) / 1000;
      const roll = Math.random();
      if (roll < 0.06) {
        bodies.push({ x: 40 + Math.random() * (w - 80), y: -30, vx: 0, vy: 1.4, r: 12, kind: "cell", hp: 1, rot: 0, vr: 0.03, shape: [] });
      } else if (age > 15 && roll < 0.3) {
        bodies.push({ x: Math.random() * w, y: -30, vx: (Math.random() - 0.5) * 3, vy: 1.6 + Math.random(), r: 16, kind: "drone", hp: 2, rot: 0, vr: 0, shape: [] });
      } else {
        const r = 14 + Math.random() * 26;
        bodies.push({
          x: Math.random() * w,
          y: -r,
          vx: (Math.random() - 0.5) * 1.2,
          vy: 1.2 + Math.random() * 1.8 + age * 0.03,
          r,
          kind: "rock",
          hp: r > 28 ? 3 : 1,
          rot: Math.random() * 6,
          vr: (Math.random() - 0.5) * 0.04,
          shape: Array.from({ length: 9 }, () => 0.75 + Math.random() * 0.35),
        });
      }
      nextSpawn = t + Math.max(220, 850 - age * 12);
    }

    function frame(t: number) {
      const f = Math.min(3, (t - last) / 16.7);
      last = t;

      // Move the player: keys, or follow the pointer.
      const k = 7 + ship.stats.speed * 1.4;
      if (keys.has("ArrowLeft") || keys.has("a")) player.tx -= k * f;
      if (keys.has("ArrowRight") || keys.has("d")) player.tx += k * f;
      if (keys.has("ArrowUp") || keys.has("w")) player.ty -= k * f;
      if (keys.has("ArrowDown") || keys.has("s")) player.ty += k * f;
      player.tx = Math.max(20, Math.min(w - 20, player.tx));
      player.ty = Math.max(h * 0.35, Math.min(h - 30, player.ty));
      player.x += (player.tx - player.x) * Math.min(1, speed * f);
      player.y += (player.ty - player.y) * Math.min(1, speed * f);

      // Shooting
      if ((firing || keys.has(" ")) && t - lastShot > cooldownMs) {
        lastShot = t;
        shots.push({ x: player.x - 6, y: player.y - 16, vy: -11 });
        shots.push({ x: player.x + 6, y: player.y - 16, vy: -11 });
        sfxRef.current?.shoot();
      }

      if (t > nextSpawn) spawn(t);

      // Background
      ctx!.fillStyle = "rgba(2,3,8,0.9)";
      ctx!.fillRect(0, 0, w, h);
      for (const s of stars) {
        s.y += (0.5 + s.s * 2.5) * f * 0.002;
        if (s.y > 1) s.y = 0;
        ctx!.fillStyle = `rgba(255,255,255,${0.2 + s.s * 0.6})`;
        ctx!.fillRect(s.x * w, s.y * h, 1 + s.s, 1 + s.s * 3);
      }

      // Shots
      ctx!.fillStyle = ship.accent;
      ctx!.shadowColor = ship.accent;
      ctx!.shadowBlur = 8;
      for (let i = shots.length - 1; i >= 0; i--) {
        const s = shots[i];
        s.y += s.vy * f;
        if (s.y < -20) {
          shots.splice(i, 1);
          continue;
        }
        ctx!.fillRect(s.x - 1.5, s.y - 8, 3, 12);
      }
      ctx!.shadowBlur = 0;

      // Asteroids, drones, shield cells
      for (let i = bodies.length - 1; i >= 0; i--) {
        const b = bodies[i];
        b.x += b.vx * f;
        b.y += b.vy * f;
        b.rot += b.vr * f;
        if (b.kind === "drone") b.vx += Math.sin(t * 0.004 + i) * 0.08 * f;
        if (b.y > h + 60 || b.x < -80 || b.x > w + 80) {
          bodies.splice(i, 1);
          continue;
        }

        // Shot hits
        let gone = false;
        for (let j = shots.length - 1; j >= 0 && b.kind !== "cell"; j--) {
          const s = shots[j];
          if (Math.hypot(s.x - b.x, s.y - b.y) < b.r) {
            shots.splice(j, 1);
            b.hp -= 1;
            if (b.hp <= 0) {
              points += b.kind === "drone" ? 50 : b.r > 28 ? 25 : 10;
              boom(b.x, b.y, b.kind === "drone" ? "248,113,113" : "203,213,225", b.kind === "drone" ? 30 : 18);
              sfxRef.current?.boom();
              bodies.splice(i, 1);
              gone = true;
              break;
            }
          }
        }
        if (gone) continue;

        // Ship collisions
        if (Math.hypot(player.x - b.x, player.y - b.y) < b.r + 12) {
          bodies.splice(i, 1);
          if (b.kind === "cell") {
            player.hull = Math.min(maxHull, player.hull + 1);
            points += 15;
            boom(b.x, b.y, "74,222,128", 16);
            sfxRef.current?.pickup();
          } else if (t > player.hurtUntil) {
            player.hull -= 1;
            player.hurtUntil = t + 1200;
            boom(player.x, player.y, "251,191,36", 30);
            sfxRef.current?.hurt();
          }
          continue;
        }

        // Draw
        ctx!.save();
        ctx!.translate(b.x, b.y);
        ctx!.rotate(b.rot);
        if (b.kind === "rock") {
          ctx!.beginPath();
          b.shape.forEach((k2, n) => {
            const a = (n / b.shape.length) * Math.PI * 2;
            const px = Math.cos(a) * b.r * k2;
            const py = Math.sin(a) * b.r * k2;
            if (n === 0) ctx!.moveTo(px, py);
            else ctx!.lineTo(px, py);
          });
          ctx!.closePath();
          ctx!.fillStyle = "#334155";
          ctx!.fill();
          ctx!.strokeStyle = "#94a3b8";
          ctx!.lineWidth = 1.5;
          ctx!.stroke();
        } else if (b.kind === "drone") {
          ctx!.fillStyle = "#7f1d1d";
          ctx!.strokeStyle = "#f87171";
          ctx!.lineWidth = 2;
          ctx!.shadowColor = "#f87171";
          ctx!.shadowBlur = 12;
          ctx!.beginPath();
          ctx!.moveTo(0, 14);
          ctx!.lineTo(14, -6);
          ctx!.lineTo(0, -2);
          ctx!.lineTo(-14, -6);
          ctx!.closePath();
          ctx!.fill();
          ctx!.stroke();
        } else {
          ctx!.strokeStyle = "#4ade80";
          ctx!.lineWidth = 2;
          ctx!.shadowColor = "#4ade80";
          ctx!.shadowBlur = 14;
          ctx!.beginPath();
          ctx!.arc(0, 0, b.r * (0.8 + 0.2 * Math.sin(t * 0.01)), 0, Math.PI * 2);
          ctx!.stroke();
          ctx!.fillStyle = "#4ade80";
          ctx!.fillRect(-2, -7, 4, 14);
          ctx!.fillRect(-7, -2, 14, 4);
        }
        ctx!.restore();
      }

      // Explosions
      for (let i = bits.length - 1; i >= 0; i--) {
        const p = bits[i];
        p.x += p.vx * f;
        p.y += p.vy * f;
        p.vx *= 0.96;
        p.vy *= 0.96;
        p.life -= 0.02 * f;
        if (p.life <= 0) {
          bits.splice(i, 1);
          continue;
        }
        ctx!.fillStyle = `rgba(${p.color},${p.life})`;
        ctx!.fillRect(p.x - 1.5, p.y - 1.5, 3, 3);
      }

      // Player (blinks while invulnerable)
      if (t > player.hurtUntil || Math.floor(t / 90) % 2 === 0) {
        const tilt = Math.max(-0.35, Math.min(0.35, (player.tx - player.x) * 0.01));
        drawShip(ctx!, ship, player.x, player.y, 1.4, tilt, firing ? 1.4 : 1, t);
      }

      // HUD
      ctx!.textAlign = "left";
      ctx!.font = "700 16px Orbitron, sans-serif";
      ctx!.fillStyle = "#fff";
      ctx!.fillText(`SCORE ${points}`, 24, 40);
      ctx!.font = "600 12px 'JetBrains Mono', monospace";
      ctx!.fillStyle = "#94a3b8";
      ctx!.fillText(`${ship.name.toUpperCase()} · HULL`, 24, 64);
      for (let i = 0; i < maxHull; i++) {
        ctx!.fillStyle = i < player.hull ? ship.accent : "rgba(255,255,255,0.12)";
        ctx!.fillRect(24 + i * 18, 72, 14, 8);
      }
      const lp = linkRef.current;
      if (lp) {
        const bw = Math.min(420, w - 48);
        const x0 = (w - bw) / 2;
        const frac = lp.total > 0 ? Math.min(1, lp.done / lp.total) : (Math.sin(t * 0.003) + 1) / 2;
        ctx!.fillStyle = "rgba(255,255,255,0.1)";
        ctx!.fillRect(x0, 22, bw, 6);
        ctx!.fillStyle = "#22d3ee";
        ctx!.fillRect(lp.total > 0 ? x0 : x0 + frac * bw * 0.8, 22, lp.total > 0 ? bw * frac : bw * 0.2, 6);
        ctx!.textAlign = "center";
        ctx!.fillStyle = "#a5f3fc";
        ctx!.fillText(
          `DATA LINK · ${describeStage(lp.stage).label}${lp.total > 0 ? ` ${lp.done}/${lp.total}` : "…"}`,
          w / 2,
          46,
        );
      }

      if (points !== scoreRef.current) {
        scoreRef.current = points;
        setScore(points);
      }
      if (player.hull <= 0) {
        boom(player.x, player.y, "251,191,36", 60);
        setPhase("over");
        return;
      }
      raf = requestAnimationFrame(frame);
    }

    const onMove = (e: PointerEvent) => {
      player.tx = e.clientX;
      player.ty = e.clientY;
    };
    const onDown = (e: PointerEvent) => {
      if ((e.target as Element).closest(".arcade__ui")) return;
      firing = true;
    };
    const onUp = () => {
      firing = false;
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", " "].includes(e.key)) e.preventDefault();
      keys.add(e.key.length === 1 ? e.key.toLowerCase() : e.key);
    };
    const onKeyUp = (e: KeyboardEvent) => keys.delete(e.key.length === 1 ? e.key.toLowerCase() : e.key);

    window.addEventListener("resize", resize);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerdown", onDown);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    started = performance.now();
    raf = requestAnimationFrame(frame);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerdown", onDown);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
    };
  }, [phase, run, ship]);

  return (
    <div className="arcade" role="dialog" aria-label="Flight simulator">
      <canvas ref={canvasRef} className="arcade__canvas" />
      <div className="arcade__ui">
        <button type="button" onClick={() => onExit(scoreRef.current, warpAtStart.current)}>
          Back to bridge (Esc)
        </button>
      </div>
      {phase === "play" && (
        <p className="arcade__help">Move: mouse or arrows · Fire: hold mouse button or Space · Green cells repair the hull</p>
      )}
      {phase === "over" && (
        <div className="arcade__panel arcade__ui">
          <p className="arcade__title is-bad">Ship destroyed</p>
          <p className="arcade__score">{score} points</p>
          <div className="arcade__actions">
            <button type="button" className="primary" onClick={() => { setPhase("play"); setRun((r) => r + 1); }}>
              Fly again
            </button>
            <button type="button" onClick={() => onExit(scoreRef.current, warpAtStart.current)}>
              Back to bridge
            </button>
          </div>
        </div>
      )}
      {phase === "acquired" && (
        <div className="arcade__panel">
          <p className="arcade__title">Data acquired</p>
          <p className="arcade__score">{score} points · returning to the bridge</p>
        </div>
      )}
    </div>
  );
}
