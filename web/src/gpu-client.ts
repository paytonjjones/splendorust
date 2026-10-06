// The search worker can block here. A second worker owns async GPU inference;
// the page remains free to render and process input.
export async function startGpu(sourceSha256: string, baseUrl: string, onFailure: (error: string) => void) {
  if (!navigator.gpu) throw new Error("This browser does not support WebGPU.");
  if (!self.crossOriginIsolated || typeof SharedArrayBuffer === "undefined") {
    throw new Error("The champion needs cross-origin isolated WebGPU workers.");
  }
  const buffer = new SharedArrayBuffer(16 + (31 * 48 + 83) * 4);
  const control = new Int32Array(buffer, 0, 4);
  const input = new Float32Array(buffer, 16, 31 * 48);
  const output = new Float32Array(buffer, 16 + 31 * 48 * 4, 83);
  const worker = new Worker(new URL("./gpu.worker.ts", import.meta.url), { type: "module" });
  let initialized = false;
  const ready = new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("WebGPU startup timed out.")), 60_000);
    worker.onerror = () => {
      Atomics.store(control, 0, -1);
      Atomics.notify(control, 0);
      clearTimeout(timer);
      if (initialized) onFailure("The WebGPU worker stopped.");
      else reject(new Error("The WebGPU worker could not start."));
    };
    worker.onmessage = (event: MessageEvent<{ type: string; error?: string }>) => {
      if (event.data.type === "ready") { clearTimeout(timer); initialized = true; resolve(); }
      if (event.data.type === "error") {
        clearTimeout(timer);
        if (initialized) onFailure(event.data.error ?? "WebGPU inference failed.");
        else reject(new Error(event.data.error));
      }
    };
  });
  worker.postMessage({ buffer, sourceSha256, baseUrl });
  try { await ready; } catch (error) { worker.terminate(); throw error; }
  const predict = (tokens: Float32Array) => {
    if (Atomics.load(control,0) === -1) throw new Error("WebGPU inference failed.");
    input.set(tokens);
    Atomics.store(control,0,1); Atomics.notify(control,0);
    const start = performance.now();
    while (Atomics.load(control,0) === 1) {
      if (Atomics.wait(control,0,1,2000) === "timed-out" || performance.now() - start > 2000) {
        Atomics.store(control, 0, -1);
        worker.terminate();
        throw new Error("WebGPU inference timed out.");
      }
    }
    if (Atomics.load(control,0) !== 2) throw new Error("WebGPU inference failed.");
    const result = output.slice();
    Atomics.store(control,0,0); Atomics.notify(control,0);
    return result;
  };
  Object.assign(globalThis, { splendorInference: { predict } });
  return () => worker.terminate();
}
