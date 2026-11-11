// Run on HPDPS-8: node tests/test_web_controls.js /path/to/site-root
// Exercises figure controls, paths, and the offline fallback using a minimal DOM.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(process.argv[2] || path.join(__dirname, "../docs"));
const source = fs.readFileSync(path.join(root, "site.js"), "utf8");
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
const manifest = JSON.parse(fs.readFileSync(path.join(root, "data/results.json"), "utf8"));
const revision = source.match(/const dataVersion = "([^"]+)"/)[1];
const qualityRevision = source.match(/const qualityVersion = "([^"]+)"/)[1];
const qualityTypes = ["ssim_rd", "pcc_rd", "nrmse_rd", "spectral_l1_rd",
  "spectral_l2_rd", "fourier_l2_rd", "field_acf_rd", "error_acf_rd"];
const crossTypes = ["cross_mean_rd", "cross_max_rd"];
const expectedArrows = {
  ratio: "↑", throughput: "↑", "pareto-compress": "↗", "pareto-decompress": "↗",
  rd: "↖", ssim_rd: "↖", pcc_rd: "↖", error_acf_rd: "↓",
};

class Element {
  constructor(tag = "") {
    this.tag = tag;
    this.value = "";
    this.options = [];
    this.children = [];
    this.dataset = {};
    this.listeners = {};
    this.textContent = "";
    this.disabled = false;
    this.rows = [{ cells: [{ textContent: "" }] }];
  }
  addEventListener(name, fn) { this.listeners[name] = fn; }
  change() { this.listeners.change(); }
  click() { this.listeners.click(); }
  replaceChildren(...items) {
    this.groups = items.filter(item => item.tag === "optgroup");
    this.options = items.flatMap(item => item.tag === "optgroup" ? item.options : [item]);
    this.children = items.flatMap(item => item.tag === "fragment" ? item.children : [item]);
  }
  append(...items) { this.options.push(...items); this.children.push(...items); }
  insertCell() { const cell = new Element("td"); this.children.push(cell); return cell; }
}
class Option {
  constructor(label, value) { this.label = label; this.value = value; }
}
function makeEnvironment(offline, search = "") {
  const elements = {};
  const document = {
    getElementById(id) { return elements[id] ||= new Element(); },
    createDocumentFragment() { return new Element("fragment"); },
    createElement(tag) { return new Element(tag); },
  };
  elements.dataset = new Element(); elements.dataset.value = "all";
  elements.metric = new Element(); elements.metric.value = "rd";
  const fetched = [];
  async function fetch(url) {
    fetched.push(url);
    if (offline) throw new Error("offline");
    return {ok: true, json: async () => manifest};
  }
  const window = {location: new URL("https://example.test/LFCBenchmark/" + search)};
  vm.runInNewContext(source, {document, Option, fetch, Intl, window, URL, URLSearchParams});
  return {elements, fetched};
}
function expectedFigure(kind, dataset) {
  if (kind === "pareto-compress") return dataset === "all" ? "overall_pareto_1e-3" : "datasets_pareto_compress_1e-3";
  if (kind === "pareto-decompress") return "datasets_pareto_decompress_1e-3";
  return (dataset === "all" ? "datasets" : dataset) + "_" + kind;
}

async function main() {
  const {elements:e, fetched} = makeEnvironment(false);
  await new Promise(setImmediate);
  assert.deepEqual(fetched, ["./data/results.json?v=" + revision]);
  assert.equal(e["sdrbench-download-title"].textContent, "SDRBench");
  assert.equal(e["sdrbench-download-detail"].textContent, "Audited scientific-array measurements");
  assert(!html.includes("SDRBench preview"));
  assert(html.includes(">single threads<"));
  assert(!html.includes('id="measurements-view"'));
  assert(html.includes("native-source.bundle?v=" + revision));
  assert(fs.existsSync(path.join(root, "data/sdrbench/native-source.bundle")));
  const datasets = ["all", "NYX", "Hurricane", "Miranda", "SCALE", "CESM", "JHTDB"];
  assert.deepEqual(e.dataset.options.map(o => o.value), datasets);
  assert.deepEqual(e.metric.groups.map(group => group.label), ["Performance", "Field fidelity (rate–distortion)", "Spatial and spectral", "Cross-variable"]);
  assert.equal(e.metric.options.find(option => option.value === "rd").label, "RD · PSNR");
  for (const dataset of datasets) {
    e.dataset.value = dataset;
    e.dataset.change();
    const types = ["ratio", "throughput", "pareto-compress"];
    if (dataset !== "all") types.push("pareto-decompress");
    types.push("rd", ...qualityTypes);
    if (["all", "NYX", "Hurricane", "Miranda"].includes(dataset)) types.push(...crossTypes);
    assert.deepEqual(e.metric.options.map(o => o.value), types);
    for (const kind of types) {
      e.metric.value = kind;
      e.metric.change();
      const isRatio = kind === "ratio";
      assert.equal(e["ratio-view"].hidden, !isRatio);
      assert.equal(e["figure-view"].hidden, isRatio);
      assert.equal(e["figure-direction-arrow"].textContent, expectedArrows[kind] ?? "↙");
      assert(e["figure-direction-text"].textContent);
      const link = new URL(e[isRatio ? "ratio-permalink" : "figure-permalink"].href);
      assert.equal(link.hash, "#results");
      assert.equal(link.searchParams.get("view_dataset"), dataset);
      assert.equal(link.searchParams.get("view_figure"), kind);
      assert(!link.searchParams.has("view_bound"));
      if (isRatio) {
        assert.deepEqual(e["ratio-columns"].children[0].children.map(cell => cell.textContent),
          ["Dataset", "Codec", "1E-1", "1E-2", "1E-3", "1E-4", "1E-5", "1E-6"]);
        const table = e["ratio-body"].children;
        assert.equal(table.length, dataset === "all" ? 30 : 5);
        const first = table[0].children.map(cell => cell.textContent);
        const source = manifest.sdrbench.table.find(row => row.dataset === first[0] && row.codec === "ZFP" && row.alpha === 0.001);
        assert.equal(first[4], new Intl.NumberFormat("en", {maximumFractionDigits: 2}).format(source.ratio));
        continue;
      }
      const figure = expectedFigure(kind, dataset);
      const isQuality = qualityTypes.includes(kind) || crossTypes.includes(kind);
      const directory = isQuality ? "./data/quality/figures/" : "./data/sdrbench/figures/";
      const version = isQuality ? qualityRevision : revision;
      const image = directory + figure + ".png?v=" + version;
      const pdf = directory + figure + ".pdf?v=" + version;
      assert.equal(e["figure-image"].src, image);
      assert.equal(e["figure-image-link"].href, image);
      assert.equal(e["figure-pdf"].href, pdf);
      const fullRange = e["figure-full-range"];
      const fullFigure = figure + "_full";
      const hasFullRange = isQuality && manifest.quality_rd.full_range_figures.includes(fullFigure);
      assert.equal(fullRange.hidden, !hasFullRange);
      if (hasFullRange) {
        assert.equal(fullRange.href, directory + fullFigure + ".png?v=" + version);
        assert(fs.existsSync(path.join(root, directory, fullFigure + ".png")));
      }
      assert(fs.existsSync(path.join(root, image.split("?")[0])));
      assert(fs.existsSync(path.join(root, pdf.split("?")[0])));
    }
  }
  const offline = makeEnvironment(true).elements;
  await new Promise(setImmediate);
  offline.dataset.value = "NYX"; offline.dataset.change();
  offline.metric.value = "ratio"; offline.metric.change();
  assert.equal(offline["ratio-view"].hidden, false);
  assert(offline["ratio-body"].rows[0].cells[0].textContent.includes("CSV download"));
  offline.metric.value = "rd"; offline.metric.change();
  assert.equal(offline["figure-image"].src, "./data/sdrbench/figures/NYX_rd.png?v=" + revision);
  const deep = makeEnvironment(false, "?view_dataset=CESM&view_figure=ssim_rd&view_bound=0.0001").elements;
  await new Promise(setImmediate);
  assert.equal(deep.dataset.value, "CESM"); assert.equal(deep.metric.value, "ssim_rd");
  assert(deep["figure-image"].src.includes("CESM_ssim_rd.png"));
  assert(!new URL(deep["figure-permalink"].href).searchParams.has("view_bound"));
  const legacy = makeEnvironment(false, "?view_dataset=CESM&view_figure=ssim_loss_rd").elements;
  await new Promise(setImmediate);
  assert.equal(legacy.metric.value, "ssim_rd");
  const invalid = makeEnvironment(false, "?view_dataset=unknown&view_figure=unknown").elements;
  await new Promise(setImmediate);
  assert.equal(invalid.dataset.value, "all"); assert.equal(invalid.metric.value, "rd");
  const unavailable = makeEnvironment(false, "?view_dataset=CESM&view_figure=cross_mean_rd").elements;
  await new Promise(setImmediate);
  assert.equal(unavailable.dataset.value, "CESM"); assert.equal(unavailable.metric.value, "rd");
  console.log("Web figure controls: all datasets, chart directions, ratio table, and offline fallback passed.");
}
main().catch(error => { console.error(error); process.exitCode = 1; });
