import { downloadBytes, type EngineProgress } from "./engine-download";
import * as ort from "onnxruntime-web/webgpu";
import moduleUrl from "../node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.asyncify.mjs?url";

export interface GpuManifest {
  schema: string;
  sourceSha256: string;
  sha256: string;
  bytes: number;
  url: string;
}

export async function loadGpuModel(sourceSha256: string, baseUrl: string, capture = true, onProgress?: (progress: EngineProgress) => void, batch = 1) {
  if (batch !== 1 && (!import.meta.env.DEV || ![4,8].includes(batch))) throw new Error("Batch inference is a development probe only.");
  if (!navigator.gpu) throw new Error("This browser does not support WebGPU.");
  ort.env.wasm.numThreads = 1;
  ort.env.wasm.wasmPaths = { mjs: moduleUrl };
  // Pages accepts files below 25 MiB. Store the larger ORT runtime as gzip,
  // then supply its verified bytes directly to the WebAssembly loader.
  const progress = (detail: string, loaded = 0, total: number | null = null) => onProgress?.({ label: "Loading the WebGPU engine", detail, loaded, total });
  progress("Downloading runtime", 0, 6605903);
  const runtimeResponse = await fetch(new URL("onnxruntime/ort-1.30.0-asyncify.gz.bin", baseUrl));
  if (!runtimeResponse.ok || !runtimeResponse.body) throw new Error("The GPU runtime is unavailable.");
  const compressed = await downloadBytes(runtimeResponse, 6605903, loaded => progress("Downloading runtime", loaded, 6605903));
  progress("Preparing runtime");
  const runtime = new Uint8Array(await new Response(new Blob([compressed]).stream().pipeThrough(new DecompressionStream("gzip"))).arrayBuffer());
  if (runtime.length !== 26781914 || await sha256(runtime) !== "39f9f0894d478800487ed9f7dbe92618498db320cf55c8e3d89adff8dce658da") throw new Error("GPU runtime hash check failed.");
  ort.env.wasm.wasmBinary = runtime;
  const metadataResponse = await fetch(new URL(batch === 1 ? "webgpu.json" : `webgpu-batch${batch}.json`, baseUrl), { cache: "no-cache" });
  if (!metadataResponse.ok) throw new Error("WebGPU model metadata is unavailable.");
  const metadata = await metadataResponse.json() as GpuManifest;
  if (metadata.schema !== "splendor-webgpu-model-v1" || metadata.sourceSha256 !== sourceSha256) {
    throw new Error("WebGPU weights do not match the engine.");
  }
  progress("Downloading engine weights", 0, metadata.bytes);
  const response = await fetch(new URL(metadata.url, baseUrl));
  if (!response.ok) throw new Error("WebGPU weights are unavailable.");
  const bytes = await downloadBytes(response, metadata.bytes, loaded => progress("Downloading engine weights", loaded, metadata.bytes));
  const hash = await sha256(bytes);
  if (bytes.length !== metadata.bytes || hash !== metadata.sha256) throw new Error("WebGPU model hash check failed.");
  if (!await navigator.gpu.requestAdapter()) throw new Error("WebGPU is unavailable. Enable hardware acceleration and restart your browser.");
  progress("Preparing GPU pipelines");
  const session = await ort.InferenceSession.create(bytes, { executionProviders: ["webgpu"], enableGraphCapture: capture, preferredOutputLocation: capture ? "gpu-buffer" : "cpu" });
  const device = await ort.env.webgpu.device;
  let deviceError: string | null = null;
  const lost = device.lost.then(info => { deviceError = `WebGPU device lost: ${info.message || info.reason}. Restart the game.`; return deviceError; });
  const input = new Float32Array(batch * 31 * 48);
  // Capture requires fixed GPU inputs. CPU-backed input tensors gave stale
  // outputs in the earlier experiment. Keep one input and one readback buffer.
  const buffer = capture ? device.createBuffer({ size: input.byteLength, usage: GPUBufferUsage.COPY_DST | GPUBufferUsage.STORAGE }) : null;
  const tensor = buffer ? ort.Tensor.fromGpuBuffer(buffer, { dataType: "float32", dims: [batch,31,48] }) : new ort.Tensor("float32", input, [batch,31,48]);
  const readback = capture ? device.createBuffer({ size: Math.ceil(batch * 83 * 4 / 16) * 16, usage: GPUBufferUsage.MAP_READ | GPUBufferUsage.COPY_DST }) : null;
  const evaluate = async (tokens: Float32Array) => {
    if (deviceError) throw new Error(deviceError);
    if (tokens.length !== input.length) throw new Error("Engine input size is incorrect.");
    if (buffer) device.queue.writeBuffer(buffer, 0, tokens as Float32Array<ArrayBuffer>);
    else input.set(tokens);
    const out = await session.run({ tokens: tensor });
    if (deviceError) throw new Error(deviceError);
    let result: Float32Array;
    if (readback) {
      const encoder = device.createCommandEncoder();
      encoder.copyBufferToBuffer(out.logits.gpuBuffer, 0, readback, 0, batch * 324);
      encoder.copyBufferToBuffer(out.values.gpuBuffer, 0, readback, batch * 324, batch * 8);
      device.queue.submit([encoder.finish()]);
      await readback.mapAsync(GPUMapMode.READ);
      result = new Float32Array(readback.getMappedRange(), 0, batch * 83).slice();
      readback.unmap();
    } else {
      result = new Float32Array(batch * 83);
      result.set(out.logits.data as Float32Array);
      result.set(out.values.data as Float32Array, batch * 81);
    }
    out.logits.dispose();
    out.values.dispose();
    return result;
  };
  return { metadata, evaluate, lost, release: async () => { await session.release(); buffer?.destroy(); readback?.destroy(); } };
}

async function sha256(bytes: Uint8Array<ArrayBuffer>): Promise<string> {
  return [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))].map(x => x.toString(16).padStart(2, "0")).join("");
}
