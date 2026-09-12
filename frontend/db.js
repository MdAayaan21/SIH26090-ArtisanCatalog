/**
 * Member 3 — Offline & Local Storage: IndexedDB persistence layer.
 *
 * Stores draft listings (photos as Blobs + audio Blob + metadata) locally
 * so the artisan never loses work on a bad connection. All writes for one
 * capture session happen inside a single IndexedDB transaction, so a crash
 * mid-write can never leave an orphaned photo with no matching draft record.
 */
const DB_NAME = "kaarigar_bazaar";
const DB_VERSION = 1;
const STORE_DRAFTS = "drafts";      // one row per capture session (a "batch")
const STORE_MEDIA = "media_blobs";  // photo/audio blobs, keyed by draft id + slot

const ArtisanDB = (() => {
  let dbPromise = null;

  function open() {
    if (dbPromise) return dbPromise;
    dbPromise = new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION);

      req.onupgradeneeded = (event) => {
        const db = event.target.result;
        if (!db.objectStoreNames.contains(STORE_DRAFTS)) {
          const drafts = db.createObjectStore(STORE_DRAFTS, { keyPath: "clientBatchId" });
          drafts.createIndex("syncState", "syncState", { unique: false });
        }
        if (!db.objectStoreNames.contains(STORE_MEDIA)) {
          db.createObjectStore(STORE_MEDIA, { keyPath: "blobKey" });
        }
      };

      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
    return dbPromise;
  }

  /**
   * Atomically writes the draft record AND all its media blobs in one
   * transaction. If anything fails, IndexedDB rolls back the whole write —
   * so there is never a draft with missing photos or a photo with no draft.
   */
  async function saveDraftAtomic(draft, mediaBlobs) {
    const db = await open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction([STORE_DRAFTS, STORE_MEDIA], "readwrite");
      tx.objectStore(STORE_DRAFTS).put(draft);
      for (const blobRecord of mediaBlobs) {
        tx.objectStore(STORE_MEDIA).put(blobRecord);
      }
      tx.oncomplete = () => resolve(draft);
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error || new Error("Draft write aborted"));
    });
  }

  async function updateDraftState(clientBatchId, patch) {
    const db = await open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_DRAFTS, "readwrite");
      const store = tx.objectStore(STORE_DRAFTS);
      const getReq = store.get(clientBatchId);
      getReq.onsuccess = () => {
        const existing = getReq.result;
        if (!existing) return reject(new Error("Draft not found: " + clientBatchId));
        store.put({ ...existing, ...patch });
      };
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  async function getQueuedDrafts() {
    const db = await open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_DRAFTS, "readonly");
      const req = tx.objectStore(STORE_DRAFTS).getAll();
      req.onsuccess = () => resolve(req.result.filter(d => d.syncState !== "committed"));
      req.onerror = () => reject(req.error);
    });
  }

  async function getMediaBlob(blobKey) {
    const db = await open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_MEDIA, "readonly");
      const req = tx.objectStore(STORE_MEDIA).get(blobKey);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  async function deleteDraftAndMedia(clientBatchId, blobKeys) {
    const db = await open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction([STORE_DRAFTS, STORE_MEDIA], "readwrite");
      tx.objectStore(STORE_DRAFTS).delete(clientBatchId);
      for (const key of blobKeys) tx.objectStore(STORE_MEDIA).delete(key);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  return { saveDraftAtomic, updateDraftState, getQueuedDrafts, getMediaBlob, deleteDraftAndMedia };
})();
