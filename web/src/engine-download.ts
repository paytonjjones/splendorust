export interface EngineProgress {
  label: string;
  detail: string;
  loaded: number;
  total: number | null;
}

// Counts bytes from the response stream. The caller supplies the verified asset
// size, so HTTP compression does not give the progress bar a false denominator.
export async function downloadBytes(response: Response, total: number, report: (loaded: number) => void): Promise<Uint8Array<ArrayBuffer>> {
  if (!response.body) throw new Error("The engine download has no response body.");
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let loaded = 0;
  let lastReport = 0;
  report(0);
  while (true) {
    const chunk = await reader.read();
    if (chunk.done) break;
    loaded += chunk.value.length;
    if (loaded > total) { await reader.cancel(); throw new Error("The engine download exceeds its declared size."); }
    chunks.push(chunk.value);
    if (performance.now() - lastReport >= 100) { report(loaded); lastReport = performance.now(); }
  }
  if (loaded !== total) throw new Error("The engine download size does not match its metadata.");
  const bytes = new Uint8Array(loaded);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  report(loaded);
  return bytes;
}
