"use strict";

const byId = (id) => document.getElementById(id);
const dataset = byId("dataset");
const metric = byId("metric");
const number = new Intl.NumberFormat("en", { maximumFractionDigits: 2 });
const displayOrder = ["NYX", "Hurricane", "Miranda", "SCALE", "CESM", "JHTDB"];
const codecOrder = ["ZFP", "PFPL", "SPERR", "SZ3", "Falcons"];
// Versioned asset URLs prevent cached preview figures from being mixed with
// the updated measurement tables while GitHub Pages caches are refreshed.
const dataVersion = "20261111-compact-v2";
const qualityVersion = "20261111-fidelity-v3";
const qualityNames = {
  ssim_rd: "RD · SSIM",
  pcc_rd: "RD · Pearson correlation",
  nrmse_rd: "RD · NRMSE",
  spectral_l1_rd: "RD · Spectral power L1 error",
  spectral_l2_rd: "RD · Spectral power L2 error",
  fourier_l2_rd: "RD · Fourier L2 error",
  field_acf_rd: "RD · Field autocorrelation change",
  error_acf_rd: "Rate · Error autocorrelation",
  cross_mean_rd: "RD · Mean cross-variable correlation change",
  cross_max_rd: "RD · Maximum cross-variable correlation change",
};
const metricNames = {
  rd: "RD · PSNR",
  ratio: "Compression ratio table",
  throughput: "Compression and decompression throughput",
  "pareto-compress": "Pareto frontier · 1E-3",
  "pareto-decompress": "Decompression Pareto by dataset · 1E-3",
  ...qualityNames,
};
const metricGroups = {
  "Performance": ["ratio", "throughput", "pareto-compress", "pareto-decompress"],
  "Field fidelity (rate–distortion)": ["rd", "ssim_rd", "pcc_rd", "nrmse_rd"],
  "Spatial and spectral": ["spectral_l1_rd", "spectral_l2_rd", "fourier_l2_rd", "field_acf_rd", "error_acf_rd"],
  "Cross-variable": ["cross_mean_rd", "cross_max_rd"],
};
const descriptions = {
  rd: "PSNR versus bits per value for error bounds 1E-1 through 1E-5.",
  throughput: "Top: compression. Bottom: decompression. Bars cover 1E-2 through 1E-5.",
  "pareto-compress": "Compression ratio versus throughput at 1E-3. Rings identify nondominated codecs.",
  "pareto-decompress": "Compression ratio versus decompression throughput at 1E-3. Rings identify nondominated codecs.",
};
const upperLeft = ["↖", "Upper left is better"];
const lowerLeft = ["↙", "Lower left is better"];
const upperRight = ["↗", "Upper right is better"];
const figureDirections = {
  rd: upperLeft,
  ratio: ["↑", "Higher compression ratios are better"],
  throughput: ["↑", "Higher throughput is better"],
  "pareto-compress": upperRight,
  "pareto-decompress": upperRight,
  ssim_rd: upperLeft,
  pcc_rd: upperLeft,
  nrmse_rd: lowerLeft,
  spectral_l1_rd: lowerLeft,
  spectral_l2_rd: lowerLeft,
  fourier_l2_rd: lowerLeft,
  field_acf_rd: lowerLeft,
  error_acf_rd: ["↓", "Lower values mean weaker error autocorrelation"],
  cross_mean_rd: lowerLeft,
  cross_max_rd: lowerLeft,
};

function boundName(value) {
  return Number(value).toExponential().toUpperCase();
}

function replaceOptions(select, options, fallback) {
  const previous = select.value;
  select.replaceChildren(...options.map(([value, label]) => new Option(label, value)));
  select.value = options.some(([value]) => value === previous) ? previous : fallback;
}

function replaceMetricOptions(options) {
  const previous = metric.value;
  const available = new Map(options);
  const groups = [];
  for (const [label, keys] of Object.entries(metricGroups)) {
    const choices = keys.filter(key => available.has(key));
    if (!choices.length) continue;
    const group = document.createElement("optgroup");
    group.label = label;
    group.append(...choices.map(key => new Option(available.get(key), key)));
    groups.push(group);
  }
  metric.replaceChildren(...groups);
  metric.value = available.has(previous) ? previous : "rd";
}

function updateFigureLink() {
  const url = new URL(window.location.href);
  url.searchParams.set("view_dataset", dataset.value);
  url.searchParams.set("view_figure", metric.value);
  url.searchParams.delete("view_bound");
  url.hash = "results";
  const link = url.toString();
  byId("figure-permalink").href = link;
  byId("ratio-permalink").href = link;
}

function figureName(metricValue, datasetValue) {
  if (metricValue === "pareto-compress") {
    return datasetValue === "all" ? "overall_pareto_1e-3" : "datasets_pareto_compress_1e-3";
  }
  if (metricValue === "pareto-decompress") return "datasets_pareto_decompress_1e-3";
  return (datasetValue === "all" ? "datasets" : datasetValue) + "_" + metricValue;
}

function renderFigure() {
  const figure = figureName(metric.value, dataset.value);
  const quality = qualityResults?.metrics[metric.value];
  const directory = quality ? "./data/quality/figures/" : "./data/sdrbench/figures/";
  const revision = quality ? qualityVersion : dataVersion;
  const image = byId("figure-image");
  const label = metricNames[metric.value];
  const isPareto = metric.value.startsWith("pareto-");
  const selection = dataset.value === "all" ? "SDRBench" : dataset.value;
  const multiDataset = isPareto && figure.startsWith("datasets_");
  const allDatasets = dataset.value === "all";
  const layout = multiDataset || (allDatasets && (metric.value === "rd" || (quality && !quality.cross))) ? "strip"
    : isPareto || (allDatasets && quality?.cross) ? "pair"
    : metric.value === "rd" || quality ? "single" : "wide";
  byId("figure-view").dataset.layout = layout;
  byId("figure-frame").tabIndex = layout === "strip" ? 0 : -1;
  image.src = directory + figure + ".png?v=" + revision;
  image.alt = label + " for " + (multiDataset ? "all dataset panels" : selection);
  byId("figure-image-link").href = image.src;
  byId("figure-pdf").href = directory + figure + ".pdf?v=" + revision;
  const fullRange = byId("figure-full-range");
  const fullFigure = figure + "_full";
  const hasFullRange = Boolean(quality && qualityResults.full_range_figures?.includes(fullFigure));
  fullRange.hidden = !hasFullRange;
  if (hasFullRange) fullRange.href = directory + fullFigure + ".png?v=" + revision;
  let description = quality?.description ?? descriptions[metric.value];
  if (quality) {
    description += " Error bounds: 1E-1 through 1E-5.";
    if (hasFullRange) description += " Each curve stops near the start of its high-rate plateau.";
    if (quality.cross) description += " Only the audited NYX, Hurricane and Miranda variable groups are shown; index alignment does not establish physical co-location.";
  }
  if (metric.value === "throughput" && dataset.value !== "all") {
    description = "Left: compression. Right: decompression. Bars cover 1E-2 through 1E-5.";
  }
  if (multiDataset) description += " The figure contains one panel per dataset.";
  if (figure === "overall_pareto_1e-3") description += " Compression and decompression are shown separately.";
  byId("figure-description").textContent = description;
}

const codecLabel = (codec) => codec === "SZ3" ? "SZ3.3" : codec;

function selectedPoints(run) {
  return run.table
    .filter((point) => dataset.value === "all" || point.dataset === dataset.value)
    .sort((a, b) => displayOrder.indexOf(a.dataset) - displayOrder.indexOf(b.dataset) ||
      codecOrder.indexOf(a.codec) - codecOrder.indexOf(b.codec));
}

function renderRatioTable(run) {
  const bounds = [...run.bounds].sort((a, b) => b - a);
  const headings = document.createElement("tr");
  for (const label of ["Dataset", "Codec", ...bounds.map(boundName)]) {
    const th = document.createElement("th");
    th.scope = "col";
    th.textContent = label;
    headings.append(th);
  }
  byId("ratio-columns").replaceChildren(headings);

  const groups = new Map();
  for (const point of selectedPoints(run)) {
    const key = point.dataset + "/" + point.codec;
    if (!groups.has(key)) groups.set(key, {dataset: point.dataset, codec: point.codec, ratios: new Map()});
    groups.get(key).ratios.set(point.alpha, point.ratio);
  }
  const fragment = document.createDocumentFragment();
  for (const row of groups.values()) {
    const tr = document.createElement("tr");
    tr.insertCell().textContent = row.dataset;
    const codec = document.createElement("th");
    codec.scope = "row";
    codec.textContent = codecLabel(row.codec);
    tr.append(codec);
    for (const alpha of bounds) {
      const value = row.ratios.get(alpha);
      tr.insertCell().textContent = value == null ? "—" : number.format(value);
    }
    fragment.append(tr);
  }
  byId("ratio-body").replaceChildren(fragment);
}

let results, qualityResults;

function updateFigure() {
  const isRatio = metric.value === "ratio";
  byId("figure-view").hidden = isRatio;
  byId("ratio-view").hidden = !isRatio;
  const plotTransform = qualityResults?.metrics[metric.value]?.plot_transform;
  const [arrow, direction] = plotTransform === "one_minus" ? lowerLeft : figureDirections[metric.value];
  byId("figure-direction-arrow").textContent = arrow;
  byId("figure-direction-text").textContent = direction;
  if (isRatio) {
    if (results) renderRatioTable(results);
  } else {
    renderFigure();
  }
  updateFigureLink();
}

function updateDataset() {
  const options = Object.entries(metricNames).filter(([key]) =>
    (key !== "pareto-decompress" || dataset.value !== "all") &&
    (key === "ratio" || (Object.hasOwn(qualityNames, key)
      ? (qualityResults && qualityResults.figures.includes(figureName(key, dataset.value)))
      : (!results || results.figures.includes(figureName(key, dataset.value))))));
  replaceMetricOptions(options);
  updateFigure();
}

async function loadResults() {
  const response = await fetch("./data/results.json?v=" + dataVersion, { cache: "no-cache" });
  if (!response.ok) throw new Error("Results could not be loaded");
  const manifest = await response.json();
  const run = manifest.sdrbench ?? manifest.runs?.sdrbench;
  if (!run) throw new Error("SDRBench results are missing");
  byId("sdrbench-download-title").textContent = "SDRBench";
  byId("sdrbench-download-detail").textContent = "Audited scientific-array measurements";
  const options = [["all", "All datasets"], ...displayOrder
    .filter((name) => run.datasets.includes(name))
    .map((name) => [name, name])];
  replaceOptions(dataset, options, "all");

  const list = byId("backend-list");
  for (const codec of codecOrder) {
    const backend = manifest.backends[codec];
    if (!backend) continue;
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.href = backend.url + "/commit/" + backend.commit;
    link.append(codec + " ");
    const commit = document.createElement("code");
    commit.textContent = backend.commit.slice(0, 8);
    link.append(commit);
    item.append(link);
    list.append(item);
  }

  results = run;
  qualityResults = manifest.quality_rd;
  const requested = new URLSearchParams(window.location.search);
  const datasetValue = requested.get("view_dataset");
  if ([...dataset.options].some(option => option.value === datasetValue)) dataset.value = datasetValue;
  updateDataset();
  const requestedFigure = requested.get("view_figure");
  const figureValue = requestedFigure === "ssim_loss_rd" ? "ssim_rd" : requestedFigure;
  if ([...metric.options].some(option => option.value === figureValue)) metric.value = figureValue;
  updateFigure();
}

dataset.addEventListener("change", updateDataset);
metric.addEventListener("change", updateFigure);
updateDataset();

loadResults().catch(() => {
  byId("ratio-body").rows[0].cells[0].textContent = "Use the CSV download for compression ratios.";
});
