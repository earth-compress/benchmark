// The lossy page: rate against error for each dataset, and a viewer that puts
// georvq beside another codec at the rate of a slider.
const NS = "http://www.w3.org/2000/svg";
const PAYLOAD = JSON.parse(document.getElementById("chart-data").textContent);
const RAMP = [[0, 0, 4], [59, 15, 112], [140, 41, 129], [222, 73, 104], [254, 159, 109], [252, 253, 191]];
const CROP = 128;
function el(name, attrs, text) {
  const node = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text !== undefined) node.textContent = text;
  return node;
}
function ramp(v) {
  const x = Math.min(Math.max(v, 0), 1) * (RAMP.length - 1);
  const i = Math.min(Math.floor(x), RAMP.length - 2), t = x - i;
  return RAMP[i].map((c, k) => Math.round(c * (1 - t) + RAMP[i + 1][k] * t));
}
const fmt = v => (v >= 100 ? v.toFixed(0) : v >= 10 ? v.toFixed(1) : v >= 1 ? v.toFixed(2) : v.toPrecision(2));
function logTicks(lo, hi) {
  const out = [];
  for (let e = Math.floor(Math.log10(lo)) - 1; e <= Math.ceil(Math.log10(hi)); e++)
    for (const m of [1, 2, 5]) { const v = m * 10 ** e; if (v >= lo && v <= hi) out.push(v); }
  return out;
}
function legend(codecs, names) {
  const div = document.createElement("div");
  div.className = "legend";
  for (const c of names) {
    const item = document.createElement("span");
    item.style.setProperty("--c", codecs[c][1]);
    item.innerHTML = `<i></i>${codecs[c][0]}`;
    div.append(item);
  }
  return div;
}

// Rate against error, both on log scales.
function rd(box, set, metric, rate) {
  const { curves, codecs, metrics, georvq } = set;
  const [label, unit] = metrics[metric];
  const W = Math.max(320, box.clientWidth || 960);
  const H = Math.round(Math.max(300, Math.min(480, W * 0.5)));
  const L = 56, R = 24, T = 40, B = 54;
  const all = Object.values(curves).flat().filter(p => p[metric] > 0);
  const x0 = Math.log10(Math.min(...all.map(p => p.bpp)) / 1.3), x1 = Math.log10(Math.max(...all.map(p => p.bpp)) * 1.3);
  const y0 = Math.log10(Math.min(...all.map(p => p[metric])) / 1.5), y1 = Math.log10(Math.max(...all.map(p => p[metric])) * 1.5);
  const X = v => L + (Math.log10(v) - x0) / (x1 - x0) * (W - L - R);
  const Y = v => H - B - (Math.log10(v) - y0) / (y1 - y0) * (H - T - B);
  const svg = el("svg", { class: "in", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `Bits per pixel against ${label}` });
  const axes = el("g", { class: "axes" });
  for (const v of logTicks(10 ** x0, 10 ** x1)) {
    axes.append(el("line", { x1: X(v), x2: X(v), y1: T, y2: H - B, class: "grid" }));
    axes.append(el("text", { x: X(v), y: H - B + 20, class: "tick", "text-anchor": "middle" }, v.toLocaleString("en")));
  }
  const yt = logTicks(10 ** y0, 10 ** y1);
  for (const v of yt.length > 9 ? yt.filter(v => String(v)[0] !== "2") : yt) {
    axes.append(el("line", { x1: L, x2: W - R, y1: Y(v), y2: Y(v), class: "grid" }));
    axes.append(el("text", { x: L - 10, y: Y(v) + 4, class: "tick", "text-anchor": "end" }, v.toLocaleString("en", { maximumSignificantDigits: 3 })));
  }
  axes.append(el("text", { x: W - R, y: H - 8, class: "axis", "text-anchor": "end" }, "bits per pixel →"));
  axes.append(el("text", { x: L, y: T - 14, class: "axis" }, `↓ ${label}${unit ? `, ${unit}` : ""}`));
  svg.append(axes);
  if (rate) svg.append(el("line", { class: "now", x1: X(rate), x2: X(rate), y1: T, y2: H - B }));
  const names = Object.keys(curves).sort((a, b) => (a === georvq) - (b === georvq));
  for (const c of names) {
    const points = curves[c].filter(p => p[metric] > 0);
    const g = el("g", { class: `series${c === georvq ? " lead" : ""}`, style: `--c:${codecs[c][1]}` });
    g.append(el("polyline", { points: points.map(p => `${X(p.bpp)},${Y(p[metric])}`).join(" ") }));
    for (const p of points) {
      const dot = el("circle", { cx: X(p.bpp), cy: Y(p[metric]), r: c === georvq ? 4 : 3.5 });
      dot.append(el("title", {}, `${codecs[c][0]} · ${p.setting} · ${p.bpp.toFixed(2)} bits per pixel · ${label} ${fmt(p[metric])}${unit ? " " + unit : ""} · decode ${p.decode_s.toFixed(2)} s`));
      g.append(dot);
    }
    svg.append(g);
  }
  box.replaceChildren(legend(codecs, [georvq, ...names.filter(c => c !== georvq)]), svg);
}

// How much of each sample's power the decode keeps, at each scale.
function spectrum(box, set, views, colours) {
  const W = Math.max(300, box.clientWidth || 500), H = 240, L = 40, R = 24, T = 34, B = 44;
  const n = 24, edges = Array.from({ length: n + 1 }, (_, k) => (2 / 504) * (0.5 / (2 / 504)) ** (k / n));
  const centres = edges.slice(0, n).map((e, k) => Math.sqrt(e * edges[k + 1]));
  const X = f => L + (Math.log10(f) - Math.log10(centres[0])) / (Math.log10(centres[n - 1]) - Math.log10(centres[0])) * (W - L - R);
  const Y = v => H - B - Math.min(Math.max(v, 0), 1.6) / 1.6 * (H - T - B);
  const svg = el("svg", { class: "in", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Power kept at each scale" });
  for (const v of [0, 0.5, 1, 1.5]) {
    svg.append(el("line", { x1: L, x2: W - R, y1: Y(v), y2: Y(v), class: v === 1 ? "one" : "grid" }));
    svg.append(el("text", { x: L - 10, y: Y(v) + 4, class: "tick", "text-anchor": "end" }, v.toFixed(1)));
  }
  for (const m of [2000, 1000, 500, 200, 100, 50, 20]) {
    const f = 10 / m;
    if (f < centres[0] || f > centres[n - 1]) continue;
    svg.append(el("line", { x1: X(f), x2: X(f), y1: T, y2: H - B, class: "grid" }));
    svg.append(el("text", { x: X(f), y: H - B + 18, class: "tick", "text-anchor": "middle" }, `${m} m`));
  }
  svg.append(el("text", { x: W - R, y: H - 4, class: "axis", "text-anchor": "end" }, "finer detail →"));
  svg.append(el("text", { x: L, y: T - 12, class: "axis" }, "↑ power of the decode over the original"));
  views.forEach((v, k) => {
    if (!v) return;
    svg.append(el("polyline", { class: "spec", style: `--c:${colours[k]}`, points: v.spectrum.map((s, i) => `${X(centres[i])},${Y(s)}`).join(" ") }));
  });
  box.replaceChildren(svg);
}

function similarity(codes, p) {
  // The cosine of every pixel's embedding with the embedding at pixel p.
  const D = 64, N = CROP * CROP, e = new Float32Array(D * N);
  for (let i = 0; i < D * N; i++) { const v = codes[i] / 127.5; e[i] = v * Math.abs(v); }
  const ref = new Float32Array(D);
  let rn = 0;
  for (let d = 0; d < D; d++) { ref[d] = e[d * N + p]; rn += ref[d] * ref[d]; }
  const out = new Float32Array(N);
  for (let q = 0; q < N; q++) {
    let dot = 0, n = 0;
    for (let d = 0; d < D; d++) { const v = e[d * N + q]; dot += v * ref[d]; n += v * v; }
    out[q] = codes[q] === -128 ? NaN : dot / Math.sqrt(Math.max(n * rn, 1e-12));
  }
  return out;
}

function viewer(panel, set, key, onRate) {
  const ae = key === "alphaearth";
  const base = `${key}/`;
  const [cl, cr] = ["left", "right"].map(s => panel.querySelector(`canvas.${s}`));
  const [sl, sr] = ["left", "right"].map(s => panel.querySelector(`.side.${s}`));
  const stage = panel.querySelector(".stage"), handle = panel.querySelector(".handle"), target = panel.querySelector(".target");
  const slider = panel.querySelector(".rate input"), out = panel.querySelector(".rate output");
  const other = panel.querySelector("select.other"), note = panel.querySelector(".mode-note");
  const sampleBox = panel.querySelector(".samples");
  const ids = Object.keys(set.samples);
  const state = { sample: ids[0], stop: set.stops.indexOf(set.start), mode: "image", split: 0.5, pixel: (CROP / 2) * CROP + CROP / 2 };
  const cache = new Map();
  const load = (url, kind) => {
    if (!cache.has(url)) cache.set(url, kind === "bin"
      ? fetch(url).then(r => r.arrayBuffer()).then(b => new Int8Array(b))
      : new Promise((ok, fail) => { const i = new Image(); i.onload = () => ok(i); i.onerror = fail; i.src = url; }));
    return cache.get(url);
  };
  ids.forEach((id, k) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = set.samples[id].site;
    b.dataset.id = id;
    sampleBox.append(b);
  });
  const others = Object.keys(set.codecs).filter(c => c !== set.georvq);
  other.innerHTML = `<option value="original">original</option>` + others.map(c => `<option value="${c}">${set.codecs[c][0]}</option>`).join("");
  other.value = others.includes("jpegxl-distance") ? "jpegxl-distance" : others[0];
  slider.value = state.stop;
  const metric = ae ? "cos_mean" : "rmse_10m";
  const caption = (code, v, stop) => {
    if (code === "original") return "original";
    const err = ae ? `1 − cos ${fmt(v.cos_mean)}` : `RMSE ${fmt(v.rmse_10m)} DN`;
    const far = v.bits_per_pixel > stop * 1.4 ? ", its lowest rate" : v.bits_per_pixel < stop / 1.4 ? ", its highest rate" : "";
    return `${set.codecs[code][0]} · ${v.setting} · ${v.bits_per_pixel.toFixed(2)} bpp${far} · ${err}`;
  };
  // A paint that a newer render overtook draws nothing.
  async function paint(canvas, mine, code, v) {
    const ctx = canvas.getContext("2d");
    const folder = `${base}${state.sample}/`;
    if (state.mode === "similarity") {
      const codes = await load(folder + (code === "original" ? "original.bin" : v.codes), "bin");
      if (mine !== token) return;
      const s = similarity(codes, state.pixel);
      canvas.width = canvas.height = CROP;
      const img = ctx.createImageData(CROP, CROP);
      s.forEach((c, i) => {
        const rgb = Number.isNaN(c) ? [200, 200, 200] : ramp((c - 0.4) / 0.6);
        img.data.set([...rgb, 255], i * 4);
      });
      ctx.putImageData(img, 0, 0);
      return;
    }
    if (state.mode === "error" && code === "original") { canvas.width = canvas.height = 8; ctx.fillStyle = `rgb(${RAMP[0]})`; ctx.fillRect(0, 0, 8, 8); return; }
    const img = await load(folder + (code === "original" ? "original.webp" : state.mode === "error" ? v.error : v.image));
    if (mine !== token) return;
    canvas.width = img.naturalWidth; canvas.height = img.naturalHeight;
    ctx.drawImage(img, 0, 0);
  }
  let token = 0;
  async function render() {
    const mine = ++token;
    const stop = set.stops[state.stop];
    const chosen = set.samples[state.sample].stops[String(stop)] || {};
    const lv = chosen[set.georvq], rv = other.value === "original" ? null : chosen[other.value];
    out.textContent = `${stop} bits per pixel`;
    sampleBox.querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.id === state.sample)));
    panel.querySelectorAll(".modes button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.mode === state.mode)));
    sl.textContent = caption(set.georvq, lv, stop);
    sr.textContent = caption(other.value, rv, stop);
    stage.classList.toggle("pixelated", ae);
    target.hidden = state.mode !== "similarity";
    note.innerHTML = {
      image: ae ? "The first three principal components of the original embedding, as red, green and blue, applied to each decode. Drag to compare." : "True colour from B4, B3 and B2. Drag to compare.",
      error: `Error at each pixel, ${ae ? "1 − cos" : "the RMSE of the four 10 m bands"}, on a scale from ${ae ? "0 to 0.05" : "0 to 250 DN"}, dark to light.`,
      similarity: "The central 128 pixels. Click one, and each side shows the cosine of every pixel with it in that decode, from 0.4, dark, to 1, light: what a similarity search would find.",
    }[state.mode];
    await Promise.all([paint(cl, mine, set.georvq, lv), paint(cr, mine, other.value, rv)]);
    if (mine !== token) return;
    place();
    onefile(lv);
    if (!ae) spectrum(panel.querySelector(".chart.spectrum"), set, [lv, rv], [set.codecs[set.georvq][1], rv ? set.codecs[other.value][1] : "#143031"]);
    onRate(stop);
  }
  function onefile(lv) {
    const rungs = set.samples[state.sample].rungs, top = Math.max(...rungs.map(r => r.bits_per_pixel));
    const bar = panel.querySelector(".onefile .bar"), text = panel.querySelector(".onefile .note");
    const read = lv ? lv.bits_per_pixel : 0;
    bar.style.setProperty("--read", `${(read / top) * 100}%`);
    bar.replaceChildren(...rungs.map(r => { const t = document.createElement("i"); t.style.left = `${(r.bits_per_pixel / top) * 100}%`; return t; }));
    text.textContent = lv
      ? `One georvq file of ${top.toFixed(2)} bits per pixel holds all ${rungs.length} depths. At this rate a reader takes ${read.toFixed(2)} of them, ${Math.round((read / top) * 100)}% of the file. Every other codec writes a new file for each rate.`
      : `One georvq file of ${top.toFixed(2)} bits per pixel holds all ${rungs.length} depths, and this rate is past its last one.`;
  }
  function place() {
    cl.style.clipPath = `inset(0 ${(1 - state.split) * 100}% 0 0)`;
    handle.style.left = `${state.split * 100}%`;
    target.style.left = `${((state.pixel % CROP) + 0.5) / CROP * 100}%`;
    target.style.top = `${(Math.floor(state.pixel / CROP) + 0.5) / CROP * 100}%`;
  }
  let dragging = false;
  const at = e => { const r = stage.getBoundingClientRect(); return [(e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height]; };
  stage.addEventListener("pointerdown", e => {
    const [x, y] = at(e);
    if (state.mode === "similarity" && !e.target.closest(".handle")) {
      state.pixel = Math.min(CROP - 1, Math.floor(y * CROP)) * CROP + Math.min(CROP - 1, Math.floor(x * CROP));
      render();
      return;
    }
    dragging = true;
    stage.setPointerCapture(e.pointerId);
    state.split = Math.min(Math.max(x, 0), 1);
    place();
  });
  stage.addEventListener("pointermove", e => { if (dragging) { state.split = Math.min(Math.max(at(e)[0], 0), 1); place(); } });
  stage.addEventListener("pointerup", () => { dragging = false; });
  slider.addEventListener("input", () => { state.stop = Number(slider.value); render(); });
  other.addEventListener("change", render);
  sampleBox.addEventListener("click", e => { const b = e.target.closest("button"); if (b) { state.sample = b.dataset.id; render(); } });
  panel.querySelector(".modes").addEventListener("click", e => { const b = e.target.closest("button"); if (b) { state.mode = b.dataset.mode; render(); } });
  render();
}

document.querySelectorAll(".panel.lossy").forEach(panel => {
  const key = panel.dataset.set, set = PAYLOAD[key];
  const box = panel.querySelector(".chart.rd"), metric = panel.querySelector("select.metric");
  let rate = set.start, width = 0;
  const draw = () => { width = box.clientWidth; rd(box, set, metric.value, rate); };
  metric.addEventListener("change", draw);
  new ResizeObserver(() => { if (Math.abs(box.clientWidth - width) > 40) draw(); }).observe(box);
  viewer(panel, set, key, r => { if (r !== rate) { rate = r; draw(); } });
  draw();
});

const tabs = [...document.querySelectorAll('[role="tab"]')];
tabs.forEach(tab => tab.addEventListener("click", () => {
  tabs.forEach(t => {
    t.setAttribute("aria-selected", String(t === tab));
    document.getElementById(t.getAttribute("aria-controls")).hidden = t !== tab;
  });
}));
