/* AI Companies bubble chart — D3-driven. */

const payload = JSON.parse(document.getElementById("company-data").textContent);
const COMPANIES = payload.companies;

/* ───── axis fields ───── */

const AXIS_FIELDS = [
  { key: "founded_year", label: "Founded", noun: "founding year", format: d => d, scale: "linear" },
  { key: "company_value", label: "Company value ($B)", noun: "company value", format: fmtMoney, scale: "sqrt" },
  { key: "revenue", label: "Revenue ($B)", noun: "revenue", format: fmtMoney, scale: "sqrt" },
  { key: "profit_loss", label: "Profit / Loss ($B)", noun: "profit / loss", format: fmtMoney, scale: "linear" },
];
const AXIS_BY_KEY = Object.fromEntries(AXIS_FIELDS.map(f => [f.key, f]));

function fmtMoney(v) {
  if (v == null) return "—";
  const abs = Math.abs(v);
  if (abs >= 1000) return `$${(v / 1000).toFixed(1)}T`;
  if (abs >= 1)    return `$${v.toFixed(1)}B`;
  return `$${(v * 1000).toFixed(0)}M`;
}

/* ───── country → color ───── */

const COUNTRY_COLORS = {
  US: "var(--sol-blue)",
  CN: "var(--sol-red)",
  GB: "var(--sol-violet)",
  IL: "var(--sol-cyan)",
  AE: "var(--sol-yellow)",
  KR: "var(--sol-magenta)",
  JP: "var(--sol-orange)",
  TW: "var(--sol-green)",
};
const OTHER_COLOR = "var(--sol-base0)";
function colorFor(country) { return COUNTRY_COLORS[country] || OTHER_COLOR; }

/* ───── filter state ───── */

const uniq = (arr) => Array.from(new Set(arr)).filter(v => v != null);
const COUNTRY_NAMES = Object.fromEntries(
  COMPANIES.map(c => [c.hq_country, c.hq_country_name]).filter(([k]) => k)
);
const countryName = (code) => COUNTRY_NAMES[code] || code;
const allCountries = uniq(COMPANIES.map(c => c.hq_country))
  .sort((a, b) => countryName(a).localeCompare(countryName(b)));
const allStatuses = uniq(COMPANIES.map(c => c.public_or_private)).sort();
const allCategories = uniq(COMPANIES.flatMap(c => c.categories)).sort();
const allConfidence = ["high", "medium", "low"];

const filters = {
  country: new Set(allCountries),
  public_or_private: new Set(allStatuses),
  category: new Set(allCategories),
  data_confidence: new Set(allConfidence),
};

let xKey = "founded_year";
let yKey = "company_value";
let selectedId = null;

/* ───── scales ───── */

const MARGIN = { top: 16, right: 24, bottom: 48, left: 72 };
const SIZE_RANGE = [6, 42];
const NO_VALUE_RADIUS = 4;

function rangeOf(key) {
  const vals = COMPANIES.map(c => c[key]).filter(v => v != null && !Number.isNaN(v));
  if (vals.length === 0) return [0, 1];
  return [Math.min(...vals), Math.max(...vals)];
}
const DOMAINS = Object.fromEntries(AXIS_FIELDS.map(f => [f.key, rangeOf(f.key)]));
const VALUE_DOMAIN = rangeOf("company_value");

function makeScale(field) {
  const [lo, hi] = DOMAINS[field.key];
  const factory = field.scale === "sqrt" ? d3.scaleSqrt : d3.scaleLinear;
  if (field.key === "founded_year") return d3.scaleLinear().domain([lo - 1, hi + 1]);
  if (field.key === "profit_loss") {
    const span = Math.max(Math.abs(lo), Math.abs(hi));
    return d3.scaleLinear().domain([-span * 1.05, span * 1.05]);
  }
  return factory().domain([0, hi * 1.05]);
}

const sizeScale = d3.scaleSqrt().domain([0, VALUE_DOMAIN[1]]).range(SIZE_RANGE);

/* ───── DOM setup ───── */

const svg = d3.select("#chart");
const chartRoot = svg.append("g");
const gridLayer  = chartRoot.append("g").attr("class", "grid");
const xAxisG = chartRoot.append("g").attr("class", "axis axis-x");
const yAxisG = chartRoot.append("g").attr("class", "axis axis-y");
const zeroLine = chartRoot.append("line").attr("class", "zero-line").style("display", "none");
const bubbleLayer = chartRoot.append("g").attr("class", "bubbles");
const labelLayer  = chartRoot.append("g").attr("class", "labels");
const xLabel = chartRoot.append("text").attr("class", "axis-label").attr("text-anchor", "middle");
const yLabel = chartRoot.append("text").attr("class", "axis-label").attr("text-anchor", "middle").attr("transform", "rotate(-90)");

const container = document.getElementById("chart-container");
let width = 0, height = 0;

function buildAxisSelects() {
  for (const [id, current] of [["x-axis", xKey], ["y-axis", yKey]]) {
    const sel = d3.select("#" + id);
    sel.selectAll("option")
      .data(AXIS_FIELDS).enter()
      .append("option")
      .attr("value", d => d.key)
      .text(d => d.label);
    sel.property("value", current);
    sel.on("change", function () {
      if (id === "x-axis") xKey = this.value; else yKey = this.value;
      render({ duration: 750 });
    });
  }
}

function buildFilters() {
  const groups = [
    { key: "country", values: allCountries, label: (v) => `${countryName(v)} (${COMPANIES.filter(c => c.hq_country === v).length})`, swatch: colorFor },
    { key: "public_or_private", values: allStatuses, label: (v) => v.charAt(0).toUpperCase() + v.slice(1) },
    { key: "category", values: allCategories, label: (v) => v.replace(/_/g, " ") },
    { key: "data_confidence", values: allConfidence, label: (v) => v.charAt(0).toUpperCase() + v.slice(1) },
  ];
  for (const g of groups) {
    const container = document.querySelector(`.filter-group[data-filter="${g.key}"] .filter-options`);
    container.innerHTML = "";
    for (const v of g.values) {
      const label = document.createElement("label");
      label.className = "filter-option";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.autocomplete = "off";
      cb.checked = true;
      cb.addEventListener("change", () => {
        if (cb.checked) filters[g.key].add(v); else filters[g.key].delete(v);
        render({ duration: 400 });
      });
      label.appendChild(cb);
      if (g.swatch) {
        const dot = document.createElement("span");
        dot.className = "swatch";
        dot.style.background = g.swatch(v);
        label.appendChild(dot);
      }
      const text = document.createElement("span");
      text.textContent = g.label(v);
      label.appendChild(text);
      container.appendChild(label);
    }
  }
}

/* ───── filtering ───── */

function passesNonAxisFilters(c) {
  if (!filters.country.has(c.hq_country)) return false;
  if (!filters.public_or_private.has(c.public_or_private)) return false;
  if (!c.categories.some(cat => filters.category.has(cat))) return false;
  if (!filters.data_confidence.has(c.data_confidence)) return false;
  return true;
}

function passes(c) {
  return passesNonAxisFilters(c) && c[xKey] != null && c[yKey] != null;
}

/* ───── render ───── */

function resize() {
  width = container.clientWidth;
  height = container.clientHeight;
  svg.attr("viewBox", `0 0 ${width} ${height}`);
  render({ duration: 0 });
}

function render({ duration = 400 } = {}) {
  if (!width || !height) return;
  const innerW = width - MARGIN.left - MARGIN.right;
  const innerH = height - MARGIN.top - MARGIN.bottom;
  chartRoot.attr("transform", `translate(${MARGIN.left},${MARGIN.top})`);

  const xField = AXIS_BY_KEY[xKey];
  const yField = AXIS_BY_KEY[yKey];
  const xScale = makeScale(xField).range([0, innerW]);
  const yScale = makeScale(yField).range([innerH, 0]);

  const xAxis = d3.axisBottom(xScale).ticks(Math.max(4, innerW / 90)).tickFormat(xField.format);
  const yAxis = d3.axisLeft(yScale).ticks(Math.max(4, innerH / 60)).tickFormat(yField.format);
  const ease = d3.easeCubicInOut;

  xAxisG.attr("transform", `translate(0,${innerH})`)
    .transition().duration(duration).ease(ease).call(xAxis);
  yAxisG.transition().duration(duration).ease(ease).call(yAxis);

  // gridlines
  const gridXAxis = d3.axisBottom(xScale).ticks(Math.max(4, innerW / 90)).tickSize(-innerH).tickFormat("");
  const gridYAxis = d3.axisLeft(yScale).ticks(Math.max(4, innerH / 60)).tickSize(-innerW).tickFormat("");
  gridLayer.selectAll(".grid-x").data([null]).join("g").attr("class", "grid grid-x")
    .attr("transform", `translate(0,${innerH})`).transition().duration(duration).ease(ease).call(gridXAxis);
  gridLayer.selectAll(".grid-y").data([null]).join("g").attr("class", "grid grid-y")
    .transition().duration(duration).ease(ease).call(gridYAxis);

  // zero line for profit/loss
  zeroLine.style("display", yKey === "profit_loss" ? null : "none")
    .transition().duration(duration).ease(ease)
    .attr("x1", 0).attr("x2", innerW)
    .attr("y1", yScale(0)).attr("y2", yScale(0));

  xLabel.attr("x", innerW / 2).attr("y", innerH + 38).text(xField.label);
  yLabel.attr("x", -innerH / 2).attr("y", -52).text(yField.label);

  // bubbles
  const visible = COMPANIES.filter(passes);
  document.getElementById("status").textContent = `${visible.length} / ${COMPANIES.length} companies`;
  renderExclusions();

  const join = bubbleLayer.selectAll("circle.bubble")
    .data(visible, d => d.id);

  join.exit()
    .transition().duration(duration).ease(ease)
    .attr("r", 0).style("opacity", 0).remove();

  const entered = join.enter().append("circle")
    .attr("class", "bubble")
    .attr("fill", d => colorFor(d.hq_country))
    .attr("fill-opacity", 0.7)
    .attr("cx", d => xScale(d[xKey]))
    .attr("cy", d => yScale(d[yKey]))
    .attr("r", 0)
    .style("opacity", 0)
    .on("mouseenter", (event, d) => showLabel(d))
    .on("mouseleave", () => clearLabel())
    .on("click", (event, d) => selectCompany(d.id));

  entered.merge(join)
    .classed("selected", d => d.id === selectedId)
    .transition().duration(duration).ease(ease)
    .attr("cx", d => xScale(d[xKey]))
    .attr("cy", d => yScale(d[yKey]))
    .attr("r", d => d.company_value != null ? sizeScale(d.company_value) : NO_VALUE_RADIUS)
    .style("opacity", 1);
}

/* ───── axis exclusions note ───── */

function renderExclusions() {
  const el = document.getElementById("axis-exclusions");
  el.innerHTML = "";
  const eligible = COMPANIES.filter(passesNonAxisFilters);
  for (const axisKey of [xKey, yKey]) {
    const field = AXIS_BY_KEY[axisKey];
    const missing = eligible
      .filter(c => c[axisKey] == null)
      .sort((a, b) => a.name.localeCompare(b.name));
    if (!missing.length) continue;
    const p = document.createElement("p");
    p.appendChild(document.createTextNode("Not shown: "));
    missing.forEach((c, i) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "exclusion-link";
      btn.textContent = c.name;
      btn.addEventListener("click", () => selectCompany(c.id));
      p.appendChild(btn);
      if (i < missing.length - 1) p.appendChild(document.createTextNode(", "));
    });
    p.appendChild(document.createTextNode(` — ${field.noun} is unknown.`));
    el.appendChild(p);
  }
}

/* ───── hover label ───── */

function showLabel(d) {
  const xField = AXIS_BY_KEY[xKey];
  const yField = AXIS_BY_KEY[yKey];
  const innerW = width - MARGIN.left - MARGIN.right;
  const innerH = height - MARGIN.top - MARGIN.bottom;
  const xScale = makeScale(xField).range([0, innerW]);
  const yScale = makeScale(yField).range([innerH, 0]);
  bubbleLayer.selectAll("circle.bubble").filter(b => b.id === d.id).raise();
  labelLayer.selectAll("text").remove();
  labelLayer.append("text")
    .attr("class", "bubble-label")
    .attr("x", xScale(d[xKey]))
    .attr("y", yScale(d[yKey]))
    .text(d.stock_ticker || d.name);
}
function clearLabel() { labelLayer.selectAll("text").remove(); }

/* ───── selection + details ───── */

function selectCompany(id) {
  selectedId = id;
  bubbleLayer.selectAll("circle.bubble").classed("selected", d => d.id === id);
  renderDetails(COMPANIES.find(c => c.id === id));
}

function splitSentences(text) {
  if (!text) return [];
  // Split on sentence boundary: period/question/exclaim followed by space + capital/number,
  // which preserves abbreviations like "U.S." or "e.g.".
  const parts = text.split(/(?<=[.!?])\s+(?=[A-Z0-9])/);
  return parts.map(p => p.trim().replace(/[.]$/, "")).filter(Boolean);
}

function titleCase(s) { return s.replace(/_/g, " ").replace(/\b\w/g, ch => ch.toUpperCase()); }

function field(label, content) {
  if (content == null || (Array.isArray(content) && !content.length)) return null;
  const el = document.createElement("div");
  el.className = "detail-field";
  const lbl = document.createElement("span");
  lbl.className = "detail-label";
  lbl.textContent = label;
  el.appendChild(lbl);
  const val = document.createElement("div");
  val.className = "detail-value";
  if (typeof content === "string") val.textContent = content;
  else val.appendChild(content);
  el.appendChild(val);
  return el;
}

function listOf(items) {
  const ul = document.createElement("ul");
  for (const it of items) {
    const li = document.createElement("li");
    if (it instanceof Node) li.appendChild(it); else li.textContent = it;
    ul.appendChild(li);
  }
  return ul;
}

function link(href, text) {
  const a = document.createElement("a");
  a.href = href; a.textContent = text || href;
  a.target = "_blank"; a.rel = "noopener";
  return a;
}

function renderDetails(c) {
  const empty = document.getElementById("details-empty");
  const body = document.getElementById("details-body");
  if (!c) { empty.hidden = false; body.hidden = true; return; }
  empty.hidden = true; body.hidden = false;
  body.innerHTML = "";

  const h = document.createElement("h2");
  const swatch = document.createElement("span");
  swatch.className = "swatch-inline";
  swatch.style.background = colorFor(c.hq_country);
  h.appendChild(swatch);
  h.appendChild(document.createTextNode(c.name));
  body.appendChild(h);

  const fields = [];
  fields.push(field("Year founded", c.founded_year != null ? String(c.founded_year) : null));
  if (c.hq_country || c.hq_city) fields.push(field("HQ", [c.hq_city, countryName(c.hq_country)].filter(Boolean).join(", ")));
  fields.push(field("Public / Private", c.public_or_private ? titleCase(c.public_or_private) : null));
  fields.push(field("Stock ticker", c.stock_ticker));
  fields.push(field("Categories", c.categories.length ? c.categories.map(titleCase).join(", ") : null));

  if (c.ceo) {
    if (c.ceo.wikipedia_url) fields.push(field("CEO", link(c.ceo.wikipedia_url, c.ceo.name)));
    else fields.push(field("CEO", c.ceo.name));
  }
  if (c.founders.length) {
    const nodes = c.founders.map(p => p.wikipedia_url ? link(p.wikipedia_url, p.name) : document.createTextNode(p.name));
    fields.push(field("Founders", listOf(nodes)));
  }
  if (c.gov_contracts.length) fields.push(field("Government contracts", c.gov_contracts.join(", ")));

  const govSentences = splitSentences(c.gov_contract_notes);
  if (govSentences.length) fields.push(field("Government contract notes", listOf(govSentences)));
  const regSentences = splitSentences(c.regulatory_actions);
  if (regSentences.length) fields.push(field("Regulatory actions", listOf(regSentences)));
  const noteSentences = splitSentences(c.notes);
  if (noteSentences.length) fields.push(field("Notes", listOf(noteSentences)));

  if (c.sources.length) {
    const links = c.sources.map(url => link(url, shortenUrl(url)));
    fields.push(field("Sources", listOf(links)));
  }

  for (const f of fields) if (f) body.appendChild(f);
}

function shortenUrl(u) {
  try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return u; }
}

/* ───── theme ───── */

const THEME_KEY = "ai-companies-theme";
function applyTheme(t) {
  document.documentElement.setAttribute("data-theme", t);
  document.getElementById("theme-toggle").textContent = t === "dark" ? "Light" : "Dark";
}
function toggleTheme() {
  const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
  localStorage.setItem(THEME_KEY, next);
  applyTheme(next);
}
applyTheme(localStorage.getItem(THEME_KEY) || "dark");
document.getElementById("theme-toggle").addEventListener("click", toggleTheme);

/* ───── boot ───── */

buildAxisSelects();
buildFilters();
new ResizeObserver(resize).observe(container);
resize();
