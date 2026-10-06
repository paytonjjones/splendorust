import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { gzipSync } from 'node:zlib';
import { createHash } from 'node:crypto';
const source = readFileSync('node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.asyncify.wasm');
const expected = '39f9f0894d478800487ed9f7dbe92618498db320cf55c8e3d89adff8dce658da';
if (createHash('sha256').update(source).digest('hex') !== expected) throw new Error('Unexpected ONNX Runtime binary. Review the pinned runtime before changing its hash.');
mkdirSync('public/onnxruntime', { recursive: true });
// Use .bin: some servers decode .gz automatically, which would decode it twice.
writeFileSync('public/onnxruntime/ort-1.30.0-asyncify.gz.bin', gzipSync(source, { level: 9 }));
for (const name of ['LICENSE', 'ThirdPartyNotices.txt']) {
  writeFileSync(`public/onnxruntime/${name}`, readFileSync(`scripts/onnxruntime/${name}`));
}

const model = JSON.parse(readFileSync('public/webgpu.json', 'utf8'));
const champion = JSON.parse(readFileSync('public/champion.json', 'utf8'));
const graph = readFileSync(`public${model.url}`);
if (model.sourceSha256 !== champion.model.sha256 || graph.length !== model.bytes || createHash('sha256').update(graph).digest('hex') !== model.sha256) {
  throw new Error('Export WebGPU weights from the registered champion before building.');
}
