// Animated star field behind the whole page (demo/beyond branch).
// - Three depths of stars drift towards the viewer and twinkle; the mouse adds parallax.
// - `warp`: stars stretch into streaks (light-speed jump) while a search is loading.
// - `burst`: each increase fires a burst of sparks from the centre (a result arrived).
// - Reduced motion: one still frame, no animation.
import { useEffect, useRef } from "react";
import { SHIPS, TRAFFIC, drawShip, type ShipDesign } from "./ships";

interface Props {
  warp: boolean;
  burst: number;
  onScan?: (name: string) => void; // a passing ship was clicked
  onHail?: (name: string) => void; // a passing ship came into view
}

interface Npc {
  name: string;
  design: ShipDesign;
  x: number;
  y: number;
  vx: number;
  vy: number;
  scale: number;
  born: number;
}

// Clicks on the UI never count as scanning a ship behind it.
const UI = "button,a,input,select,textarea,label,.card,.telemetry,.game-hud,.radar,.toast,.mission-log,.hangar,.arcade,.boot,.banner";

// Passing ships keep their shape but get a muted "civilian" livery.
const NPC_DESIGNS: ShipDesign[] = SHIPS.map((s) => ({ ...s, hull: "#475569", accent: "#94a3b8" }));

interface Star {
  x: number; // -1..1, scaled by the spread
  y: number;
  z: number; // depth: 1 = far, 0 = at the viewer
  twinkle: number; // twinkle speed
  hue: string;
}

interface Spark {
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number; // 1 -> 0
  hue: string;
}

interface Meteor {
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number;
}

const HUES = ["255,255,255", "255,255,255", "255,255,255", "165,243,252", "34,211,238", "253,230,138"];
const pick = <T,>(list: T[]) => list[Math.floor(Math.random() * list.length)];

function newStar(far = false): Star {
  return {
    x: Math.random() * 2 - 1,
    y: Math.random() * 2 - 1,
    z: far ? 1 : Math.random() * 0.95 + 0.05,
    twinkle: 1 + Math.random() * 3,
    hue: pick(HUES),
  };
}

export function Starfield({ warp, burst, onScan, onHail }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const warpRef = useRef(warp);
  const burstRef = useRef(0); // bursts waiting to be drawn
  const scanRef = useRef(onScan);
  const hailRef = useRef(onHail);
  scanRef.current = onScan;
  hailRef.current = onHail;

  useEffect(() => {
    warpRef.current = warp;
  }, [warp]);

  useEffect(() => {
    if (burst > 0) burstRef.current += 1;
  }, [burst]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let w = 0;
    let h = 0;
    let stars: Star[] = [];
    const sparks: Spark[] = [];
    const meteors: Meteor[] = [];
    const npcs: Npc[] = [];
    let nextNpc = performance.now() + 4000; // first ship after a few seconds
    let speed = 0.0007; // depth per frame
    const mouse = { x: 0, y: 0, tx: 0, ty: 0 };
    let raf = 0;
    let last = performance.now();

    function resize() {
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      w = window.innerWidth;
      h = window.innerHeight;
      canvas!.width = Math.round(w * dpr);
      canvas!.height = Math.round(h * dpr);
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      // More stars on bigger screens, capped for speed.
      const count = Math.min(700, Math.round((w * h) / 2600));
      stars = Array.from({ length: count }, () => newStar());
      if (reduce) draw(0, 16);
    }

    // Star at depth z -> screen position.
    function project(s: Star, z: number) {
      const spread = Math.max(w, h) * 0.55;
      const px = mouse.x * (1 - z) * 40;
      const py = mouse.y * (1 - z) * 40;
      return { x: w / 2 + (s.x * spread) / (z * 1.6 + 0.15) + px, y: h / 2 + (s.y * spread) / (z * 1.6 + 0.15) + py };
    }

    function draw(t: number, dt: number) {
      const f = Math.min(3, dt / 16.7); // frame-rate independent
      ctx!.clearRect(0, 0, w, h);

      // Ease the speed towards normal drift or light speed.
      const target = warpRef.current ? 0.022 : 0.0007;
      speed += (target - speed) * (warpRef.current ? 0.03 : 0.06) * f;
      mouse.x += (mouse.tx - mouse.x) * 0.05 * f;
      mouse.y += (mouse.ty - mouse.y) * 0.05 * f;
      const streak = Math.min(1, (speed - 0.0007) / 0.02); // 0 = dots, 1 = full streaks

      for (const s of stars) {
        const zPrev = s.z;
        if (!reduce) s.z -= speed * f;
        if (s.z <= 0.02) Object.assign(s, newStar(true));
        const p = project(s, s.z);
        if (p.x < -50 || p.x > w + 50 || p.y < -50 || p.y > h + 50) {
          Object.assign(s, newStar(true));
          continue;
        }
        const near = 1 - s.z;
        const twinkle = reduce ? 1 : 0.65 + 0.35 * Math.sin(t * 0.001 * s.twinkle + s.x * 10);
        const alpha = Math.min(1, 0.15 + near * 1.1) * twinkle;
        const size = 0.3 + near * 1.9;

        if (streak > 0.02) {
          // Line from where the star was a few frames ago: the light-speed streak.
          const tail = project(s, Math.min(1, zPrev + speed * 14 * streak));
          ctx!.strokeStyle = `rgba(${s.hue},${alpha})`;
          ctx!.lineWidth = size;
          ctx!.beginPath();
          ctx!.moveTo(tail.x, tail.y);
          ctx!.lineTo(p.x, p.y);
          ctx!.stroke();
        } else {
          ctx!.fillStyle = `rgba(${s.hue},${alpha})`;
          ctx!.beginPath();
          ctx!.arc(p.x, p.y, size, 0, Math.PI * 2);
          ctx!.fill();
        }
      }

      if (reduce) return;

      // A shooting star now and then (not during warp).
      if (!warpRef.current && Math.random() < 0.004 * f && meteors.length < 2) {
        const fromLeft = Math.random() < 0.5;
        meteors.push({
          x: fromLeft ? Math.random() * w * 0.5 : w * 0.5 + Math.random() * w * 0.5,
          y: Math.random() * h * 0.4,
          vx: (fromLeft ? 1 : -1) * (9 + Math.random() * 6),
          vy: 4 + Math.random() * 3,
          life: 1,
        });
      }
      for (let i = meteors.length - 1; i >= 0; i--) {
        const m = meteors[i];
        m.x += m.vx * f;
        m.y += m.vy * f;
        m.life -= 0.018 * f;
        if (m.life <= 0) {
          meteors.splice(i, 1);
          continue;
        }
        const g = ctx!.createLinearGradient(m.x, m.y, m.x - m.vx * 10, m.y - m.vy * 10);
        g.addColorStop(0, `rgba(255,255,255,${m.life})`);
        g.addColorStop(1, "rgba(34,211,238,0)");
        ctx!.strokeStyle = g;
        ctx!.lineWidth = 1.6;
        ctx!.beginPath();
        ctx!.moveTo(m.x, m.y);
        ctx!.lineTo(m.x - m.vx * 10, m.y - m.vy * 10);
        ctx!.stroke();
      }

      // Passing ships: cross the screen with blinking nav lights, not during warp.
      if (!warpRef.current && t > nextNpc && npcs.length < 2) {
        nextNpc = t + 9000 + Math.random() * 12000;
        const fromLeft = Math.random() < 0.5;
        const vx = (fromLeft ? 1 : -1) * (0.7 + Math.random() * 0.9);
        const npc: Npc = {
          name: pick(TRAFFIC),
          design: pick(NPC_DESIGNS),
          x: fromLeft ? -40 : w + 40,
          y: h * (0.15 + Math.random() * 0.7),
          vx,
          vy: (Math.random() - 0.5) * 0.35,
          scale: 0.9 + Math.random() * 0.6,
          born: t,
        };
        npcs.push(npc);
        hailRef.current?.(npc.name);
      }
      for (let i = npcs.length - 1; i >= 0; i--) {
        const n = npcs[i];
        n.x += n.vx * f * (warpRef.current ? 6 : 1);
        n.y += n.vy * f;
        if (n.x < -80 || n.x > w + 80) {
          npcs.splice(i, 1);
          continue;
        }
        const angle = Math.atan2(n.vx, -n.vy);
        drawShip(ctx!, n.design, n.x, n.y, n.scale, angle, 0.6, t);
        // Red/green navigation lights on the wing tips
        const blink = Math.floor((t - n.born) / 500) % 2 === 0;
        const side = 14 * n.scale;
        const px = Math.cos(angle) * side;
        const py = Math.sin(angle) * side;
        ctx!.fillStyle = blink ? "rgba(248,113,113,0.95)" : "rgba(248,113,113,0.25)";
        ctx!.beginPath();
        ctx!.arc(n.x - px, n.y - py, 2, 0, Math.PI * 2);
        ctx!.fill();
        ctx!.fillStyle = blink ? "rgba(74,222,128,0.25)" : "rgba(74,222,128,0.95)";
        ctx!.beginPath();
        ctx!.arc(n.x + px, n.y + py, 2, 0, Math.PI * 2);
        ctx!.fill();
        ctx!.fillStyle = "rgba(203,213,225,0.55)";
        ctx!.font = "10px 'JetBrains Mono', monospace";
        ctx!.textAlign = "center";
        ctx!.fillText(n.name.toUpperCase(), n.x, n.y - 26 * n.scale);
      }

      // Burst of sparks when a result arrives.
      while (burstRef.current > 0) {
        burstRef.current -= 1;
        for (let i = 0; i < 160; i++) {
          const a = Math.random() * Math.PI * 2;
          const v = 2 + Math.random() * 9;
          sparks.push({ x: w / 2, y: h * 0.45, vx: Math.cos(a) * v, vy: Math.sin(a) * v, life: 1, hue: pick(HUES) });
        }
      }
      ctx!.globalCompositeOperation = "lighter";
      for (let i = sparks.length - 1; i >= 0; i--) {
        const s = sparks[i];
        s.x += s.vx * f;
        s.y += s.vy * f;
        s.vx *= 0.97;
        s.vy = s.vy * 0.97 + 0.05 * f;
        s.life -= 0.012 * f;
        if (s.life <= 0) {
          sparks.splice(i, 1);
          continue;
        }
        ctx!.fillStyle = `rgba(${s.hue},${s.life})`;
        ctx!.beginPath();
        ctx!.arc(s.x, s.y, 1.2 + s.life * 1.6, 0, Math.PI * 2);
        ctx!.fill();
      }
      ctx!.globalCompositeOperation = "source-over";
    }

    function frame(t: number) {
      draw(t, t - last);
      last = t;
      raf = requestAnimationFrame(frame);
    }

    function onPointer(e: PointerEvent) {
      mouse.tx = (e.clientX / w) * 2 - 1;
      mouse.ty = (e.clientY / h) * 2 - 1;
    }

    // Click on open sky near a passing ship = scan it.
    function onClick(e: MouseEvent) {
      if ((e.target as Element | null)?.closest?.(UI)) return;
      const hit = npcs.find((n) => Math.hypot(n.x - e.clientX, n.y - e.clientY) < 34 * n.scale);
      if (!hit) return;
      scanRef.current?.(hit.name);
      for (let i = 0; i < 40; i++) {
        const a = Math.random() * Math.PI * 2;
        const v = 1 + Math.random() * 4;
        sparks.push({ x: hit.x, y: hit.y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, life: 1, hue: "74,222,128" });
      }
    }

    resize();
    window.addEventListener("resize", resize);
    if (!reduce) {
      window.addEventListener("pointermove", onPointer);
      window.addEventListener("click", onClick);
      raf = requestAnimationFrame(frame);
    }
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", onPointer);
      window.removeEventListener("click", onClick);
    };
  }, []);

  return <canvas ref={canvasRef} className="starfield" aria-hidden="true" />;
}
