import { loadGpuModel } from "./webgpu-model";

self.onmessage = async (event: MessageEvent<{ buffer: SharedArrayBuffer; sourceSha256: string; baseUrl: string }>) => {
  const { buffer, sourceSha256, baseUrl } = event.data;
  const control = new Int32Array(buffer, 0, 4);
  const input = new Float32Array(buffer, 16, 31 * 48);
  const output = new Float32Array(buffer, 16 + 31 * 48 * 4, 83);
  try {
    const model = await loadGpuModel(sourceSha256, baseUrl);
    void model.lost.then(error => {
      Atomics.store(control, 0, -1);
      Atomics.notify(control, 0);
      self.postMessage({ type: "error", error });
    });
    // Warm GPU pipelines before any game prediction.
    for (let i = 0; i < 3; i++) await model.evaluate(input);
    self.postMessage({ type: "ready", model: model.metadata });
    while (true) {
      while (Atomics.load(control, 0) !== 1) {
        const state = Atomics.load(control, 0);
        const wait = Atomics.waitAsync(control, 0, state);
        if (wait.async) await wait.value;
      }
      output.set(await model.evaluate(input));
      Atomics.store(control, 0, 2);
      Atomics.notify(control, 0);
    }
  } catch (error) {
    Atomics.store(control, 0, -1);
    Atomics.notify(control, 0);
    self.postMessage({ type: "error", error: String(error) });
  }
};
