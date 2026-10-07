import {chromium} from '@playwright/test';
import {readFile,writeFile,appendFile} from 'node:fs/promises';
const plan=JSON.parse(await readFile('../research/browser-batch-20261006/PLAN.json','utf8'));
const out='../research/browser-batch-20261006/games.jsonl';
await writeFile(out,JSON.stringify({type:'metadata',plan})+'\n',{flag:'wx'});
const browser=await chromium.launch({channel:'chrome',headless:true});
try {
 const page=await browser.newPage();
 await page.exposeFunction('recordMatch',async message=>{
  if (['game','error','ready','done'].includes(message.type)) await appendFile(out,JSON.stringify(message)+'\n');
  if (message.type==='game') console.log(JSON.stringify({type:'game',seed:message.record.seed,batchSeat:message.record.batchSeat,result:message.record.result,stopped:message.record.stopped}));
  if (message.type==='turn') console.log(JSON.stringify({type:'progress',seed:message.seed,batchSeat:message.batchSeat,turns:message.turnCount,batch:message.turn.batch,ms:Math.round(message.turn.ms),simulations:message.turn.simulations}));
 });
 await page.route('**/batch-strength-empty',route=>route.fulfill({status:200,contentType:'text/html',body:'<!doctype html><title>Batch strength</title>',headers:{'Cross-Origin-Opener-Policy':'same-origin','Cross-Origin-Embedder-Policy':'require-corp'}}));
 await page.goto('http://127.0.0.1:4175/batch-strength-empty');
 const adapter=await page.evaluate(async()=>{const a=await navigator.gpu.requestAdapter();return a?{vendor:a.info.vendor,device:a.info.device,fallback:a.info.isFallbackAdapter}:null;});
 if (!adapter || adapter.fallback) throw new Error('Hardware WebGPU required');
 await writeFile('../research/browser-batch-20261006/backend.json',JSON.stringify({browser:browser.version(),adapter},null,2)+'\n');
 await page.evaluate(seeds=>{
  window.matchDone=false;window.matchError=null;
  const worker=new Worker('/src/batch-strength.worker.ts',{type:'module'});
  worker.onmessage=async e=>{await window.recordMatch(e.data);if(e.data.type==='done')window.matchDone=true;if(e.data.type==='error')window.matchError=e.data.error;};
  worker.onerror=e=>{window.matchError=e.message;};
  worker.postMessage({seeds});
 },plan.seeds);
 await page.waitForFunction(()=>window.matchDone||window.matchError,undefined,{timeout:2100000});
 const error=await page.evaluate(()=>window.matchError);if(error)throw new Error(error);
} finally {await browser.close();}
