import { chromium } from '@playwright/test';
import { writeFile } from 'node:fs/promises';
const url = process.argv[2] ?? 'http://127.0.0.1:5173';
const mode = process.argv[3] ?? "standard";
const query = mode.startsWith("batch") ? `?capture=1&batch=${Number(mode.slice(5))}` : mode === "capture" ? "?capture=1" : "";
const browser = await chromium.launch({ channel: 'chrome', headless: true });
try {
  const page = await browser.newPage();
  await page.goto(`${url}/webgpu-probe.html${query}`);
  await page.waitForFunction(() => window.gpuProbe || window.gpuProbeError, undefined, { timeout: 120000 });
  const result = await page.evaluate(() => ({ result: window.gpuProbe, error: window.gpuProbeError }));

  const adapter = await page.evaluate(async () => {
    const adapter = await navigator.gpu.requestAdapter();
    if (!adapter) throw new Error('No GPU adapter');
    return { vendor: adapter.info.vendor, architecture: adapter.info.architecture, device: adapter.info.device, description: adapter.info.description, fallback: adapter.info.isFallbackAdapter };
  });
  const receipt = { browser: browser.version(), browserFlags: [], adapter, ...result };
  await writeFile(process.argv[4] ?? `../research/webgpu-20261006/tuning-probe${process.argv[3] === 'capture' ? '-capture' : ''}.json`, JSON.stringify(receipt, null, 2) + '\n');
  console.log(JSON.stringify(receipt));
  if (result.error) throw new Error(result.error);
} finally { await browser.close(); }
