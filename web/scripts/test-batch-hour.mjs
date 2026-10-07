import {chromium} from '@playwright/test';
import {readFile,writeFile,appendFile} from 'node:fs/promises';
const dir='../research/browser-batch-hour-20261007';
const plan=JSON.parse(await readFile(dir+'/PLAN.json','utf8'));
const out=dir+'/games.jsonl';
await writeFile(out,JSON.stringify({type:'metadata',plan})+'\n',{flag:'wx'});
const browser=await chromium.launch({channel:'chrome',headless:true});
let writes=Promise.resolve();
try {
 const page=await browser.newPage();
 await page.exposeFunction('recordMatch',message=>{
  writes=writes.then(()=>appendFile(out,JSON.stringify(message)+'\n'));
  if(message.type==='game') console.log(JSON.stringify({type:'finished',id:message.record.id,seats:message.record.seats,status:message.record.result?.status??message.record.stopped,seconds:Math.round(message.record.elapsedMs/1000)}));
  if(message.type==='start') console.log(JSON.stringify(message));
  if(message.type==='turn' && message.turnCount%10===0) console.log(JSON.stringify({type:'progress',id:message.id,turns:message.turnCount,seats:message.seats}));
  return writes;
 });
 await page.route('**/batch-hour-empty',route=>route.fulfill({status:200,contentType:'text/html',body:'<!doctype html><title>Batch hour</title>',headers:{'Cross-Origin-Opener-Policy':'same-origin','Cross-Origin-Embedder-Policy':'require-corp'}}));
 await page.goto('http://127.0.0.1:4175/batch-hour-empty');
 const adapter=await page.evaluate(async()=>{const a=await navigator.gpu.requestAdapter();return a?{vendor:a.info.vendor,device:a.info.device,fallback:a.info.isFallbackAdapter}:null;});
 if(!adapter||adapter.fallback) throw new Error('Hardware WebGPU required');
 await writeFile(dir+'/backend.json',JSON.stringify({browser:browser.version(),adapter,start:new Date().toISOString()},null,2)+'\n');
 await page.evaluate(plan=>{
  window.matchDone=false;window.matchError=null;
  const worker=new Worker('/src/batch-hour.worker.ts',{type:'module'});
  worker.onmessage=async e=>{await window.recordMatch(e.data);if(e.data.type==='done')window.matchDone=true;if(e.data.type==='error')window.matchError=e.data.error;};
  worker.onerror=e=>{window.matchError=e.message;};
  worker.postMessage({schedule:plan.schedule,deadlineEpochMs:Date.parse(plan.play_cutoff_utc)});
 },plan);
 await page.waitForFunction(()=>window.matchDone||window.matchError,undefined,{timeout:Math.max(1000,Date.parse(plan.play_cutoff_utc)-Date.now()+30000)});
 await writes;
 const error=await page.evaluate(()=>window.matchError);if(error)throw new Error(error);
} finally {await writes;await browser.close();}
