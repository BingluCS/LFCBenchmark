// Run on HPDPS-8 with geckodriver and the site HTTP server.
import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';

const driver = process.env.WEBDRIVER_URL || 'http://127.0.0.1:17774';
const page = process.env.BENCHMARK_URL || 'http://127.0.0.1:18768/';
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
  const created=await command('POST','/session',{capabilities:{alwaysMatch:{browserName:'firefox',
    'moz:firefoxOptions':{args:['-headless']}}}});
  session=created.sessionId;
  const base='/session/'+session;
  const execute=script=>command('POST',base+'/execute/sync',{script,args:[]});
  const screenshot=async name=>{
    if(!process.env.SCREENSHOT_PREFIX)return;
    const bytes=await command('GET',base+'/screenshot');
    await writeFile(process.env.SCREENSHOT_PREFIX+'-'+name+'.png',Buffer.from(bytes,'base64'));
  };
  await command('POST',base+'/window/rect',{width:1440,height:1000});
  await command('POST',base+'/url',{url:page});
  for(const width of [1440,1024,768,390,320]){
    await command('POST',base+'/window/rect',{width,height:1000});
    await execute('window.scrollTo({top:0,behavior:"instant"});');
    await sleep(150);
    const layout=await execute('const r=e=>e.getBoundingClientRect();const a=r(document.querySelector(".hero-copy")),b=r(document.querySelector(".hero-board"));return {window:document.documentElement.clientWidth,page:document.documentElement.scrollWidth,a:{left:a.left,right:a.right,top:a.top,bottom:a.bottom},b:{left:b.left,right:b.right,top:b.top,bottom:b.bottom},nav:document.querySelectorAll(".top nav a").length};');
    if(layout.page>layout.window+1)console.log('Overflowing elements:',await execute('return [...document.querySelectorAll("body *")].filter(e=>e.getBoundingClientRect().right>document.documentElement.clientWidth+1 && getComputedStyle(e).position!=="sticky").map(e=>({tag:e.tagName,cls:e.className,right:Math.round(e.getBoundingClientRect().right)})).slice(0,20);'));
    assert(layout.page<=layout.window+1,'page overflow at '+width+': '+JSON.stringify(layout));
    assert.equal(layout.nav,5);
    assert(layout.a.right<=layout.b.left+1 || layout.a.bottom<=layout.b.top+1,'hero overlaps at '+width+': '+JSON.stringify(layout));
    if(width===1440)await screenshot('desktop');
    if(width===390)await screenshot('mobile');
  }
  // Firefox can impose a minimum window size; an iframe exercises the actual
  // CSS viewport at narrow phone widths even when the outer window is wider.
  for(const width of [320,360,414]){
    const frame=await command('POST',base+'/execute/async',{script:`const done=arguments[arguments.length-1];
      const f=document.createElement('iframe');f.style.cssText='position:fixed;left:0;top:0;width:${width}px;height:800px;border:0;z-index:100';
      f.onload=()=>{const d=f.contentDocument;done({window:d.documentElement.clientWidth,page:d.documentElement.scrollWidth});f.remove();};
      f.src=location.href;document.body.append(f);`,args:[]});
    assert(frame.window<=width && frame.page<=frame.window+1,'phone viewport overflow at '+width+': '+JSON.stringify(frame));
  }
  if(process.env.SCREENSHOT_PREFIX){
    await command('POST',base+'/window/rect',{width:1440,height:1000});
    await execute('document.getElementById("results").scrollIntoView({behavior:"instant"});');
    await sleep(500); await screenshot('results');
    await execute('document.getElementById("downloads").scrollIntoView({behavior:"instant"});');
    await sleep(500); await screenshot('downloads');
  }
  await execute('document.querySelector("#protocol-details > summary").click();');
  assert(await execute('return document.getElementById("protocol-details").open;'));
  const qualityLink=await execute('return document.querySelector(".overview-card[href*=ssim_rd]").href;');
  await command('POST',base+'/url',{url:qualityLink});
  let qualityReady=false;
  for(let i=0;i<100;i++){
    qualityReady=await execute('return document.getElementById("dataset").value==="all" && document.getElementById("metric").value==="ssim_rd";');
    if(qualityReady)break; await sleep(100);
  }
  assert(qualityReady,'the quality overview link did not open the SSIM figure');
  console.log('Firefox browser: desktop/mobile layout, navigation, quality overview link and protocol disclosure passed.');
} finally {
  if(session)await command('DELETE','/session/'+session);
}
