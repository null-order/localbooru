(() => {
  const CLIP_UPLOAD_STORE_KEY = "localbooru.clipUploads.v2";
  const CLIP_UPLOAD_STORE_LIMIT = 24;
  const CLIP_SESSION_KEY_PREFIX = "localbooru.clipSnapshot:";

  function getLocalStorageSafe() {
    try {
      if (typeof window === "undefined") return null;
      return window.localStorage || null;
    } catch (err) {
      console.debug("localStorage unavailable", err);
      return null;
    }
  }

  function getSessionStorageSafe() {
    try {
      if (typeof window === "undefined") return null;
      return window.sessionStorage || null;
    } catch (err) {
      console.debug("sessionStorage unavailable", err);
      return null;
    }
  }

  function loadUploadStore() {
    const storage = getLocalStorageSafe();
    if (!storage) return {};
    try {
      const raw = storage.getItem(CLIP_UPLOAD_STORE_KEY);
      if (!raw) return {};
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object") {
        return parsed;
      }
    } catch (err) {
      console.warn("Failed to load clip upload cache", err);
    }
    return {};
  }

  let uploadStore = loadUploadStore();

  function persistUploadStore() {
    const storage = getLocalStorageSafe();
    if (!storage) return;
    try {
      storage.setItem(CLIP_UPLOAD_STORE_KEY, JSON.stringify(uploadStore));
    } catch (err) {
      console.warn("Failed to persist clip upload cache", err);
    }
  }

  function pruneUploadStore() {
    const tokens = Object.keys(uploadStore || {});
    if (tokens.length <= CLIP_UPLOAD_STORE_LIMIT) return;
    const ordered = tokens
      .map((token) => ({
        token,
        updatedAt:
          typeof uploadStore[token]?.updatedAt === "number"
            ? uploadStore[token].updatedAt
            : 0,
      }))
      .sort((a, b) => a.updatedAt - b.updatedAt);
    const excess = ordered.slice(
      0,
      Math.max(0, tokens.length - CLIP_UPLOAD_STORE_LIMIT),
    );
    let modified = false;
    excess.forEach(({ token }) => {
      if (uploadStore[token]) {
        delete uploadStore[token];
        modified = true;
      }
    });
    if (modified) {
      persistUploadStore();
    }
  }

  function createUploadToken() {
    if (typeof crypto !== "undefined" && crypto.randomUUID) {
      return `upl-${crypto.randomUUID()}`;
    }
    const millis = Date.now().toString(36);
    const random = Math.random().toString(36).slice(2, 10);
    return `upl-${millis}-${random}`;
  }

  function recordUpload(token, data) {
    if (!token) return;
    if (!uploadStore || typeof uploadStore !== "object") {
      uploadStore = {};
    }
    uploadStore[token] = {
      vector: typeof data.vector === "string" ? data.vector : null,
      thumbnail: typeof data.thumbnail === "string" ? data.thumbnail : null,
      label: typeof data.label === "string" ? data.label : "",
      mimeType: typeof data.mimeType === "string" ? data.mimeType : "",
      size: Number.isFinite(data.size) ? Number(data.size) : null,
      updatedAt: Date.now(),
    };
    pruneUploadStore();
    persistUploadStore();
  }

  function readUpload(token, { touch = false } = {}) {
    if (!token || !uploadStore) return null;
    const entry = uploadStore[token];
    if (entry && touch) {
      entry.updatedAt = Date.now();
      persistUploadStore();
    }
    return entry || null;
  }

  function removeUpload(token) {
    if (!token || !uploadStore || !uploadStore[token]) return;
    delete uploadStore[token];
    persistUploadStore();
  }

  function stashSnapshotForUrl(url, snapshot) {
    const storage = getSessionStorageSafe();
    if (!storage) return;
    try {
      if (!snapshot || !Array.isArray(snapshot) || !snapshot.length) {
        storage.removeItem(CLIP_SESSION_KEY_PREFIX + url);
      } else {
        storage.setItem(
          CLIP_SESSION_KEY_PREFIX + url,
          JSON.stringify(snapshot),
        );
      }
    } catch (err) {
      console.debug("Failed to persist clip snapshot", err);
    }
  }

  function readSnapshotForUrl(url) {
    const storage = getSessionStorageSafe();
    if (!storage) return null;
    try {
      const raw = storage.getItem(CLIP_SESSION_KEY_PREFIX + url);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        return parsed;
      }
    } catch (err) {
      console.debug("Failed to load clip snapshot", err);
    }
    return null;
  }

  function clearSnapshotForUrl(url) {
    const storage = getSessionStorageSafe();
    if (!storage) return;
    try {
      storage.removeItem(CLIP_SESSION_KEY_PREFIX + url);
    } catch (err) {
      console.debug("Failed to clear clip snapshot", err);
    }
  }

  function encodeQuery({ query, chips }) {
    const tokens = [];
    const trimmed =
      typeof query === "string" ? query.trim().replace(/\s+/g, " ") : "";
    if (trimmed) {
      tokens.push(`text:${encodeURIComponent(trimmed)}`);
    }
    const source = Array.isArray(chips) ? chips : [];
    source.forEach((chip) => {
      if (!chip || typeof chip !== "object") return;
      const negative = !!chip.negative;
      let value = null;
      if (
        chip.kind === "gallery" &&
        Number.isFinite(chip.imageId) &&
        chip.imageId >= 0
      ) {
        value = String(Math.trunc(Number(chip.imageId)));
      } else if (chip.kind === "upload") {
        const token =
          typeof chip.token === "string" && chip.token
            ? chip.token
            : typeof chip.clipToken === "string" && chip.clipToken
              ? chip.clipToken
              : null;
        if (token) {
          value = token;
        }
      }
      if (!value) return;
      const prefix = negative ? "-image:" : "image:";
      tokens.push(`${prefix}${encodeURIComponent(String(value))}`);
    });
    return tokens.length ? tokens.join(",") : null;
  }

  function decodeQuery(value) {
    const base = {
      mode: "tokens",
      query: "",
      positiveImages: [],
      negativeImages: [],
      uploads: [],
    };
    if (typeof value !== "string" || !value) {
      return { ...base, mode: "empty" };
    }
    if (value.startsWith("state:")) {
      const legacy = decodeLegacyState(value.slice(6));
      legacy.mode = "legacy";
      return legacy;
    }

    const textParts = [];
    const positiveImages = [];
    const negativeImages = [];
    const uploads = [];

    value.split(",").forEach((rawToken) => {
      const trimmed = rawToken.trim();
      if (!trimmed) return;
      let negative = false;
      let body = trimmed;
      if (body.startsWith("-")) {
        negative = true;
        body = body.slice(1);
      }
      if (body.startsWith("text:")) {
        const encoded = body.slice(5);
        if (!negative) {
          try {
            textParts.push(decodeURIComponent(encoded));
          } catch (err) {
            textParts.push(encoded);
          }
        }
        return;
      }
      if (!body.startsWith("image:")) {
        return;
      }
      const encoded = body.slice(6);
      let tokenValue = "";
      try {
        tokenValue = decodeURIComponent(encoded);
      } catch (err) {
        tokenValue = encoded;
      }
      if (!tokenValue) {
        return;
      }
      if (/^\d+$/.test(tokenValue)) {
        const numeric = Number(tokenValue);
        if (negative) {
          if (!negativeImages.includes(numeric)) {
            negativeImages.push(numeric);
          }
        } else if (!positiveImages.includes(numeric)) {
          positiveImages.push(numeric);
        }
        return;
      }
      uploads.push({
        token: tokenValue,
        negative,
      });
    });

    return {
      mode: "tokens",
      query: textParts.join(" ").trim(),
      positiveImages,
      negativeImages,
      uploads,
    };
  }

  function decodeLegacyState(encoded) {
    const fallback = {
      query: "",
      positiveImages: [],
      negativeImages: [],
      uploads: [],
    };
    if (!encoded) return fallback;
    const state = base64DecodeJson(encoded);
    if (!state || typeof state !== "object") {
      return fallback;
    }
    const version = Number(state.v) || 0;
    const query = typeof state.q === "string" ? state.q : "";
    const positiveImages = Array.isArray(state.p)
      ? state.p
      : Array.isArray(state.pos)
        ? state.pos
        : [];
    const negativeImages = Array.isArray(state.n)
      ? state.n
      : Array.isArray(state.neg)
        ? state.neg
        : [];
    let uploads = [];
    if (version >= 2 && Array.isArray(state.u)) {
      uploads = state.u
        .map((entry) => {
          if (!entry || typeof entry !== "object") return null;
          const token =
            typeof entry.t === "string" && entry.t ? entry.t : null;
          if (!token) return null;
          return {
            token,
            negative: entry.n === 1,
            label: typeof entry.l === "string" ? entry.l : "",
          };
        })
        .filter(Boolean);
    } else if (Array.isArray(state.chips)) {
      uploads = state.chips
        .map((chip) => {
          if (!chip || chip.kind !== "upload") return null;
          const token =
            typeof chip.clipToken === "string" && chip.clipToken
              ? chip.clipToken
              : typeof chip.token === "string" && chip.token
                ? chip.token
                : null;
          if (!token) return null;
          return {
            token,
            negative: !!chip.negative,
            label: typeof chip.label === "string" ? chip.label : "",
          };
        })
        .filter(Boolean);
    }

    return {
      query,
      positiveImages: (positiveImages || [])
        .map(Number)
        .filter((num) => Number.isFinite(num)),
      negativeImages: (negativeImages || [])
        .map(Number)
        .filter((num) => Number.isFinite(num)),
      uploads,
    };
  }

  function base64DecodeJson(value) {
    if (typeof value !== "string" || !value) return null;
    try {
      const binary = atob(value);
      const percentEncoded = Array.from(binary)
        .map((char) => `%${char.charCodeAt(0).toString(16).padStart(2, "0")}`)
        .join("");
      const json = decodeURIComponent(percentEncoded);
      return JSON.parse(json);
    } catch (err) {
      console.error("Failed to decode clip state", err);
      return null;
    }
  }

  window.ClipState = {
    encodeQuery,
    decodeQuery,
    createUploadToken,
    recordUpload,
    readUpload,
    removeUpload,
    stashSnapshotForUrl,
    readSnapshotForUrl,
    clearSnapshotForUrl,
    touchUpload(token) {
      return readUpload(token, { touch: true });
    },
  };
})();
