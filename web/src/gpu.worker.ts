import { waitForGpuRequest } from "./gpu-mailbox";
import { loadGpuModel } from "./webgpu-model";

self.onmessage = async (event: MessageEvent<{ buffer: SharedArrayBuffer; sourceSha256: string; baseUrl: string; batch: 1 | 2 | 8 }>) => {
  const { buffer, sourceSha256, baseUrl, batch } = event.data;
  const control = new Int32Array(buffer, 0, 4);
  const input = new Float32Array(buffer, 16, batch * 31 * 48);
  const output = new Float32Array(buffer, 16 + batch * 31 * 48 * 4, batch * 83);
  try {
    const model = await loadGpuModel(sourceSha256, baseUrl, true, progress => self.postMessage({ type: "progress", progress }), batch);
    void model.lost.then(error => {
      Atomics.store(control, 0, -1);
      Atomics.notify(control, 0);
      self.postMessage({ type: "error", error });
    });
    // Warm GPU pipelines before any game prediction.
    for (let i = 0; i < 3; i++) await model.evaluate(input);
    self.postMessage({ type: "ready", model: model.metadata });
    while (true) {
      await waitForGpuRequest(control);
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
