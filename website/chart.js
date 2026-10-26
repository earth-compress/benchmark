// The compression ratio against decode speed chart, drawn from a JSON block on the page.
const NS = "http://www.w3.org/2000/svg";
const STILL = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
// Labels are 11 px below this width and 13 px above it, as in style.css.
const SMALL_TEXT = window.matchMedia("(max-width: 760px)").matches;
function el(name, attrs, text) {
  const node = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text !== undefined) node.textContent = text;
  return node;
}
function frontier(points) {
  const sorted = [...points].sort((a, b) => b.speed - a.speed);
  const front = [];
  let best = -Infinity;
  for (const p of sorted) if (p.ratio > best) { front.push(p); best = p.ratio; }
  return front;
}
const slug = name => name.toLowerCase().replace(/[^a-z0-9]+/g, "-");
const rate = entry => ({
  ratio: entry.input / entry.compressed,
  speed: entry.input / 1e6 / (entry.decode_ns / 1e9),
  entry,
});
const mbs = (bytes, ns) => Math.round(bytes / 1e6 / (ns / 1e9)).toLocaleString("en");
const mb = bytes => (bytes / 1e6).toLocaleString("en", { maximumFractionDigits: 1 });
function details(id, group, p) {
  const e = p.entry;
  const span = e.samples === 1
    ? `${mbs(e.input, e.decode_max_ns)} to ${mbs(e.input, e.decode_min_ns)} MB/s over the repeated calls`
    : `${e.samples} samples${e.corpora ? ` in ${e.corpora} corpora` : ""}`;
  return `<strong>${id}</strong>${group ? `<span class="group">${group}</span>` : ""}
<dl>
<dt>ratio</dt><dd>${p.ratio.toFixed(3)}</dd>
<dt>bits per value</dt><dd>${(e.compressed * 8 / e.elements).toFixed(2)}</dd>
<dt>decode</dt><dd>${mbs(e.input, e.decode_ns)} MB/s</dd>
<dt>encode</dt><dd>${mbs(e.input, e.encode_ns)} MB/s</dd>
<dt>size</dt><dd>${mb(e.input)} MB to ${mb(e.compressed)} MB</dd>
</dl>
<p>${span}</p>
<p>${e.version}</p>`;
}
function hover(box, target, html, x, y) {
  const show = () => {
    const tip = box.querySelector(".tip");
    tip.innerHTML = html;
    tip.hidden = false;
    const top = box.querySelector("svg").getBoundingClientRect().top - box.getBoundingClientRect().top;
    const left = x + 14 + tip.offsetWidth > box.clientWidth ? x - 14 - tip.offsetWidth : x + 14;
    tip.style.left = `${Math.max(0, left)}px`;
    tip.style.top = `${Math.max(0, top + y - 12)}px`;
  };
  const hide = () => { box.querySelector(".tip").hidden = true; };
  target.addEventListener("pointerenter", show);
  target.addEventListener("pointerleave", hide);
  target.addEventListener("focus", show);
  target.addEventListener("blur", hide);
}
function legend(groups, present) {
  const div = document.createElement("div");
  div.className = "legend";
  for (const name of [...new Set(Object.values(groups))]) {
    if (!present.has(name)) continue;
    const item = document.createElement("span");
    item.className = `g-${slug(name)}`;
    item.innerHTML = `<i></i>${name}`;
    div.append(item);
  }
  return div;
}
function draw(box, totals, CODECS, groups, reference) {
  const points = CODECS.filter(c => totals[c]).map(c => ({ id: c, group: groups[c], ...rate(totals[c]) }));
  const ref = reference && totals[reference] ? rate(totals[reference]) : null;
  const W = Math.max(320, box.clientWidth || 960);
  const H = Math.round(Math.max(300, Math.min(520, W * 0.56)));
  const L = 48, R = W < 600 ? 96 : 150, T = 40, B = 54;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Compression ratio against decode speed" });
  const speeds = points.map(p => p.speed), ratios = points.map(p => p.ratio);
  const x0 = Math.log10(Math.min(...speeds, 100) / 1.5), x1 = Math.log10(Math.max(...speeds, 1000) * 1.5);
  const y0 = 1, y1 = Math.max(1.5, Math.ceil(Math.max(...ratios, ref ? ref.ratio : 1, 1) * 1.1 * 4) / 4);
  const X = v => L + (Math.log10(v) - x0) / (x1 - x0) * (W - L - R);
  const Y = v => H - B - (v - y0) / (y1 - y0) * (H - T - B);
  const axes = el("g", { class: "axes" });
  const narrow = W < 600;
  for (const v of narrow ? [10, 100, 1000, 10000] : [10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000]) {
    if (Math.log10(v) < x0 || Math.log10(v) > x1) continue;
    axes.append(el("line", { x1: X(v), x2: X(v), y1: T, y2: H - B, class: "grid" }));
    axes.append(el("text", { x: X(v), y: H - B + 20, class: "tick", "text-anchor": "middle" }, v.toLocaleString("en")));
  }
  const step = y1 - y0 > 2 ? 0.5 : 0.25;
  for (let v = y0; v <= y1 + 1e-9; v += step) {
    axes.append(el("line", { x1: L, x2: W - R, y1: Y(v), y2: Y(v), class: "grid" }));
    axes.append(el("text", { x: L - 10, y: Y(v) + 4, class: "tick", "text-anchor": "end" }, v.toFixed(2)));
  }
  axes.append(el("text", { x: W - R, y: H - 8, class: "axis", "text-anchor": "end" }, "decode MB/s →"));
  axes.append(el("text", { x: L, y: T - 14, class: "axis" }, "↑ compression ratio"));
  svg.append(axes);
  const placed = [];
  if (ref) {
    const y = Y(ref.ratio);
    const text = `JPEG 2000 reference · decode ${Math.round(ref.speed).toLocaleString("en")} MB/s`;
    const g = el("g", { class: "reference", tabindex: 0, "aria-label": text });
    g.append(el("line", { x1: L, x2: W - R, y1: y, y2: y }));
    g.append(el("line", { class: "hit", x1: L, x2: W - R, y1: y, y2: y }));
    g.append(el("text", { x: L + 6, y: y - 6, "text-anchor": "start" }, text));
    svg.append(g);
    const w = text.length * (SMALL_TEXT ? 5.6 : 6.6);
    placed.push({ x: L + 6, y: y - 18, w, h: 15 });
    hover(box, g, details(reference, "reference", ref), L + 6 + w, y);
  }
  const front = frontier(points);
  if (front.length > 1) {
    const path = el("path", { class: "pareto", d: front.map((p, i) => `${i ? "L" : "M"}${X(p.speed)},${Y(p.ratio)}`).join(" ") });
    svg.append(path);
  }
  const onFront = new Set(front.map(p => p.id));
  const order = [...points].sort((a, b) => a.speed - b.speed);
  const free = box => !placed.some(o => box.x < o.x + o.w && o.x < box.x + box.w && box.y < o.y + o.h && o.y < box.y + box.h);
  points.forEach(p => placed.push({ x: X(p.speed) - 7, y: Y(p.ratio) - 7, w: 14, h: 14 }));
  order.forEach((p, i) => {
    const g = el("g", { class: `point g-${slug(p.group || "")}` + (onFront.has(p.id) ? " front" : ""), style: `--i:${i}` });
    g.setAttribute("tabindex", 0);
    g.setAttribute("aria-label", `${p.id}: ratio ${p.ratio.toFixed(2)}, decode ${Math.round(p.speed).toLocaleString("en")} MB/s`);
    g.append(el("circle", { cx: X(p.speed), cy: Y(p.ratio), r: 6 }));
    g.append(el("circle", { class: "hit", cx: X(p.speed), cy: Y(p.ratio), r: 14 }));
    hover(box, g, details(p.id, p.group, p), X(p.speed), Y(p.ratio));
    if (narrow && !onFront.has(p.id)) { svg.append(g); return; }
    const w = p.id.length * (SMALL_TEXT ? 6.7 : 7.9), cx = X(p.speed), cy = Y(p.ratio);
    const spots = [[cx + 10, cy + 4, "start"], [cx - 10, cy + 4, "end"], [cx + 8, cy - 10, "start"], [cx + 8, cy + 20, "start"], [cx - 8, cy - 10, "end"], [cx - 8, cy + 20, "end"]];
    const fits = s => {
      const b = { x: s[2] === "end" ? s[0] - w : s[0], y: s[1] - 12, w, h: 15 };
      return b.x > L && b.x + w < W ? b : null;
    };
    const spot = spots.find(s => fits(s) && free(fits(s))) || spots.find(fits) || spots[0];
    if (fits(spot)) placed.push(fits(spot));
    g.append(el("text", { x: spot[0], y: spot[1], "text-anchor": spot[2], class: "label" }, p.id));
    svg.append(g);
  });
  if (!points.length) svg.append(el("text", { x: (W - R) / 2, y: H / 2, class: "axis", "text-anchor": "middle" }, "No results yet"));
  const tip = document.createElement("div");
  tip.className = "tip";
  tip.hidden = true;
  box.replaceChildren(legend(groups, new Set(points.map(p => p.group))), svg, tip);
  const path = svg.querySelector(".pareto");
  if (path && !STILL) {
    const length = path.getTotalLength();
    path.style.strokeDasharray = length;
    path.animate(
      [{ strokeDashoffset: length }, { strokeDashoffset: 0 }],
      { duration: 1100, delay: order.length * 90 + 350, easing: "ease-in-out", fill: "backwards" },
    );
  }
  svg.getBoundingClientRect();
  svg.classList.add("in");
}

function mountChart(box, read) {
  const { data, codecs, groups, reference } = JSON.parse(document.getElementById("chart-data").textContent);
  const render = () => draw(box, data[read()] || {}, codecs, groups, reference);
  // Draw once now, and again only when the width changes enough to matter.
  let lastWidth = box.clientWidth;
  render();
  new ResizeObserver(entries => {
    const width = Math.round(entries[0].contentRect.width);
    if (Math.abs(width - lastWidth) > 40) { lastWidth = width; render(); }
  }).observe(box);
  return render;
}

document.querySelectorAll("[data-chart]").forEach(box => {
  const select = document.getElementById(box.dataset.select || "");
  const render = mountChart(box, () => (select ? select.value : box.dataset.chart));
  if (select) select.addEventListener("change", render);
});

const tabs = [...document.querySelectorAll('[role="tab"]')];
tabs.forEach(tab => tab.addEventListener("click", () => {
  tabs.forEach(t => {
    const on = t === tab;
    t.setAttribute("aria-selected", String(on));
    document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
  });
  const pick = document.querySelector(".pick");
  if (pick) pick.style.visibility = tab === tabs[0] ? "visible" : "hidden";
}));
