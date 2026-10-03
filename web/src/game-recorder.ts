import type { GameRecorderUpdate, RecordedGame } from "./types";

interface StoredGame extends RecordedGame {
  ownerId: string;
  uploadEnabled: boolean;
  uploadedVersion: number;
  uploadError?: string;
}

const DATABASE_NAME = "splendor-web-training";
const DATABASE_VERSION = 1;
const STORE_NAME = "games";
const UPLOAD_INTERVAL_MS = 2_000;
const MAX_KEEPALIVE_BYTES = 60 * 1024;
const OWNER_STORAGE_KEY = "splendor-web-log-tab-owner";

function getTabOwnerId(): string {
  try {
    const existing = sessionStorage.getItem(OWNER_STORAGE_KEY);
    // A duplicated tab can inherit sessionStorage. Only a reload or history
    // restore keeps the old owner; a new navigation receives its own owner.
    const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined;
    if (existing && (navigation?.type === 'reload' || navigation?.type === 'back_forward')) return existing;
    const ownerId = createGameId();
    sessionStorage.setItem(OWNER_STORAGE_KEY, ownerId);
    return ownerId;
  } catch {
    return createGameId();
  }
}

function randomHex(byteCount: number): string {
  const bytes = crypto.getRandomValues(new Uint8Array(byteCount));
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function createGameId(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function createWriteToken(): string {
  return randomHex(32);
}

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("IndexedDB request failed."));
  });
}

function openDatabase(): Promise<IDBDatabase> {
  if (typeof indexedDB === "undefined") return Promise.reject(new Error("IndexedDB is not available."));
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(STORE_NAME)) {
        database.createObjectStore(STORE_NAME, { keyPath: "gameId" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Could not open the game log."));
    request.onblocked = () => reject(new Error("The game log is blocked by another tab."));
  });
}

function serverRecord(record: StoredGame): RecordedGame {
  const {
    ownerId: _ownerId,
    uploadEnabled: _uploadEnabled,
    uploadedVersion: _uploadedVersion,
    uploadError: _uploadError,
    ...envelope
  } = record;
  return envelope;
}

function safePublicRecord(record: StoredGame): Omit<RecordedGame, "writeToken"> {
  const { writeToken: _writeToken, ...publicRecord } = serverRecord(record);
  return publicRecord;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** Serializes local journal writes and uploads without waiting on them from game search. */
export class GameRecorder {
  private readonly records = new Map<string, StoredGame>();
  private database: IDBDatabase | null = null;
  private databaseTask: Promise<IDBDatabase> | null = null;
  private persistenceTail: Promise<void> = Promise.resolve();
  private flushTimer: number | null = null;
  private flushTask: Promise<void> | null = null;
  private retryDelayMs = UPLOAD_INTERVAL_MS;
  private readonly ownerId: string;
  private storageError: string | undefined;
  private status: GameRecorderUpdate = {
    status: "idle",
    pendingUploads: 0,
    storedGames: 0,
  };
  private disposed = false;
  private pagehideHandler = () => this.sendLatestKeepalive();
  private onlineHandler = () => {
    if (this.flushTimer !== null) window.clearTimeout(this.flushTimer);
    this.flushTimer = null;
    this.retryDelayMs = UPLOAD_INTERVAL_MS;
    void this.flushUploads();
  };

  constructor(
    private readonly onUpdate: (update: GameRecorderUpdate) => void,
    private readonly endpoint = "/api/games",
  ) {
    this.ownerId = getTabOwnerId();
    window.addEventListener("pagehide", this.pagehideHandler);
    window.addEventListener("online", this.onlineHandler);
    void this.restore().catch(() => {});
  }

  getUpdate(): GameRecorderUpdate {
    return { ...this.status };
  }

  /** Update memory first, then queue the durable write. */
  save(record: RecordedGame, uploadEnabled: boolean): void {
    const previous = this.records.get(record.gameId);
    if (previous && record.version <= previous.version) return;
    const stored: StoredGame = {
      ...record,
      ownerId: previous?.ownerId ?? this.ownerId,
      uploadEnabled,
      uploadedVersion: previous?.uploadedVersion ?? 0,
      uploadError: undefined,
    };
    this.records.set(record.gameId, stored);
    this.publish({ status: "saving", error: undefined });
    this.persistenceTail = this.persistenceTail.then(async () => {
      let persisted = false;
      try {
        await this.persistLatest(record.gameId);
        persisted = true;
      } catch (error) {
        this.storageError = `Could not save this game locally: ${errorMessage(error)}`;
        this.publish({ status: "error", error: this.storageError });
      }
      if (stored.uploadEnabled) {
        if (stored.status === "in_progress") this.scheduleFlush();
        else void this.flushUploads();
      } else if (persisted) {
        this.publish({ status: "saved", error: undefined });
      }
    });
  }

  /** Mark any prior interrupted games abandoned after restoring their durable snapshots. */
  async abandonRestoredGames(exceptGameId?: string): Promise<void> {
    try {
      await this.restore();
      for (const record of this.records.values()) {
        if (record.gameId === exceptGameId || record.ownerId !== this.ownerId || record.status !== "in_progress") continue;
        const updated: RecordedGame = {
          ...record,
          version: record.version + 1,
          updatedAt: new Date().toISOString(),
          status: "abandoned",
        };
        this.save(updated, record.uploadEnabled);
      }
    } catch {
      // The recorder status already contains the storage failure. The game can continue.
    }
  }

  async exportGames(): Promise<string> {
    await this.persistenceTail;
    try {
      await this.restore();
    } catch {
      // Use the in-memory copy if storage is unavailable.
    }
    const rows = [...this.records.values()]
      .sort((a, b) => a.startedAt.localeCompare(b.startedAt))
      .map((record) => JSON.stringify(safePublicRecord(record)));
    return rows.length ? `${rows.join("\n")}\n` : "";
  }

  retryUploads(): void {
    if (this.flushTimer !== null) {
      window.clearTimeout(this.flushTimer);
      this.flushTimer = null;
    }
    this.retryDelayMs = UPLOAD_INTERVAL_MS;
    void this.flushUploads();
  }

  dispose(): void {
    this.disposed = true;
    window.removeEventListener("pagehide", this.pagehideHandler);
    window.removeEventListener("online", this.onlineHandler);
    if (this.flushTimer !== null) window.clearTimeout(this.flushTimer);
  }

  private async restore(): Promise<void> {
    try {
      const database = await this.getDatabase();
      const transaction = database.transaction(STORE_NAME, "readonly");
      const stored = await requestResult(transaction.objectStore(STORE_NAME).getAll() as IDBRequest<StoredGame[]>);
      for (const record of stored) {
        const current = this.records.get(record.gameId);
        if (!current || record.version > current.version) this.records.set(record.gameId, record);
      }
      if (this.storageError?.startsWith("Could not open the local game log:")) this.storageError = undefined;
      this.publish({
        status: this.pendingCount() ? "queued" : this.records.size ? "saved" : "idle",
        error: undefined,
      });
      if (this.pendingCount()) this.scheduleFlush();
    } catch (error) {
      this.storageError = `Could not open the local game log: ${errorMessage(error)}`;
      this.publish({ status: "error", error: this.storageError });
      throw error;
    }
  }

  private getDatabase(): Promise<IDBDatabase> {
    if (this.database) return Promise.resolve(this.database);
    if (!this.databaseTask) {
      this.databaseTask = openDatabase().then((database) => {
        this.database = database;
        database.onversionchange = () => database.close();
        return database;
      }).catch((error: unknown) => {
        this.databaseTask = null;
        throw error;
      });
    }
    return this.databaseTask;
  }

  private async persistLatest(gameId: string): Promise<void> {
    const record = this.records.get(gameId);
    if (!record) return;
    const database = await this.getDatabase();
    const transaction = database.transaction(STORE_NAME, "readwrite");
    transaction.objectStore(STORE_NAME).put(record);
    await new Promise<void>((resolve, reject) => {
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error ?? new Error("IndexedDB write failed."));
      transaction.onabort = () => reject(transaction.error ?? new Error("IndexedDB write was aborted."));
    });
    this.storageError = undefined;
  }

  private pendingCount(): number {
    let pending = 0;
    for (const record of this.records.values()) {
      if (record.uploadEnabled && record.uploadedVersion < record.version) pending += 1;
    }
    return pending;
  }

  private publish(update: Partial<GameRecorderUpdate>): void {
    const safeUpdate = this.storageError
      ? { ...update, status: "error" as const, error: this.storageError }
      : update;
    this.status = {
      ...this.status,
      ...safeUpdate,
      pendingUploads: this.pendingCount(),
      storedGames: this.records.size,
    };
    this.onUpdate(this.getUpdate());
  }

  private scheduleFlush(): void {
    if (this.disposed || this.flushTimer !== null) return;
    this.publish({ status: "queued", error: undefined });
    this.flushTimer = window.setTimeout(() => {
      this.flushTimer = null;
      void this.flushUploads();
    }, this.retryDelayMs);
  }

  private async flushUploads(): Promise<void> {
    if (this.flushTask) return this.flushTask;
    this.flushTask = this.flushNow().finally(() => {
      this.flushTask = null;
    });
    return this.flushTask;
  }

  private async flushNow(): Promise<void> {
    await this.persistenceTail;
    const queue = [...this.records.values()].filter(
      (record) => record.uploadEnabled && record.uploadedVersion < record.version,
    );
    if (queue.length === 0) {
      this.publish({
        status: this.records.size ? "saved" : "idle",
        error: undefined,
      });
      return;
    }
    this.publish({ status: "uploading", error: undefined });
    for (const queued of queue) {
      const current = this.records.get(queued.gameId);
      if (!current || current.uploadedVersion >= current.version) continue;
      const body = JSON.stringify(serverRecord(current));
      if (new TextEncoder().encode(body).byteLength > 512 * 1024) {
        this.publish({ status: "error", error: "This game log is larger than the server limit; download the local JSONL copy." });
        return;
      }
      try {
        const response = await fetch(this.endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body,
        });
        if (response.status === 409) {
          this.publish({ status: "error", error: "The server rejected a conflicting replay version. The local copy is preserved." });
          return;
        }
        if (response.status >= 400 && response.status < 500 && response.status !== 408 && response.status !== 429) {
          this.publish({ status: "error", error: `The server rejected this game log (${response.status}). The local copy is preserved.` });
          return;
        }
        if (!response.ok) throw new Error(`The server returned ${response.status}.`);
        const ack = (await response.json()) as { storedVersion?: number };
        if (!Number.isInteger(ack.storedVersion)) throw new Error("The server response did not include a stored version.");
        const latest = this.records.get(current.gameId);
        if (latest) {
          latest.uploadedVersion = Math.max(latest.uploadedVersion, Math.min(ack.storedVersion!, current.version));
          latest.uploadError = undefined;
          this.records.set(latest.gameId, latest);
          this.persistenceTail = this.persistenceTail.then(async () => {
            try {
              await this.persistLatest(latest.gameId);
            } catch (error) {
              this.storageError = `Game uploaded, but the local copy could not be saved: ${errorMessage(error)}`;
              this.publish({ status: "error", error: this.storageError });
            }
          });
          await this.persistenceTail;
        }
      } catch (error) {
        const message = errorMessage(error);
        const latest = this.records.get(current.gameId);
        if (latest) latest.uploadError = message;
        this.retryDelayMs = Math.min(Math.max(this.retryDelayMs * 2, UPLOAD_INTERVAL_MS), 30_000);
        this.scheduleFlush();
        this.publish({ status: "queued", error: `Game log upload failed and will retry: ${message}` });
        return;
      }
    }
    const pending = this.pendingCount();
    this.retryDelayMs = UPLOAD_INTERVAL_MS;
    this.publish({ status: pending ? "queued" : "saved", error: undefined });
    if (pending) this.scheduleFlush();
  }

  private sendLatestKeepalive(): void {
    const record = [...this.records.values()]
      .filter((candidate) => candidate.uploadEnabled && candidate.uploadedVersion < candidate.version)
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))[0];
    if (!record) return;
    const body = JSON.stringify(serverRecord(record));
    if (new TextEncoder().encode(body).byteLength > MAX_KEEPALIVE_BYTES) return;
    void fetch(this.endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      keepalive: true,
    }).then(async (response) => {
      if (!response.ok) return;
      const ack = (await response.json()) as { storedVersion?: number };
      const latest = this.records.get(record.gameId);
      if (!latest || !Number.isInteger(ack.storedVersion)) return;
      latest.uploadedVersion = Math.max(latest.uploadedVersion, Math.min(ack.storedVersion!, record.version));
      this.records.set(latest.gameId, latest);
      this.persistenceTail = this.persistenceTail.then(async () => {
        try {
          await this.persistLatest(latest.gameId);
        } catch (error) {
          this.storageError = `Game uploaded, but the local copy could not be saved: ${errorMessage(error)}`;
          this.publish({ status: "error", error: this.storageError });
        }
      });
    }).catch(() => {
      // The newest snapshot is already durable in IndexedDB and will retry online.
    });
  }
}
