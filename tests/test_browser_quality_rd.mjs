// Run on HPDPS-8 with local HTTP and geckodriver services.
import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';

const driver = process.env.WEBDRIVER_URL || 'http://127.0.0.1:17772';
const page = process.env.BENCHMARK_URL || 'http://127.0.0.1:18766/';
async function command(method, path, body) {
  const response = await fetch(driver + path, {method, headers:{'content-type':'application/json'},
    ...(body === undefined ? {} : {body:JSON.stringify(body)})});
  const result = await response.json();
  if (!response.ok || result.value?.error) throw new Error(JSON.stringify(result));
  return result.value;
}
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
let session;
try {
  const created = await command('POST', '/session', {capabilities:{alwaysMatch:{browserName:'firefox',
    'moz:firefoxOptions':{args:['-headless']}}}});
  session = created.sessionId;
  const base = '/session/' + session;
  const execute = script => command('POST', base + '/execute/sync', {script,args:[]});
  const select = async (id, value) => execute(`const s=document.getElementById(${JSON.stringify(id)});
    s.value=${JSON.stringify(value)}; s.dispatchEvent(new Event('change'));`);
  const waitForImage = async stem => {
    await execute('document.getElementById("figure-image").scrollIntoView({block:"center",behavior:"instant"});');
    let ready = false;
    for (let i=0; i<100; i++) {
      ready = await execute(`const i=document.getElementById('figure-image');
        return i.src.includes(${JSON.stringify('/' + stem + '.png')}) && i.complete && i.naturalWidth > 0;`);
      if (ready) break;
      await sleep(100);
    }
    assert(ready, 'image did not load: ' + stem);
  };
  await command('POST', base + '/window/rect', {width:1440,height:1000});
  await command('POST', base + '/url', {url:page});
  let ready = false;
  for (let i=0; i<100; i++) {
    ready = await execute('return [...document.getElementById("metric").options].some(x=>x.value==="ssim_rd");');
    if (ready) break;
    await sleep(100);
  }
  assert(ready, 'quality figure choices did not load');
  const groups = await execute('return [...document.querySelectorAll("#metric optgroup")].map(x=>x.label);');
  assert.deepEqual(groups,['Performance','Field fidelity (rate–distortion)','Spatial and spectral','Cross-variable']);
  await waitForImage('datasets_rd');
  const strip = await execute('const i=document.getElementById("figure-image"); return {aspect:i.naturalWidth/i.naturalHeight,height:i.getBoundingClientRect().height};');
  assert(strip.aspect > 4 && strip.height < 300, 'combined RD plot should be a compact row');
  const overview = await execute(`return {
    threads: document.getElementById('result-status').textContent,
    arrow: document.getElementById('figure-direction-arrow').textContent,
    direction: document.querySelector('.figure-direction strong').textContent,
    visibleTables: [...document.querySelectorAll('#results table')].filter(table => table.getClientRects().length).length
  };`);
  assert.deepEqual(overview,{threads:'single threads',arrow:'↖',direction:'Upper left is better',visibleTables:0});
  await select('metric', 'throughput');
  assert.equal(await execute('return document.getElementById("figure-direction-text").textContent;'),'Higher throughput is better');
  await select('metric', 'ssim_rd');
  await waitForImage('datasets_ssim_rd');
  const description = await execute('return document.getElementById("figure-description").textContent;');
  assert(description.startsWith('Median field SSIM') && description.includes('1E-1 through 1E-5'));
  const fullRange = await execute('const link=document.getElementById("figure-full-range"); return {hidden:link.hidden,path:new URL(link.href).pathname};');
  assert(!fullRange.hidden && fullRange.path.endsWith('/datasets_ssim_rd_full.png'));
  await select('metric', 'ratio');
  const ratio = await execute(`return {visible:!document.getElementById('ratio-view').hidden,
    figureHidden:document.getElementById('figure-view').hidden,
    bounds:[...document.querySelectorAll('#ratio-columns th')].slice(2).map(x=>x.textContent),
    rows:document.getElementById('ratio-body').rows.length};`);
  assert.deepEqual(ratio,{visible:true,figureHidden:true,bounds:['1E-1','1E-2','1E-3','1E-4','1E-5','1E-6'],rows:30});
  await select('dataset', 'NYX');
  assert.equal(await execute('return document.getElementById("ratio-body").rows.length;'),5);
  await select('metric', 'ssim_rd');
  await waitForImage('NYX_ssim_rd');
  await select('metric', 'pcc_rd');
  await waitForImage('NYX_pcc_rd');
  assert((await execute('return document.getElementById("figure-description").textContent;')).startsWith('Median Pearson correlation'));
  assert.equal(await execute('return document.getElementById("figure-direction-arrow").textContent;'),'↖');
  const permalink = await execute('return document.getElementById("figure-permalink").href;');
  await command('POST', base + '/url', {url:permalink});
  for (let i=0; i<100; i++) {
    ready = await execute('return document.getElementById("dataset").value==="NYX" && document.getElementById("metric").value==="pcc_rd";');
    if (ready) break;
    await sleep(100);
  }
  assert(ready, 'figure permalink did not restore the selected view');
  await waitForImage('NYX_pcc_rd');
  await select('metric', 'cross_mean_rd');
  await waitForImage('NYX_cross_mean_rd');
  assert((await execute('return document.getElementById("figure-description").textContent;')).includes('co-location'));
  await select('dataset', 'CESM');
  const cesmOptions = await execute('return [...document.getElementById("metric").options].map(x=>x.value);');
  assert(!cesmOptions.includes('cross_mean_rd') && !cesmOptions.includes('cross_max_rd'));
  await select('metric', 'spectral_l1_rd');
  await waitForImage('CESM_spectral_l1_rd');
  await select('dataset', 'all');
  await select('metric', 'pcc_rd');
  await waitForImage('datasets_pcc_rd');
  await execute('document.getElementById("figure-image").scrollIntoView();');
  await sleep(800);
  if (process.env.SCREENSHOT_PATH) {
    const screenshot = await command('GET', base + '/screenshot');
    await writeFile(process.env.SCREENSHOT_PATH, Buffer.from(screenshot, 'base64'));
  }
  await command('POST', base + '/window/rect', {width:390,height:844});
  const mobile = await execute('const f=document.getElementById("figure-frame"); return {window:document.documentElement.clientWidth,page:document.documentElement.scrollWidth,plotWidth:f.clientWidth,plotContent:f.scrollWidth};');
  assert(mobile.page <= mobile.window + 1, 'unexpected mobile page overflow: ' + JSON.stringify(mobile));
  assert(mobile.plotContent > mobile.plotWidth, 'dataset row must scroll within the plot on phones');
  console.log('Firefox browser: compact RD plots, ratio table, dataset switching and mobile layout passed.');
} finally {
  if (session) await command('DELETE', '/session/' + session);
}
