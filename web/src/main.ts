import { INTERCEPTS, JOURNAL, VOICES, type Voice } from "./voices";

const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const $ = <T extends HTMLElement>(id: string): T => document.getElementById(id) as T;

/* ---------- звёздное поле ---------- */

type Star = { x: number; y: number; r: number; depth: number; phase: number };

/** Одна искра, отрисованная заранее. Рисовать лучи и свечение
 *  по двести раз в кадр дорого — копировать картинку дёшево. */
function sparkleSprite(): HTMLCanvasElement {
  const size = 128;
  const c = document.createElement("canvas");
  c.width = size;
  c.height = size;
  const g = c.getContext("2d");
  if (!g) return c;
  const m = size / 2;

  const halo = g.createRadialGradient(m, m, 0, m, m, m);
  halo.addColorStop(0, "rgba(255, 253, 247, 0.75)");
  halo.addColorStop(0.12, "rgba(232, 222, 200, 0.34)");
  halo.addColorStop(0.4, "rgba(207, 199, 234, 0.10)");
  halo.addColorStop(1, "rgba(207, 199, 234, 0)");
  g.fillStyle = halo;
  g.fillRect(0, 0, size, size);

  // лучи: длинные по осям, короткие по диагоналям
  const ray = (angle: number, len: number, width: number, alpha: number): void => {
    g.save();
    g.translate(m, m);
    g.rotate(angle);
    const grad = g.createLinearGradient(0, 0, len, 0);
    grad.addColorStop(0, `rgba(255, 253, 247, ${alpha})`);
    grad.addColorStop(1, "rgba(255, 253, 247, 0)");
    g.fillStyle = grad;
    g.beginPath();
    g.moveTo(0, -width);
    g.lineTo(len, 0);
    g.lineTo(0, width);
    g.closePath();
    g.fill();
    g.restore();
  };

  for (let i = 0; i < 4; i += 1) ray((Math.PI / 2) * i, m - 2, 2.6, 0.95);
  for (let i = 0; i < 4; i += 1) ray(Math.PI / 4 + (Math.PI / 2) * i, m * 0.42, 1.5, 0.5);
  for (let i = 0; i < 8; i += 1) ray((Math.PI / 4) * i + Math.PI / 8, m * 0.24, 0.9, 0.3);

  const core = g.createRadialGradient(m, m, 0, m, m, 7);
  core.addColorStop(0, "rgba(255, 255, 255, 1)");
  core.addColorStop(1, "rgba(255, 253, 247, 0)");
  g.fillStyle = core;
  g.beginPath();
  g.arc(m, m, 7, 0, Math.PI * 2);
  g.fill();
  return c;
}

const SPARK = sparkleSprite();

function sky(canvas: HTMLCanvasElement, density: number): void {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  let stars: Star[] = [];
  let w = 0;
  let h = 0;
  const eye = { x: 0, y: 0 };

  const resize = (): void => {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = canvas.clientWidth;
    h = canvas.clientHeight;
    if (w === 0 || h === 0) return;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    stars = Array.from({ length: Math.round((w * h) / density) }, () => ({
      x: Math.random() * w,
      y: Math.random() * h,
      r: Math.random() ** 2 * 1.15 + 0.22,
      depth: Math.random() * 0.75 + 0.25,
      phase: Math.random() * Math.PI * 2,
    }));
  };

  const paint = (t: number): void => {
    ctx.clearRect(0, 0, w, h);
    for (const s of stars) {
      const glow = REDUCED ? 0.6 : 0.4 + Math.sin(t / 1500 + s.phase) * 0.34;
      const size = s.r * 6.5 * (REDUCED ? 1 : 0.9 + Math.sin(t / 1700 + s.phase) * 0.14);
      ctx.globalAlpha = Math.min(Math.max(glow, 0.1) * s.depth, 1);
      ctx.drawImage(
        SPARK,
        s.x + eye.x * s.depth * 12 - size / 2,
        s.y + eye.y * s.depth * 12 - size / 2,
        size,
        size,
      );
    }
    ctx.globalAlpha = 1;
    if (!REDUCED) requestAnimationFrame(paint);
  };

  window.addEventListener("resize", resize);
  if (!REDUCED) {
    window.addEventListener("pointermove", (e) => {
      eye.x = e.clientX / window.innerWidth - 0.5;
      eye.y = e.clientY / window.innerHeight - 0.5;
    });
  }
  resize();
  requestAnimationFrame(paint);
}

/* ---------- рябь по горизонту ---------- */

function ripple(): void {
  const box = $("ripple");
  for (let i = 0; i < 48; i += 1) {
    const s = document.createElement("span");
    s.style.animationDelay = `${(i % 12) * 0.42}s`;
    box.append(s);
  }
}

/* ---------- списки ---------- */

function lists(): void {
  const cmds = $("cmds");
  for (const [cmd, what] of JOURNAL) {
    const row = document.createElement("div");
    row.className = "cmd";
    const dt = document.createElement("dt");
    dt.textContent = cmd;
    const dd = document.createElement("dd");
    dd.textContent = what;
    row.append(dt, dd);
    cmds.append(row);
  }

  const feed = $("intercepts");
  for (const [src, line, at] of INTERCEPTS) {
    const li = document.createElement("li");
    const a = document.createElement("span");
    a.className = "src";
    a.textContent = src;
    const b = document.createElement("span");
    b.textContent = line;
    const c = document.createElement("span");
    c.className = "at";
    c.textContent = at;
    li.append(a, b, c);
    feed.append(li);
  }
}

/* ---------- карточка объекта ---------- */

let run = 0;

function retype(text: string): void {
  const box = $("v-sample");
  const mine = ++run;
  if (REDUCED) {
    box.textContent = text;
    return;
  }
  const old = box.textContent ?? "";
  let i = old.length;

  const erase = (): void => {
    if (mine !== run) return;
    box.textContent = old.slice(0, (i -= 3));
    if (i > 0) window.setTimeout(erase, 12);
    else write();
  };
  let j = 0;
  const write = (): void => {
    if (mine !== run) return;
    box.textContent = text.slice(0, (j += 1));
    if (j < text.length) window.setTimeout(write, 17);
  };
  old ? erase() : write();
}

/** Видна ли карточка целиком. */
function cardFits(): boolean {
  const card = document.querySelector<HTMLElement>(".card");
  if (!card) return true;
  const box = card.getBoundingClientRect();
  return box.top >= 48 && box.bottom <= window.innerHeight - 8;
}

function focusCard(): void {
  const card = document.querySelector<HTMLElement>(".card");
  if (!card) return;
  // прилипание секций мешает точному доводу — гасим его на время перехода
  const root = document.documentElement;
  const was = root.style.scrollSnapType;
  root.style.scrollSnapType = "none";
  card.scrollIntoView({ behavior: REDUCED ? "auto" : "smooth", block: "nearest" });
  window.setTimeout(() => {
    root.style.scrollSnapType = was;
  }, 900);
}

function open(v: Voice): void {
  $("v-code").textContent = v.code;
  $("v-mag").textContent = v.tagline;
  $("v-name").textContent = v.name;
  $("v-about").textContent = v.about;
  $("v-cmd").textContent = `/voice ${v.id}`;
  $("v-tags").replaceChildren(
    ...v.registers.map((r) => {
      const li = document.createElement("li");
      li.textContent = r;
      return li;
    }),
  );
  retype(v.sample);
  document.querySelectorAll<HTMLButtonElement>(".star").forEach((b) => {
    b.setAttribute("aria-pressed", String(b.dataset.id === v.id));
  });
}

/* ---------- звёзды и прицел ---------- */

let hoverScroll = 0;

function starmap(): void {
  const stars = $("stars");
  const field = $("sky");
  const cross = $("crosshair");

  for (const v of VOICES) {
    const b = document.createElement("button");
    b.className = "star";
    b.type = "button";
    b.dataset.id = v.id;
    b.style.left = `${v.x}%`;
    b.style.top = `${v.y}%`;
    b.style.setProperty("--d", `${1.15 - v.magnitude * 0.18}rem`);
    b.setAttribute("aria-pressed", "false");
    const dot = document.createElement("span");
    dot.className = "dot";
    dot.append(document.createElement("i"));   // диагональные лучи
    const label = document.createElement("span");
    label.textContent = v.name;
    b.append(dot, label);
    b.addEventListener("click", () => {
      open(v);
      focusCard();
    });
    b.addEventListener("pointerenter", () => {
      if (!window.matchMedia("(hover: hover)").matches) return;
      open(v);
      // если карточка не влезла в экран — подтягиваем, но не дёргаем
      window.clearTimeout(hoverScroll);
      hoverScroll = window.setTimeout(() => {
        if (!cardFits()) focusCard();
      }, 220);
    });
    stars.append(b);
  }

  if (REDUCED || !window.matchMedia("(hover: hover)").matches) return;

  field.addEventListener("pointerenter", () => field.classList.add("aiming"));
  field.addEventListener("pointerleave", () => field.classList.remove("aiming"));
  field.addEventListener("pointermove", (e) => {
    const box = field.getBoundingClientRect();
    let x = e.clientX - box.left;
    let y = e.clientY - box.top;

    // прицел притягивается к ближайшему объекту
    let best = 60;
    for (const dot of field.querySelectorAll<HTMLElement>(".star .dot")) {
      const d = dot.getBoundingClientRect();
      const cx = d.left + d.width / 2 - box.left;
      const cy = d.top + d.height / 2 - box.top;
      const dist = Math.hypot(cx - x, cy - y);
      if (dist < best) {
        best = dist;
        x = cx;
        y = cy;
      }
    }
    cross.style.transform = `translate(${x}px, ${y}px)`;
  });
}

/* ---------- появление блоков при скролле ---------- */

function reveal(): void {
  const items = document.querySelectorAll<HTMLElement>("[data-reveal]");
  if (REDUCED) {
    items.forEach((el) => el.classList.add("seen"));
    return;
  }
  const eye = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (e.isIntersecting) {
          e.target.classList.add("seen");
          eye.unobserve(e.target);
        }
      }
    },
    { rootMargin: "0px 0px -12% 0px", threshold: 0.15 },
  );
  items.forEach((el) => eye.observe(el));
}

/* ---------- точки-навигация и переход к следующей секции ---------- */

function navigation(): void {
  const sections = Array.from(document.querySelectorAll<HTMLElement>(".snap"));
  const dots = $("dots");

  for (const section of sections) {
    const b = document.createElement("button");
    b.className = "dot-btn";
    b.type = "button";
    b.setAttribute("aria-current", "false");
    b.dataset.target = section.id;
    const label = document.createElement("span");
    label.textContent = section.dataset.label ?? "";
    const mark = document.createElement("i");
    b.append(label, mark);
    b.addEventListener("click", () => section.scrollIntoView({ behavior: "smooth" }));
    dots.append(b);
  }

  const marks = Array.from(dots.querySelectorAll<HTMLButtonElement>(".dot-btn"));
  const eye = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (!e.isIntersecting) continue;
        for (const m of marks) {
          m.setAttribute("aria-current", String(m.dataset.target === e.target.id));
        }
      }
    },
    { threshold: 0.35 },
  );
  sections.forEach((s) => eye.observe(s));

  document.querySelectorAll<HTMLButtonElement>("[data-next]").forEach((b) => {
    b.addEventListener("click", () => {
      document.getElementById(b.dataset.next ?? "")?.scrollIntoView({ behavior: "smooth" });
    });
  });
}

sky($("hero-sky") as HTMLCanvasElement, 4800);
sky($("voice-sky") as HTMLCanvasElement, 3600);
ripple();
lists();
starmap();
open(VOICES[0]);
reveal();
navigation();

const bar = document.querySelector<HTMLElement>(".bar");
if (bar) {
  const mark = (): void => {
    bar.classList.toggle("stuck", window.scrollY > 8);
  };
  window.addEventListener("scroll", mark, { passive: true });
  mark();
}
