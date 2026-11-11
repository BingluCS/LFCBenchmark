// Run on HPDPS-8: node tests/test_leaderboard_web.js docs
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const root = path.resolve(process.argv[2] || path.join(__dirname,"../docs"));
const source = fs.readFileSync(path.join(root,"leaderboard.js"),"utf8");
const data = JSON.parse(fs.readFileSync(path.join(root,"data/leaderboard.json"),"utf8"));

class Element {
  constructor(){this.value="";this.children=[];this.listeners={};this.textContent="";this.disabled=false;this.hidden=false;this.attrs={};
    this.classList={toggle:()=>{}};}
  addEventListener(name,fn){this.listeners[name]=fn;}
  change(){this.listeners.change();} click(){this.listeners.click();}
  setAttribute(name,value){this.attrs[name]=value;}
  replaceChildren(...items){this.children=items.length===1 && items[0].fragment ? items[0].children : items;}
  append(...items){this.children.push(...items);}
  insertCell(){const cell=new Element();this.children.push(cell);return cell;}
}
class Option { constructor(label,value){this.label=label;this.value=value;} }
function environment(offline=false,search=""){
  const elements={};
  const document={getElementById(id){return elements[id] ||= new Element();},
    createDocumentFragment(){const e=new Element();e.fragment=true;return e;},
    createElement(){return new Element();}};
  elements['rank-dataset']=new Element();elements['rank-dataset'].value='NYX';
  elements['rank-bound']=new Element();elements['rank-bound'].value='0.001';
  elements['rank-metric']=new Element();elements['rank-metric'].value='ratio';
  const fetch=async()=>{if(offline)throw new Error('offline');return {ok:true,json:async()=>data};};
  const window={location:new URL("https://example.test/LFCBenchmark/"+search)};
  vm.runInNewContext(source,{document,Option,fetch,Intl,window,URL,URLSearchParams});
  return elements;
}
async function main(){
  const e=environment();await new Promise(setImmediate);
  assert.equal(e['rank-empty'].hidden,true);
  assert.equal(e['rank-dataset'].value,'NYX');assert.equal(e['rank-bound'].value,'0.001');
  let group=data.groups.find(g=>g.protocol.dataset==='NYX' && g.protocol.alpha===.001);
  assert(!e['rank-context'].textContent.includes(group.protocol.host));
  const first=group.entries.slice().sort((a,b)=>b.metrics.ratio-a.metrics.ratio)[0];
  assert.equal(e['rank-body'].children.length,5);
  assert.deepEqual(e['rank-body'].children.map(row=>row.className || ''),['rank-place-1','rank-place-2','rank-place-3','','']);
  assert.equal(e['rank-body'].children[0].children[1].children[0].textContent,first.display_name);
  assert(e['rank-direction'].textContent.includes('Higher'));
  assert.equal(e['rank-col-ratio'].hidden,true);
  e['rank-metric'].value='spectral_l1';e['rank-metric'].change();
  const best=group.entries.slice().sort((a,b)=>a.metrics.spectral_l1-b.metrics.spectral_l1)[0];
  assert.equal(e['rank-body'].children[0].children[1].children[0].textContent,best.display_name);
  assert(e['rank-direction'].textContent.includes('Lower'));
  assert.equal(e['rank-col-spectral_l1'].hidden,true);assert.equal(e['rank-col-ratio'].hidden,false);
  e['rank-dataset'].value='CESM';e['rank-dataset'].change();
  assert(e['rank-context'].textContent.includes('64 fields'));
  let link=new URL(e['rank-explore-link'].href);
  assert.equal(link.hash,'#results');assert.equal(link.searchParams.get('view_dataset'),'CESM');
  assert.equal(link.searchParams.get('view_figure'),'rd');assert(!link.searchParams.has('view_bound'));
  e['track-particle'].click();assert.equal(e['rank-empty'].hidden,false);
  assert.equal(e['experiment-hardware'].hidden,true);
  assert(e['rank-empty'].textContent.includes('No verified particle'));
  assert.equal(e['rank-dataset'].disabled,true);assert.equal(e['rank-body'].children.length,0);
  assert.equal(e['rank-scroll'].hidden,true);assert.equal(e['rank-explore-link'].hidden,true);
  e['track-domain_specific'].click();assert(e['rank-empty'].textContent.includes('domain-specific'));
  e['track-general'].click();assert.equal(e['rank-empty'].hidden,true);assert.equal(e['rank-dataset'].disabled,false);
  assert.equal(e['experiment-hardware'].hidden,false);
  const offline=environment(true);await new Promise(setImmediate);
  assert(offline['rank-empty'].textContent.includes('could not be loaded'));
  const deep=environment(false,'?rank_track=general&rank_dataset=CESM&rank_bound=0.0001&rank_metric=spectral_l1');
  await new Promise(setImmediate);
  assert.equal(deep['rank-dataset'].value,'CESM');assert.equal(deep['rank-bound'].value,'0.0001');
  assert.equal(deep['rank-metric'].value,'spectral_l1');
  link=new URL(deep['rank-permalink'].href);
  assert.equal(link.hash,'#leaderboard');assert.equal(link.searchParams.get('rank_metric'),'spectral_l1');
  const oldLink=environment(false,'?rank_metric=compress_MB_s');
  await new Promise(setImmediate);
  assert.equal(oldLink['rank-metric'].value,'compress_MiB_s');
  assert.equal(oldLink['rank-score-heading'].textContent,'Compression\nthroughput (MiB/s)');
  console.log('Leaderboard controls: rankings, cohort selection, empty tracks and offline state passed.');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
