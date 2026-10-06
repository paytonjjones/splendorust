import * as ort from "onnxruntime-web/webgpu";
import moduleUrl from "../node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.asyncify.mjs?url";

export interface GpuManifest {
  schema: string;
  sourceSha256: string;
  sha256: string;
  bytes: number;
  url: string;
}

export async function loadGpuModel(sourceSha256: string, baseUrl: string) {
  if (!navigator.gpu) throw new Error("This browser does not support WebGPU.");
  ort.env.wasm.numThreads = 1;
  ort.env.wasm.wasmPaths = { mjs: moduleUrl };
  // Pages accepts files below 25 MiB. Store the larger ORT runtime as gzip,
  // then supply its verified bytes directly to the WebAssembly loader.
  const runtimeResponse = await fetch(new URL("onnxruntime/ort-1.30.0-asyncify.gz.bin", baseUrl));
  if (!runtimeResponse.ok || !runtimeResponse.body) throw new Error("The GPU runtime is unavailable.");
  const runtime = new Uint8Array(await new Response(runtimeResponse.body.pipeThrough(new DecompressionStream("gzip"))).arrayBuffer());
  if (runtime.length !== 26781914 || await sha256(runtime) !== "39f9f0894d478800487ed9f7dbe92618498db320cf55c8e3d89adff8dce658da") throw new Error("GPU runtime hash check failed.");
  ort.env.wasm.wasmBinary = runtime;
  const metadataResponse = await fetch(new URL("webgpu.json", baseUrl), { cache: "no-cache" });
  if (!metadataResponse.ok) throw new Error("WebGPU model metadata is unavailable.");
  const metadata = await metadataResponse.json() as GpuManifest;
  if (metadata.schema !== "splendor-webgpu-model-v1" || metadata.sourceSha256 !== sourceSha256) {
    throw new Error("WebGPU weights do not match the champion.");
  }
  const response = await fetch(new URL(metadata.url, baseUrl));
  if (!response.ok) throw new Error("WebGPU weights are unavailable.");
  const bytes = new Uint8Array(await response.arrayBuffer());
  const hash = await sha256(bytes);
  if (bytes.length !== metadata.bytes || hash !== metadata.sha256) throw new Error("WebGPU model hash check failed.");
  if (!await navigator.gpu.requestAdapter()) throw new Error("WebGPU is unavailable. Enable hardware acceleration and restart your browser.");
  const session = await ort.InferenceSession.create(bytes, { executionProviders: ["webgpu"], enableGraphCapture: false });
  const device = await ort.env.webgpu.device;
  let deviceError: string | null = null;
  const lost = device.lost.then(info => { deviceError = `WebGPU device lost: ${info.message || info.reason}. Restart the game.`; return deviceError; });
  const input = new Float32Array(31 * 48);
  const tensor = new ort.Tensor("float32", input, [1, 31, 48]);
  const evaluate = async (tokens: Float32Array) => {
    if (deviceError) throw new Error(deviceError);
    input.set(tokens);
    const out = await session.run({ tokens: tensor });
    if (deviceError) throw new Error(deviceError);
    const logits = out.logits.data as Float32Array;
    const values = out.values.data as Float32Array;
    const result = new Float32Array(83);
    result.set(logits); result.set(values, 81);
    out.logits.dispose();
    out.values.dispose();
    return result;
  };
  return { metadata, evaluate, lost, release: () => session.release() };
}

async function sha256(bytes: Uint8Array<ArrayBuffer>): Promise<string> {
  return [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))].map(x => x.toString(16).padStart(2, "0")).join("");
}
