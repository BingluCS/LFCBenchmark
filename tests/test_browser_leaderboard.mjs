// Run on HPDPS-8 with a local geckodriver and HTTP server, not on the user's Mac.
import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';

const driver = process.env.WEBDRIVER_URL || 'http://127.0.0.1:17771';
const page = process.env.BENCHMARK_URL || 'http://127.0.0.1:18765/';
async function command(method, path, body) {
  const response = await fetch(driver + path, {method,headers:{'content-type':'application/json'},
    ...(body === undefined ? {} : {body:JSON.stringify(body)})});
  const result = await response.json();
  if (!response.ok || result.value?.error) throw new Error(JSON.stringify(result));
  return result.value;
}
const sleep = ms => new Promise(resolve => setTimeout(resolve,ms));
let session;
try {
  const created = await command('POST','/session',{capabilities:{alwaysMatch:{browserName:'firefox',
    'moz:firefoxOptions':{args:['-headless']}}}});
  session=created.sessionId;
  const base='/session/'+session;
  const execute=script=>command('POST',base+'/execute/sync',{script,args:[]});
  await command('POST',base+'/window/rect',{width:1440,height:1000});
  await command('POST',base+'/url',{url:page});
  let ready=false;
  for(let i=0;i<50;i++){
    ready=await execute('return document.querySelectorAll("#rank-body tr").length === 5 && document.getElementById("rank-context").textContent.includes("NYX");');
    if(ready)break;
    await sleep(100);
  }
  assert(ready,'default ranking did not load');
  const initial=await execute('return {dataset:document.getElementById("rank-dataset").value,bound:document.getElementById("rank-bound").value,metric:document.getElementById("rank-metric").value,rows:[...document.querySelectorAll("#rank-body tr")].map(r=>r.cells[1].innerText)}');
  assert.equal(initial.dataset,'NYX');assert.equal(initial.bound,'0.001');assert.equal(initial.metric,'ratio');assert.equal(initial.rows.length,5);
  const hardware=await execute('return document.querySelector(".hardware-summary").innerText;');
  assert(hardware.includes('Intel Xeon Gold 6530') && hardware.includes('2.10 GHz base'));
  assert(hardware.includes('256 GiB DDR5-4800') && !hardware.includes('I/O clock'));
  assert(!(await execute('return document.body.innerText;')).includes('HPDPS-8'));
  const places=await execute('return [...document.querySelectorAll("#rank-body tr")].slice(0,3).map(r=>({name:r.className,first:getComputedStyle(r.cells[0]).backgroundColor,last:getComputedStyle(r.cells[r.cells.length-1]).backgroundColor}));');
  assert.deepEqual(places.map(p=>p.name),['rank-place-1','rank-place-2','rank-place-3']);
  assert.equal(new Set(places.map(p=>p.first)).size,3);
  assert(places.every(p=>p.first===p.last),'sticky cells should match their ranking row');
  await execute('document.getElementById("rank-metric").value="compress_MiB_s";document.getElementById("rank-metric").dispatchEvent(new Event("change"));');
  assert.equal(await execute('return document.getElementById("rank-score-heading").innerText;'),'Compression\nthroughput (MiB/s)');
  assert.equal(await execute('return document.getElementById("rank-col-compress_MiB_s").hidden;'),true);
  await execute('document.getElementById("rank-metric").value="spectral_l1";document.getElementById("rank-metric").dispatchEvent(new Event("change"));');
  const spectral=await execute('return {header:document.getElementById("rank-score-heading").innerText,first:document.querySelector("#rank-body tr").cells[1].innerText};');
  assert(spectral.header.includes('spectral'));
  const expected=await command('POST',base+'/execute/async',{script:`const done=arguments[arguments.length-1];
    fetch('data/leaderboard.json').then(r=>r.json()).then(d=>{const g=d.groups.find(x=>x.protocol.dataset==='NYX' && x.protocol.alpha===0.001);
      done(g.entries.slice().sort((a,b)=>a.metrics.spectral_l1-b.metrics.spectral_l1)[0].display_name);}).catch(e=>done(String(e)));`,args:[]});
  assert.equal(spectral.first,expected);
  await execute('document.getElementById("rank-dataset").value="CESM";document.getElementById("rank-dataset").dispatchEvent(new Event("change"));');
  assert((await execute('return document.getElementById("rank-context").textContent;')).includes('64 fields'));
  assert((await execute('return document.getElementById("rank-direction").textContent;')).includes('Lower'));
  const rankLink=await execute('return document.getElementById("rank-permalink").href;');
  const exploreLink=await execute('return document.getElementById("rank-explore-link").href;');
  await command('POST',base+'/url',{url:exploreLink});
  let restored=false;
  for(let i=0;i<100;i++){
    restored=await execute('return document.getElementById("dataset").value==="CESM" && document.getElementById("metric").value==="rd";');
    if(restored)break; await sleep(100);
  }
  assert(restored,'ranking-to-figure link did not restore the dataset');
  await command('POST',base+'/url',{url:rankLink});
  restored=false;
  for(let i=0;i<100;i++){
    restored=await execute('return document.getElementById("rank-dataset").value==="CESM" && document.getElementById("rank-metric").value==="spectral_l1" && document.querySelectorAll("#rank-body tr").length===5;');
    if(restored)break; await sleep(100);
  }
  assert(restored,'ranking link did not restore its filters');
  await execute('document.getElementById("track-particle").click();');
  assert((await execute('return document.getElementById("rank-empty").textContent;')).includes('No verified particle'));
  await execute('document.getElementById("track-domain_specific").click();');
  assert((await execute('return document.getElementById("rank-empty").textContent;')).includes('domain-specific'));
  await execute('document.getElementById("track-general").click();document.getElementById("leaderboard").scrollIntoView();');
  await sleep(800);
  const screenshot=await command('GET',base+'/screenshot');
  if(process.env.SCREENSHOT_PATH)await writeFile(process.env.SCREENSHOT_PATH,Buffer.from(screenshot,'base64'));
  await command('POST',base+'/window/rect',{width:390,height:844});
  const mobile=await execute('return {window:document.documentElement.clientWidth,page:document.documentElement.scrollWidth,table:document.querySelector(".rank-scroll").scrollWidth,region:document.querySelector(".rank-scroll").clientWidth};');
  assert(mobile.page<=mobile.window+1,'unexpected mobile page horizontal overflow: '+JSON.stringify(mobile));
  assert(mobile.table>mobile.region,'the leaderboard table should scroll within its own region');
  const sticky=await execute('const c=document.querySelector(".rank-scroll");c.scrollLeft=240;const a=c.querySelector("tbody td:first-child").getBoundingClientRect(),b=c.querySelector("tbody td:nth-child(2)").getBoundingClientRect();return {left:a.left,right:a.right,next:b.left};');
  assert(sticky.next>=sticky.right-1,'sticky rank and compressor columns overlap: '+JSON.stringify(sticky));
  console.log('Firefox browser: rankings, share links, empty tracks and responsive layout passed.');
} finally {
  if(session)await command('DELETE','/session/'+session);
}
