const searchBox = document.getElementById("search");
const searchClearBtn = document.getElementById("search-clear");
const gridEl = document.getElementById("grid");
const statusEl = document.getElementById("status");
const sidebarEl = document.getElementById("sidebar");
const sidebarToggleBtn = document.getElementById("sidebar-toggle");
const statusCardEl = document.getElementById("status-card");
const statusWrapperEl = document.getElementById("status-wrapper");
const clipStatusSection = document.getElementById("clip-status");
const clipSummary = document.getElementById("clip-summary");
const clipProgressBar = document.getElementById("clip-progress-bar");
const clipToggleBtn = document.getElementById("clip-toggle");
const clipSearchInput = document.getElementById("clip-query");
const clipSearchClear = document.getElementById("clip-clear");
const clipChipContainer = document.getElementById("clip-chip-container");
const autoStatusSection = document.getElementById("auto-status");
const autoSummary = document.getElementById("auto-summary");
const autoErrorsList = document.getElementById("auto-errors");
const autoProgressBar = document.getElementById("auto-progress-bar");
const autoToggleBtn = document.getElementById("auto-toggle");
const ratingCardEl = document.getElementById("rating-card");
const ratingFilterInputs = ratingCardEl
  ? Array.from(ratingCardEl.querySelectorAll('input[type="checkbox"]'))
  : [];
const ratingFilterMeta = ratingFilterInputs.map((input) => {
  const label = input.closest("label");
  return {
    input,
    label,
    value: String(input.value || "").toLowerCase(),
    nameEl: label ? label.querySelector(".rating-name") : null,
    countEl: label ? label.querySelector(".rating-count") : null,
  };
});
const detailRatingSection = document.getElementById("detail-rating");
const detailRatingLabel = detailRatingSection
  ? detailRatingSection.querySelector(".rating-label")
  : null;
const ratingBarsContainer = document.getElementById("rating-bars");
const toastStack = document.getElementById("toast-stack");
const dropOverlay = document.getElementById("drop-overlay");
const loadMoreBtn = document.getElementById("load-more");
const suggestionsEl = document.getElementById("tag-suggestions");
const facetListEl = document.getElementById("facet-tags");
const detailOverlay = document.getElementById("detail-overlay");
const detailTitle = document.getElementById("detail-title");
const detailImage = document.getElementById("detail-image");
const detailInfo = document.getElementById("detail-info");
const detailTags = document.getElementById("detail-tags");
const detailNegTags = document.getElementById("detail-neg-tags");
const detailNegSection = document.getElementById("detail-neg-section");
const detailCharSection = document.getElementById("detail-char-section");
const detailCharacters = document.getElementById("detail-characters");
const detailPromptsSection = document.getElementById("detail-prompts");
const detailPrevBtn = document.getElementById("detail-prev");
const detailNextBtn = document.getElementById("detail-next");
const detailCounter = document.getElementById("detail-counter");
const detailCloseBtn = document.getElementById("detail-close");
const detailSimilarBtn = document.getElementById("detail-similar");
if (detailSimilarBtn) detailSimilarBtn.disabled = true;
const hideUCToggleBtn = document.getElementById("toggle-uc");
const sentinel = document.getElementById("scroll-sentinel");
const detailHotspots = document.getElementById("detail-hotspots");
const copyPositiveBtn = document.getElementById("copy-positive");
const copyNegativeBtn = document.getElementById("copy-negative");
const positivePreview = document.getElementById("positive-preview");
const negativePreview = document.getElementById("negative-preview");
const positiveBlock = document.getElementById("prompt-positive-block");
const negativeBlock = document.getElementById("prompt-negative-block");
const copyAllNaiBtn = document.getElementById("copy-all-nai");
const copyAllDanbooruBtn = document.getElementById("copy-all-danbooru");
const copyEmbeddedNaiBtn = document.getElementById("copy-embedded-nai");
const copyEmbeddedDanbooruBtn = document.getElementById(
  "copy-embedded-danbooru",
);
const copyAutoNaiBtn = document.getElementById("copy-auto-nai");
const copyAutoDanbooruBtn = document.getElementById("copy-auto-danbooru");
if (autoProgressBar) {
  autoProgressBar.style.width = "0%";
  autoProgressBar.dataset.label = "0%";
}
const facetLookup = new Map();
const tagToCards = new Map();
const cardElements = new Map();
let suggestionItems = [];
let suggestionIndex = -1;
const headerEl = document.querySelector(".app-header");
const PAGE_SIZE = 40;
const TAG_FETCH_BATCH_SIZE = 80;
let currentHistoryState = {
  query: "",
  detail: null,
  pos: 0,
  clip: null,
  clipSnapshot: null,
};
let pendingScrollIndex = null;
let scrollRestorePending = false;
let scrollSaveScheduled = false;
let lastAnchorIndex = 0;

const searchState = {
  query: "",
  images: [],
  index: new Map(),
  imageTags: new Map(),
  total: 0,
  loading: false,
  done: false,
};

let clipEnabled = true;
let clipModeActive = false;
let lastClipPayload = null;
let clipTotal = 0;
let clipOffset = 0;
let currentClipToken = null;
const clipChipState = {
  items: [],
  seq: 1,
};
let pendingClipSearchOptions = null;

let currentDetailId = null;
let currentDetailIndex = -1;
let hideUCTags = true;
let facetCache = [];
let tagStatsCache = new Map(); // norm|kind -> {tag, norm, kind, freq}
let tagStatsLastModified = 0;
let tagStatsLoading = false;
let autoObserver = null;
let currentPrompts = { positive: "", negative: "" };
let currentHotspotCenters = null;
let currentHotspotDots = [];
let lastQuery = "";
let pendingDetailId = null;
let clipSearchTimer = null;
const CLIP_SEARCH_DEBOUNCE = 400;
let dragCounter = 0;
const desktopMediaQuery = window.matchMedia("(min-width: 1101px)");
let sidebarVisible = desktopMediaQuery.matches;
let statusCardVisible = true;
const STATUS_CARD_STORAGE_KEY = "localbooru.statusCard.expanded";
const statusStorage = getLocalStorageSafe();
if (statusStorage) {
  const storedStatus = statusStorage.getItem(STATUS_CARD_STORAGE_KEY);
  if (storedStatus === "collapsed") {
    statusCardVisible = false;
  } else if (storedStatus === "expanded") {
    statusCardVisible = true;
  }
}

function getLocalStorageSafe() {
  try {
    if (typeof window === "undefined" || !window.localStorage) return null;
    return window.localStorage;
  } catch (err) {
    console.debug("localStorage unavailable", err);
    return null;
  }
}

function getSessionStorageSafe() {
  try {
    if (typeof window === "undefined" || !window.sessionStorage) return null;
    return window.sessionStorage;
  } catch (err) {
    console.debug("sessionStorage unavailable", err);
    return null;
  }
}

updateRatingFilterCounts();

const clipProgressHistory = [];
const autoProgressHistory = [];

function formatEtaLabel(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value <= 0) return "";
  const totalSeconds = Math.max(0, Math.round(value));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const secs = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}h ${minutes.toString().padStart(2, "0")}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${secs.toString().padStart(2, "0")}s`;
  }
  return `${secs}s`;
}

function buildRateSummary(rate, etaSeconds) {
  const value = Number(rate);
  let rateLabel = "—";
  if (Number.isFinite(value) && value > 0) {
    rateLabel =
      value >= 1 ? `${value.toFixed(1)}/min` : `${value.toFixed(2)}/min`;
  }
  let summary = `Rate: ${rateLabel}`;
  const etaLabel = formatEtaLabel(etaSeconds);
  if (etaLabel) {
    summary += ` [ETA ${etaLabel}]`;
  }
  return summary;
}

function updateStatusToggleButton(
  button,
  { state, icon, label, hidden, disabled },
) {
  if (!button) return;
  if (typeof hidden === "boolean") button.hidden = hidden;
  if (typeof disabled === "boolean") button.disabled = disabled;
  if (state) button.dataset.state = state;
  const iconEl = button.querySelector(".status-icon");
  if (iconEl && icon) iconEl.textContent = icon;
  const labelEl = button.querySelector(".status-toggle-label");
  if (labelEl && label) labelEl.textContent = label;
  if (label) button.setAttribute("aria-label", label);
}

function persistStatusCardState(expanded) {
  const storage = getLocalStorageSafe();
  if (!storage) return;
  try {
    storage.setItem(STATUS_CARD_STORAGE_KEY, expanded ? "expanded" : "collapsed");
  } catch (err) {
    console.debug("Unable to persist status panel state", err);
  }
}

function pushProgress(history, completed, total) {
  const now = Date.now();
  history.push({ time: now, completed, total });
  if (history.length > 20) history.shift();
}

function averageRatePerMinute(history) {
  if (!history || history.length < 2) return 0;
  const rates = [];
  for (let i = 1; i < history.length; i += 1) {
    const prev = history[i - 1];
    const curr = history[i];
    const deltaCompleted = Number(curr.completed) - Number(prev.completed);
    const deltaTime = Number(curr.time) - Number(prev.time);
    if (deltaCompleted > 0 && deltaTime > 500) {
      rates.push((deltaCompleted / deltaTime) * 60000);
    }
  }
  if (!rates.length) return 0;
  const sum = rates.reduce((acc, value) => acc + value, 0);
  return sum / rates.length;
}

function computeEtaSeconds(remaining, ratePerMin) {
  if (!Number.isFinite(ratePerMin) || ratePerMin <= 0) return null;
  if (!Number.isFinite(remaining) || remaining <= 0) return null;
  return (remaining / ratePerMin) * 60;
}

function getActiveClipToken() {
  if (!clipModeActive) {
    return null;
  }
  if (currentClipToken) {
    return currentClipToken;
  }
  if (lastClipPayload && typeof lastClipPayload === "object") {
    const encoded = ClipState.encodeQuery({
      query: lastClipPayload.query,
      chips: lastClipPayload.chipsSnapshot || exportClipChips(),
    });
    if (encoded) {
      currentClipToken = encoded;
      return encoded;
    }
  }
  return null;
}

function normalizeDetail(value) {
  if (value === null || value === undefined) return null;
  const num = Number(value);
  if (!Number.isFinite(num)) return null;
  const intVal = Math.trunc(num);
  return intVal >= 0 ? intVal : null;
}

function normalizeIndex(value) {
  if (value === null || value === undefined) return null;
  const num = Number(value);
  if (!Number.isFinite(num)) return null;
  const intVal = Math.trunc(num);
  return intVal >= 0 ? intVal : null;
}

function buildClipFacetSummaryFromImageTags(imageTagMap) {
  const buckets = new Map();
  if (!(imageTagMap instanceof Map)) {
    return [];
  }
  imageTagMap.forEach((tagList) => {
    const tags = Array.isArray(tagList) ? tagList : [];
    const seen = new Set();
    tags.forEach((tag) => {
      if (!tag || typeof tag !== "object") return;
      const norm = typeof tag.norm === "string" ? tag.norm : "";
      if (!norm) return;
      const kind = typeof tag.kind === "string" ? tag.kind : "prompt";
      const key = `${kind}|${norm}`;
      if (seen.has(key)) return;
      seen.add(key);
      if (!buckets.has(key)) {
        buckets.set(key, {
          tag: typeof tag.tag === "string" && tag.tag ? tag.tag : norm,
          norm,
          kind,
          freq: 0,
        });
      }
      const entry = buckets.get(key);
      entry.freq += 1;
    });
  });
  return Array.from(buckets.values()).sort((a, b) => {
    if (b.freq !== a.freq) {
      return b.freq - a.freq;
    }
    return a.tag.localeCompare(b.tag);
  });
}

const activeToasts = new Map();
const toastSuppressions = new Map();

function toastFingerprint(title, body) {
  return `${title || ""}|${body || ""}`;
}

function isToastSuppressed(key, fingerprint) {
  const state = toastSuppressions.get(key);
  return !!state && state.suppressed && state.fingerprint === fingerprint;
}

function showToast(
  key,
  { title, body, variant = "info", autoDismiss = 0, onDismiss = null } = {},
) {
  if (!toastStack) return;
  const fingerprint = toastFingerprint(title, body);
  if (isToastSuppressed(key, fingerprint)) {
    return;
  }
  toastSuppressions.set(key, { suppressed: false, fingerprint });
  let toastEntry = activeToasts.get(key);
  if (!toastEntry) {
    const toastEl = document.createElement("div");
    toastEl.className = `toast${variant === "error" ? " toast-error" : ""}`;
    toastEl.dataset.key = key;
    toastEl.innerHTML = `
            <div class="toast-title">
                <span>${title || ""}</span>
                <button type="button" class="toast-dismiss" aria-label="Dismiss">×</button>
            </div>
            <div class="toast-body">${body || ""}</div>
        `;
    toastStack.appendChild(toastEl);
    const dismissBtn = toastEl.querySelector(".toast-dismiss");
    if (dismissBtn) {
      dismissBtn.addEventListener("click", () =>
        dismissToast(key, { manual: true }),
      );
    }
    toastEntry = { element: toastEl, timer: null, onDismiss, fingerprint };
    activeToasts.set(key, toastEntry);
  } else {
    toastEntry.element.classList.toggle("toast-error", variant === "error");
    const titleEl = toastEntry.element.querySelector(".toast-title span");
    if (titleEl) titleEl.textContent = title || "";
    const bodyEl = toastEntry.element.querySelector(".toast-body");
    if (bodyEl) bodyEl.textContent = body || "";
    toastEntry.onDismiss = onDismiss;
    toastEntry.fingerprint = fingerprint;
  }
  if (toastEntry.timer) {
    clearTimeout(toastEntry.timer);
    toastEntry.timer = null;
  }
  if (autoDismiss > 0) {
    toastEntry.timer = setTimeout(() => dismissToast(key), autoDismiss);
  }
}

function dismissToast(key, options = {}) {
  const { manual = false } = options;
  const toastEntry = activeToasts.get(key);
  if (!toastEntry) {
    if (!manual) {
      toastSuppressions.delete(key);
    }
    return;
  }
  if (toastEntry.timer) {
    clearTimeout(toastEntry.timer);
  }
  toastEntry.element.classList.add("toast-leave");
  const removalDelay = 160;
  setTimeout(() => {
    if (toastEntry.element && toastEntry.element.parentElement) {
      toastEntry.element.parentElement.removeChild(toastEntry.element);
    }
  }, removalDelay);
  activeToasts.delete(key);
  if (manual) {
    toastSuppressions.set(key, {
      suppressed: true,
      fingerprint: toastEntry.fingerprint || "",
    });
  } else {
    toastSuppressions.delete(key);
  }
  if (typeof toastEntry.onDismiss === "function") {
    toastEntry.onDismiss();
  }
}

function truncateLabel(label, maxLength = 42) {
  if (typeof label !== "string") return "";
  if (label.length <= maxLength) return label;
  const head = label.slice(0, Math.max(0, maxLength - 10));
  const tail = label.slice(-8);
  return `${head}…${tail}`;
}

function deriveFilename(item) {
  if (!item) return "";
  if (typeof item.name === "string" && item.name) {
    const parts = item.name.split(/[\\/]/);
    return parts.pop() || item.name;
  }
  if (typeof item.path === "string" && item.path) {
    const segments = item.path.split(/[\\/]/);
    return segments.pop() || item.path;
  }
  return "";
}

function getFallbackLabel(item) {
  const filename = deriveFilename(item);
  return truncateLabel(filename || "untitled", 38);
}

function base64ToFloat32Vector(base64) {
  if (typeof base64 !== "string" || !base64) return null;
  try {
    const binary = atob(base64);
    const { length } = binary;
    if (length % 4 !== 0) {
      console.warn("Unexpected CLIP vector length", length);
      return null;
    }
    const buffer = new ArrayBuffer(length);
    const bytes = new Uint8Array(buffer);
    for (let i = 0; i < length; i += 1) {
      bytes[i] = binary.charCodeAt(i);
    }
    return new Float32Array(buffer);
  } catch (err) {
    console.error("Failed to decode CLIP vector", err);
    return null;
  }
}

function float32ToBase64(vector, { negate = false } = {}) {
  if (!(vector instanceof Float32Array)) {
    return null;
  }
  let view = vector;
  if (negate) {
    view = new Float32Array(vector.length);
    for (let i = 0; i < vector.length; i += 1) {
      view[i] = -vector[i];
    }
  }
  const bytes = new Uint8Array(view.buffer, view.byteOffset, view.byteLength);
  let binary = "";
  const CHUNK = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += CHUNK) {
    const slice = bytes.subarray(offset, offset + CHUNK);
    binary += String.fromCharCode(...slice);
  }
  return btoa(binary);
}

function getChipVectorBase64(chip, { negate = false } = {}) {
  if (!chip || !(chip.vector instanceof Float32Array)) return null;
  if (!chip.vectorCache) {
    chip.vectorCache = {};
  }
  const key = negate ? "negative" : "positive";
  if (chip.vectorCache[key]) {
    return chip.vectorCache[key];
  }
  const encoded = float32ToBase64(chip.vector, { negate });
  if (encoded) {
    chip.vectorCache[key] = encoded;
  }
  return encoded;
}

function clipChipPreviewUrl(chip) {
  if (!chip) return "";
  if (chip.thumbnail) return chip.thumbnail;
  if (chip.previewUrl) return chip.previewUrl;
  if (chip.kind === "gallery" && Number.isFinite(chip.imageId)) {
    return `/thumbs/${chip.imageId}`;
  }
  return "";
}

function setClipChipBackground(element, url) {
  if (!element) return;
  if (!url) {
    element.style.backgroundImage = "none";
    return;
  }
  const safeUrl = url.replace(/["'\\]/g, "\\$&");
  element.style.backgroundImage = `url("${safeUrl}")`;
}

function destroyClipChipPreview(chip) {
  if (chip && chip.previewUrl) {
    try {
      URL.revokeObjectURL(chip.previewUrl);
    } catch (err) {
      console.debug("Failed to revoke preview URL", err);
    }
    chip.previewUrl = null;
  }
}

function updateClipSearchClearVisibility() {
  if (!clipSearchClear) return;
  const hasText =
    clipSearchInput && clipSearchInput.value && clipSearchInput.value.trim();
  const hasChips = clipChipState.items.length > 0;
  if (hasText || hasChips) {
    clipSearchClear.classList.add("input-action-visible");
  } else {
    clipSearchClear.classList.remove("input-action-visible");
  }
}

function renderClipChips() {
  if (!clipChipContainer) {
    updateClipSearchClearVisibility();
    return;
  }
  clipChipContainer.innerHTML = "";
  if (!clipChipState.items.length) {
    updateClipSearchClearVisibility();
    return;
  }
  clipChipState.items.forEach((chip) => {
    if (!chip) return;
    const chipEl = document.createElement("div");
    chipEl.className = "clip-chip";
    chipEl.dataset.id = String(chip.id);
    if (chip.negative) {
      chipEl.classList.add("clip-chip-negative");
    }
    if (chip.status === "pending") {
      chipEl.classList.add("clip-chip-pending");
    }
    chipEl.setAttribute("role", "group");
    const labelParts = [];
    if (chip.label) labelParts.push(chip.label);
    if (chip.kind === "gallery" && Number.isFinite(chip.imageId)) {
      labelParts.push(`image ${chip.imageId}`);
    }
    if (chip.negative) {
      labelParts.push("negative");
    }
    chipEl.title = labelParts.join(" • ");

    const thumbEl = document.createElement("div");
    thumbEl.className = "clip-chip-thumb";
    setClipChipBackground(thumbEl, clipChipPreviewUrl(chip));
    chipEl.appendChild(thumbEl);

    if (chip.status === "pending") {
      const spinner = document.createElement("div");
      spinner.className = "clip-chip-spinner";
      spinner.setAttribute("aria-hidden", "true");
      chipEl.appendChild(spinner);
    }

    const actionsEl = document.createElement("div");
    actionsEl.className = "clip-chip-actions";

    const toggleBtn = document.createElement("button");
    toggleBtn.type = "button";
    toggleBtn.className = "clip-chip-action clip-chip-toggle";
    toggleBtn.dataset.action = "toggle";
    toggleBtn.dataset.id = String(chip.id);
    toggleBtn.title = chip.negative
      ? "Use as positive reference"
      : "Use as negative reference";
    toggleBtn.setAttribute(
      "aria-label",
      chip.negative ? "Use as positive reference" : "Use as negative reference",
    );
    toggleBtn.textContent = chip.negative ? "+" : "-";
    const toggleDisabled =
      chip.status !== "ready" && chip.kind !== "gallery"
        ? true
        : chip.kind === "upload" && !(chip.vector instanceof Float32Array);
    toggleBtn.disabled = !!toggleDisabled;
    actionsEl.appendChild(toggleBtn);

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "clip-chip-action clip-chip-remove";
    removeBtn.dataset.action = "remove";
    removeBtn.dataset.id = String(chip.id);
    removeBtn.title = "Remove image";
    removeBtn.setAttribute("aria-label", "Remove image");
    removeBtn.textContent = "x";
    actionsEl.appendChild(removeBtn);

    chipEl.appendChild(actionsEl);
    clipChipContainer.appendChild(chipEl);
  });
  updateClipSearchClearVisibility();
}

async function handleClipPaste(event) {
  if (!clipEnabled) return;
  const clipboard = event.clipboardData;
  if (!clipboard) return;
  const files = Array.from(clipboard.files || []).filter(
    (file) =>
      file && typeof file.type === "string" && file.type.startsWith("image/"),
  );
  if (!files.length) return;
  event.preventDefault();
  for (const file of files) {
    // eslint-disable-next-line no-await-in-loop
    await startClipUploadSearch(file);
  }
}

if (clipSearchInput) {
  clipSearchInput.addEventListener("paste", (event) => {
    handleClipPaste(event);
  });
}

function addClipChip(entry) {
  const chip = {
    id: clipChipState.seq++,
    kind: entry.kind,
    imageId: Number.isFinite(entry.imageId) ? Number(entry.imageId) : null,
    token: entry.token || entry.clipToken || null,
    label: entry.label || "",
    negative: !!entry.negative,
    status: entry.status || "pending",
    thumbnail: entry.thumbnail || null,
    previewUrl: entry.previewUrl || null,
    vector:
      entry.vector instanceof Float32Array
        ? entry.vector
        : base64ToFloat32Vector(entry.vector),
    vectorCache: {},
    uploadData: entry.uploadData || null,
  };
  if (!(chip.vector instanceof Float32Array)) {
    chip.vector = null;
  }
  clipChipState.items.push(chip);
  renderClipChips();
  return chip;
}

function findClipChipById(chipId) {
  return clipChipState.items.find((chip) => chip && chip.id === chipId) || null;
}

function updateClipChip(chipId, updates = {}, { silent = false } = {}) {
  const chip = findClipChipById(chipId);
  if (!chip) return null;
  if ("vector" in updates) {
    const vector =
      updates.vector instanceof Float32Array
        ? updates.vector
        : base64ToFloat32Vector(updates.vector);
    chip.vector = vector instanceof Float32Array ? vector : null;
    chip.vectorCache = {};
  }
  if ("thumbnail" in updates) {
    chip.thumbnail = updates.thumbnail || null;
  }
  if ("previewUrl" in updates) {
    if (chip.previewUrl && chip.previewUrl !== updates.previewUrl) {
      destroyClipChipPreview(chip);
    }
    chip.previewUrl = updates.previewUrl || chip.previewUrl;
  }
  if ("token" in updates || "clipToken" in updates) {
    const nextToken =
      typeof updates.token === "string" && updates.token
        ? updates.token
        : typeof updates.clipToken === "string" && updates.clipToken
          ? updates.clipToken
          : null;
    chip.token = nextToken;
    if (chip.token) {
      removeClipChips(
        (other) => other.id !== chip.id && other.token === chip.token,
        { silent: true },
      );
    }
  }
  if ("uploadData" in updates) {
    chip.uploadData = updates.uploadData || null;
  }
  if ("label" in updates) {
    chip.label = updates.label || "";
  }
  if ("negative" in updates) {
    chip.negative = !!updates.negative;
  }
  if ("status" in updates) {
    chip.status = updates.status || "pending";
  }
  if ("imageId" in updates) {
    chip.imageId = Number.isFinite(updates.imageId)
      ? Number(updates.imageId)
      : chip.imageId;
  }
  if (!silent) {
    renderClipChips();
  } else {
    updateClipSearchClearVisibility();
  }
  return chip;
}

function removeClipChip(chipId, { silent = false } = {}) {
  const nextItems = [];
  clipChipState.items.forEach((chip) => {
    if (!chip) return;
    if (chip.id === chipId) {
      destroyClipChipPreview(chip);
      return;
    }
    nextItems.push(chip);
  });
  clipChipState.items = nextItems;
  if (!silent) {
    renderClipChips();
  } else {
    updateClipSearchClearVisibility();
  }
}

function clearClipChips({ silent = false } = {}) {
  clipChipState.items.forEach((chip) => destroyClipChipPreview(chip));
  clipChipState.items = [];
  if (!silent) {
    renderClipChips();
  } else {
    updateClipSearchClearVisibility();
  }
}

function removeClipChips(predicate, { silent = false } = {}) {
  if (typeof predicate !== "function") return;
  const next = [];
  clipChipState.items.forEach((chip) => {
    if (!chip) return;
    if (predicate(chip)) {
      destroyClipChipPreview(chip);
    } else {
      next.push(chip);
    }
  });
  clipChipState.items = next;
  if (!silent) {
    renderClipChips();
  } else {
    updateClipSearchClearVisibility();
  }
}

function exportClipChips() {
  return clipChipState.items.map((chip) => ({
    kind: chip.kind,
    imageId: chip.imageId,
    negative: chip.negative,
    token: chip.token || null,
    label: chip.label,
    status: chip.status,
  }));
}

function rebuildClipChipsFromSnapshot(snapshot) {
  clearClipChips({ silent: true });
  const source = Array.isArray(snapshot) ? snapshot : [];
  const missingUploads = [];
  source.forEach((entry) => {
    if (!entry || typeof entry !== "object") {
      return;
    }
    if (entry.kind === "upload") {
      const token = entry.token || entry.clipToken || null;
      if (!token) {
        missingUploads.push(entry.label || "pasted image");
        return;
      }
      const cache = ClipState.readUpload(token, { touch: true });
      if (!cache || typeof cache.vector !== "string" || !cache.vector) {
        missingUploads.push(entry.label || "pasted image");
        return;
      }
      const vector = base64ToFloat32Vector(cache.vector);
      if (!(vector instanceof Float32Array)) {
        missingUploads.push(entry.label || "pasted image");
        return;
      }
      const thumbnailData =
        entry.thumbnail ||
        (cache.thumbnail
          ? cache.thumbnail.startsWith("data:")
            ? cache.thumbnail
            : `data:image/png;base64,${cache.thumbnail}`
          : null);
      addClipChip({
        kind: "upload",
        token,
        negative: !!entry.negative,
        vector,
        label: entry.label || cache.label || "pasted image",
        thumbnail: thumbnailData,
        status: "ready",
      });
      return;
    }
    addClipChip({
      kind: entry.kind,
      imageId: entry.imageId,
      negative: entry.negative,
      label: entry.label,
      status: entry.status || "ready",
    });
  });
  renderClipChips();
  if (missingUploads.length) {
    showToast("clip-upload-missing", {
      title: "Missing image uploads",
      body:
        missingUploads.length === 1
          ? `${missingUploads[0]} was not cached; removed from CLIP query.`
          : `${missingUploads.length} cached uploads were unavailable and removed from the CLIP query.`,
      variant: "error",
      autoDismiss: 0,
    });
  }
}

function buildClipSearchPayloadFromState(overrides = {}) {
  const {
    tagQuery: overrideTagQuery,
    query: overrideTextQuery,
    chipsSnapshot: _ignoredSnapshot,
    ...payloadOverrides
  } = overrides || {};
  const tagQuery =
    typeof overrideTagQuery === "string"
      ? overrideTagQuery
      : (searchBox?.value || "").trim();
  const textQuery =
    typeof overrideTextQuery === "string"
      ? overrideTextQuery
      : (clipSearchInput?.value || "").trim();
  const positiveIds = new Set();
  const negativeIds = new Set();
  const positiveVectors = [];
  const negativeVectors = [];
  const removedUploads = [];
  const chipsToRemove = [];
  let pendingUploads = false;

  clipChipState.items.forEach((chip) => {
    if (!chip) return;
    if (chip.kind === "gallery" && Number.isFinite(chip.imageId)) {
      if (chip.negative) {
        negativeIds.add(Number(chip.imageId));
      } else {
        positiveIds.add(Number(chip.imageId));
      }
      return;
    }
    if (chip.kind !== "upload") {
      return;
    }

    if (!(chip.vector instanceof Float32Array)) {
      const cache =
        chip.token && typeof chip.token === "string"
          ? ClipState.readUpload(chip.token, { touch: true })
          : null;
      if (cache && typeof cache.vector === "string" && cache.vector) {
        const cachedVector = base64ToFloat32Vector(cache.vector);
        if (cachedVector instanceof Float32Array) {
          const cachedThumb =
            chip.thumbnail ||
            (cache.thumbnail
              ? cache.thumbnail.startsWith("data:")
                ? cache.thumbnail
                : `data:image/png;base64,${cache.thumbnail}`
              : null);
          updateClipChip(
            chip.id,
            {
              vector: cachedVector,
              thumbnail: cachedThumb || chip.thumbnail,
              status: "ready",
            },
            { silent: true },
          );
        }
      }
    }

    if (chip.vector instanceof Float32Array) {
      const encoded = getChipVectorBase64(chip);
      if (encoded) {
        if (chip.negative) {
          negativeVectors.push(encoded);
        } else {
          positiveVectors.push(encoded);
        }
      }
      return;
    }

    if (chip.status === "pending" || !chip.token) {
      pendingUploads = true;
      return;
    }

    chipsToRemove.push(chip.id);
    removedUploads.push(chip.label || "pasted image");
  });

  if (chipsToRemove.length) {
    chipsToRemove.forEach((chipId) =>
      removeClipChip(chipId, { silent: true }),
    );
    renderClipChips();
    updateClipSearchClearVisibility();
    console.warn("[clip] Removed chips after cache check", {
      removedCount: chipsToRemove.length,
      removedUploads,
    });
  }

  const snapshot = exportClipChips();

  const payload = {
    query: textQuery,
    positiveImages: Array.from(positiveIds),
    negativeImages: Array.from(negativeIds),
    tagQuery,
    chipsSnapshot: snapshot,
  };
  if (positiveVectors.length) {
    payload.positiveVectors = positiveVectors;
  }
  if (negativeVectors.length) {
    payload.negativeVectors = negativeVectors;
  }
  return {
    payload: { ...payload, ...payloadOverrides },
    removedUploads,
    pendingUploads,
  };
}

function triggerClipSearchFromState(options = {}) {
  const { payload, removedUploads, pendingUploads } = buildClipSearchPayloadFromState(
    options.payloadOverrides,
  );
  if (removedUploads.length) {
    showToast("clip-upload-removed", {
      title: "Removed cached uploads",
      body:
        removedUploads.length === 1
          ? `${removedUploads[0]} was removed because its cached data is unavailable.`
          : `${removedUploads.length} uploads were removed because their cached data is unavailable.`,
      variant: "error",
      autoDismiss: 0,
    });
    const sanitizedSnapshot = exportClipChips();
    const sanitizedToken =
      ClipState.encodeQuery({
        query:
          (payload && typeof payload.query === "string" && payload.query) ||
          lastQuery ||
          "",
        chips: sanitizedSnapshot,
      }) || null;
    pushHistoryState(
      {
        clip: sanitizedToken,
        clipSnapshot: sanitizedSnapshot.length ? sanitizedSnapshot : null,
        pos: sanitizedToken ? currentHistoryState.pos : 0,
      },
      { replace: true },
    );
    console.warn("[clip] Removed cached uploads", {
      removedUploads,
      sanitizedToken,
      sanitizedSnapshotLength: sanitizedSnapshot.length,
    });
    currentClipToken = sanitizedToken;
    if (!sanitizedToken) {
      clipModeActive = false;
      lastClipPayload = null;
      currentClipToken = null;
      clipOffset = 0;
      clipTotal = 0;
      if (clipSearchInput) {
        clipSearchInput.value = "";
        updateClipSearchClearVisibility();
      }
      pendingScrollIndex = 0;
      scrollRestorePending = false;
      fetchImages(true);
      return Promise.resolve();
    }
  }
  if (pendingUploads) {
    statusEl.textContent = "Processing image…";
    return Promise.resolve();
  }
  if (!payload) {
    return Promise.resolve();
  }
  return runClipSearch(payload, options);
}

function scheduleClipSearch({
  debounce = true,
  append = false,
  updateHistory = true,
  payloadOverrides = undefined,
} = {}) {
  pendingClipSearchOptions = {
    append,
    updateHistory,
    payloadOverrides,
  };
  if (clipSearchTimer) {
    clearTimeout(clipSearchTimer);
    clipSearchTimer = null;
  }
  const delay = debounce ? CLIP_SEARCH_DEBOUNCE : 0;
  clipSearchTimer = setTimeout(() => {
    clipSearchTimer = null;
    if (searchState.loading) {
      return;
    }
    const nextOptions = pendingClipSearchOptions || {
      append: false,
      updateHistory: true,
      payloadOverrides,
    };
    pendingClipSearchOptions = null;
    triggerClipSearchFromState(nextOptions);
  }, delay);
}

function exitClipMode({ fetch = true } = {}) {
  if (!clipModeActive) {
    lastClipPayload = null;
    currentClipToken = null;
    if (!fetch) {
      pushHistoryState({ clip: null, clipSnapshot: null }, { replace: true });
    }
    updateClipSearchClearVisibility();
    clipModeActive = false;
    return;
  }
  if (clipSearchTimer) {
    clearTimeout(clipSearchTimer);
    clipSearchTimer = null;
  }
  pendingClipSearchOptions = null;
  if (detailOverlay.classList.contains("active")) {
    closeDetail({ skipHistory: true });
  }
  clipModeActive = false;
  lastClipPayload = null;
  currentClipToken = null;
  clipOffset = 0;
  clipTotal = 0;
  pendingDetailId = null;
  if (fetch) {
    pushHistoryState(
      { query: lastQuery, detail: null, pos: 0, clip: null, clipSnapshot: null },
      { replace: true },
    );
    fetchImages(true);
  } else {
    pushHistoryState({ clip: null, clipSnapshot: null }, { replace: true });
  }
  updateStatus();
}

if (clipChipContainer) {
  clipChipContainer.addEventListener("click", (event) => {
    const actionButton = event.target.closest(".clip-chip-action");
    if (!actionButton) return;
    const chipId = Number(actionButton.dataset.id);
    if (!Number.isFinite(chipId)) return;
    const action = actionButton.dataset.action;
    if (action === "remove") {
      removeClipChip(chipId);
      updateClipSearchClearVisibility();
      const hasText = !!(clipSearchInput && clipSearchInput.value.trim());
      if (!hasText && clipChipState.items.length === 0) {
        const shouldFetch = clipModeActive && !searchState.loading;
        exitClipMode({ fetch: shouldFetch });
        return;
      }
      scheduleClipSearch({ debounce: false, append: false, updateHistory: true });
    } else if (action === "toggle") {
      const chip = findClipChipById(chipId);
      if (!chip) return;
      if (chip.kind === "upload" && chip.status !== "ready") return;
      updateClipChip(chipId, { negative: !chip.negative });
      scheduleClipSearch({ debounce: false, append: false, updateHistory: true });
    }
  });
}

function syncClearButton(input, button) {
  if (!button) return;
  if (input && input.value && input.value.trim()) {
    button.classList.add("input-action-visible");
  } else {
    button.classList.remove("input-action-visible");
  }
}

function applySidebarState({ syncStatus = true } = {}) {
  if (!sidebarEl) return;
  const isDesktop = desktopMediaQuery.matches;
  if (isDesktop) {
    sidebarVisible = true;
    sidebarEl.classList.remove("sidebar-open");
    sidebarEl.classList.remove("collapsed");
  } else {
    sidebarEl.classList.remove("collapsed");
    sidebarEl.classList.toggle("sidebar-open", sidebarVisible);
  }
  if (syncStatus) {
    setStatusCardExpanded(statusCardVisible, { animate: false });
  }
  if (sidebarToggleBtn) {
    const expanded = isDesktop ? statusCardVisible : sidebarVisible;
    sidebarToggleBtn.setAttribute("aria-expanded", expanded ? "true" : "false");
    sidebarToggleBtn.classList.toggle("is-open", expanded);
  }
}

if (sidebarToggleBtn) {
  sidebarToggleBtn.addEventListener("click", () => {
    if (desktopMediaQuery.matches) {
      setStatusCardExpanded(!statusCardVisible, { animate: true });
    } else {
      sidebarVisible = !sidebarVisible;
      if (sidebarVisible) {
        setStatusCardExpanded(true, { animate: false });
      }
    }
    applySidebarState({ syncStatus: false });
  });
}

desktopMediaQuery.addEventListener("change", (event) => {
  if (event.matches) {
    sidebarVisible = true;
  } else {
    sidebarVisible = false;
  }
  applySidebarState({ syncStatus: false });
  setStatusCardExpanded(statusCardVisible, { animate: false });
});

applySidebarState();

function updateStatusCardHeight() {
  if (!statusWrapperEl || !statusCardEl) return;
  if (!statusCardVisible) return;
  statusWrapperEl.style.maxHeight = "none";
  statusWrapperEl.style.overflow = "visible";
}

function setStatusCardExpanded(expand, { animate = true } = {}) {
  statusCardVisible = !!expand;
  persistStatusCardState(statusCardVisible);
  if (!statusWrapperEl || !statusCardEl) return;
  const wrapper = statusWrapperEl;
  const content = statusCardEl;

  const finishTransition = (expanded) => {
    if (expanded) {
      wrapper.style.transition = "";
      wrapper.style.maxHeight = "none";
      wrapper.style.overflow = "visible";
    } else {
      wrapper.classList.add("collapsed");
      wrapper.style.transition = "";
      wrapper.style.overflow = "hidden";
    }
  };

  if (!animate) {
    wrapper.style.transition = "none";
    if (statusCardVisible) {
      wrapper.classList.remove("collapsed");
      wrapper.style.maxHeight = "none";
      wrapper.style.opacity = "1";
      wrapper.style.overflow = "visible";
    } else {
      wrapper.classList.add("collapsed");
      wrapper.style.maxHeight = "0px";
      wrapper.style.opacity = "0";
      wrapper.style.overflow = "hidden";
    }
    // force reflow then clear transition so subsequent animations work
    requestAnimationFrame(() => {
      wrapper.style.transition = "";
    });
    return;
  }

  const handler = (event) => {
    if (event.propertyName !== "max-height") {
      return;
    }
    wrapper.removeEventListener("transitionend", handler);
    finishTransition(statusCardVisible);
  };

  wrapper.removeEventListener("transitionend", handler);
  wrapper.addEventListener("transitionend", handler);

  if (statusCardVisible) {
    const target = content.scrollHeight;
    wrapper.classList.remove("collapsed");
    wrapper.style.overflow = "hidden";
    wrapper.style.transition = "none";
    wrapper.style.maxHeight = "0px";
    wrapper.style.opacity = "0";
    // force reflow
    wrapper.getBoundingClientRect();
    wrapper.style.transition = "max-height 0.28s ease, opacity 0.24s ease";
    wrapper.style.maxHeight = `${target}px`;
    wrapper.style.opacity = "1";
  } else {
    const current = wrapper.offsetHeight || content.scrollHeight;
    wrapper.style.overflow = "hidden";
    wrapper.style.transition = "none";
    wrapper.style.maxHeight = `${current}px`;
    wrapper.style.opacity = "1";
    wrapper.getBoundingClientRect();
    wrapper.style.transition = "max-height 0.24s ease, opacity 0.24s ease";
    wrapper.style.maxHeight = "0px";
    wrapper.style.opacity = "0";
  }
}

function applyTagsToCard(imageId, tags) {
  if (!cardElements.has(imageId)) {
    return;
  }
  const normalized = [];
  if (Array.isArray(tags)) {
    tags.forEach((tag) => {
      if (!tag || typeof tag !== "object") return;
      const norm = typeof tag.norm === "string" ? tag.norm : "";
      if (!norm) return;
      const kind = typeof tag.kind === "string" ? tag.kind : "prompt";
      const label = typeof tag.tag === "string" && tag.tag ? tag.tag : norm;
      const emphasis =
        typeof tag.emphasis === "string" ? tag.emphasis : "normal";
      const weight = Number.isFinite(tag.weight) ? Number(tag.weight) : 1;
      const source =
        typeof tag.source === "string" && tag.source ? tag.source : "embedded";
      normalized.push({ tag: label, norm, kind, emphasis, weight, source });
    });
  }

  const previous = searchState.imageTags.get(imageId) || [];
  const previousKeys = new Set(
    previous.map((tag) => `${tag.kind}|${tag.norm}`),
  );
  previousKeys.forEach((key) => {
    const bucket = tagToCards.get(key);
    if (bucket) {
      bucket.delete(imageId);
      if (!bucket.size) {
        tagToCards.delete(key);
      }
    }
  });

  searchState.imageTags.set(imageId, normalized);

  const newKeys = new Set();
  normalized.forEach((tag) => {
    const key = `${tag.kind}|${tag.norm}`;
    if (newKeys.has(key)) return;
    newKeys.add(key);
    if (!tagToCards.has(key)) {
      tagToCards.set(key, new Set());
    }
    tagToCards.get(key).add(imageId);
  });
}

async function loadTagsForImageIds(imageIds) {
  if (!clipModeActive) {
    return;
  }
  const uniqueIds = Array.from(
    new Set((Array.isArray(imageIds) ? imageIds : []).map(Number)),
  ).filter((id) => Number.isFinite(id) && id >= 0);
  const missing = uniqueIds.filter((id) => {
    const tags = searchState.imageTags.get(id);
    return !tags || !tags.length;
  });
  if (!missing.length) {
    return;
  }
  for (let index = 0; index < missing.length; index += TAG_FETCH_BATCH_SIZE) {
    if (!clipModeActive) {
      return;
    }
    const batch = missing.slice(index, index + TAG_FETCH_BATCH_SIZE);
    await fetchTagBatch(batch);
  }
  if (!clipModeActive) {
    return;
  }
  facetCache = buildClipFacetSummaryFromImageTags(searchState.imageTags);
  renderFacets(facetCache);
}

async function fetchTagBatch(batchIds) {
  if (!Array.isArray(batchIds) || !batchIds.length) {
    return;
  }
  try {
    const res = await fetch("/api/image-tags", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids: batchIds }),
    });
    if (!res.ok) throw new Error(`tag fetch failed: ${res.status}`);
    const payload = await res.json();
    if (!clipModeActive) {
      return;
    }
    const tagMap = payload && payload.tags;
    if (tagMap && typeof tagMap === "object") {
      Object.entries(tagMap).forEach(([idStr, tagList]) => {
        const imageId = Number(idStr);
        if (!Number.isFinite(imageId)) return;
        if (!cardElements.has(imageId)) return;
        const tags = Array.isArray(tagList) ? tagList : [];
        applyTagsToCard(imageId, tags);
      });
    }
  } catch (err) {
    console.error("Failed to load tags for images", err);
  }
}

async function startClipUploadSearch(file) {
  if (!file || !(file instanceof File)) {
    return;
  }
  if (!file.type || !file.type.toLowerCase().startsWith("image/")) {
    statusEl.textContent = "Please drop an image file";
    return;
  }
  const label = truncateLabel(file.name || "upload", 36);
  let previewUrl = null;
  try {
    previewUrl = URL.createObjectURL(file);
  } catch (err) {
    console.debug("Unable to create preview for clip upload", err);
  }

  removeClipChips(
    (chip) =>
      chip.kind === "upload" &&
      (!chip.token || chip.label === label || chip.status !== "ready"),
    { silent: true },
  );

  const chip = addClipChip({
    kind: "upload",
    label,
    previewUrl,
    status: "pending",
    negative: false,
  });

  statusEl.textContent = "Processing image…";

  const formData = new FormData();
  formData.append("file", file, file.name || "upload");

  try {
    const res = await fetch("/api/clip/embed", {
      method: "POST",
      body: formData,
    });
    if (!res.ok) throw new Error(`clip embed failed: ${res.status}`);
    const data = await res.json();
    const vectorString =
      typeof data.vector === "string" && data.vector ? data.vector : null;
    const vector = vectorString ? base64ToFloat32Vector(vectorString) : null;
    const vectorId =
      typeof data.vector_id === "string" && data.vector_id
        ? data.vector_id
        : null;
    const thumbnail =
      typeof data.thumbnail === "string" && data.thumbnail
        ? `data:image/png;base64,${data.thumbnail}`
        : null;
    const filename =
      typeof data.filename === "string" && data.filename
        ? truncateLabel(data.filename, 36)
        : label;

    if (!(vector instanceof Float32Array)) {
      throw new Error("Missing CLIP vector for upload");
    }

    const clipToken = vectorId || ClipState.createUploadToken();
    ClipState.recordUpload(clipToken, {
      vector: vectorString,
      thumbnail:
        typeof data.thumbnail === "string" && data.thumbnail
          ? data.thumbnail
          : null,
      label: filename,
      mimeType:
        typeof data.mime_type === "string" && data.mime_type
          ? data.mime_type
          : file.type || "",
      size: Number.isFinite(file.size) ? Number(file.size) : null,
    });
    if (thumbnail) {
      destroyClipChipPreview(chip);
    }
    updateClipChip(
      chip.id,
      {
        vector,
        token: clipToken,
        thumbnail,
        status: "ready",
        label: filename,
      },
      { silent: true },
    );
    renderClipChips();
    clipModeActive = true;
    lastClipPayload = null;
    currentClipToken = null;
    clipOffset = 0;
    clipTotal = 0;
    scheduleClipSearch({ debounce: false, append: false, updateHistory: true });
  } catch (err) {
    console.error("Image similarity search failed", err);
    statusEl.textContent = "Image search failed";
    removeClipChip(chip.id);
  }
}

function buildClipPayloadFromToken(token, tagQuery) {
  const decoded = ClipState.decodeQuery(token);
  if (!decoded) return null;

  const applyDecodedState = (details) => {
    const positiveImages = Array.isArray(details.positiveImages)
      ? details.positiveImages.map(Number).filter(Number.isFinite)
      : [];
    const negativeImages = Array.isArray(details.negativeImages)
      ? details.negativeImages.map(Number).filter(Number.isFinite)
      : [];
    const uploads = Array.isArray(details.uploads) ? details.uploads : [];
    const text = typeof details.query === "string" ? details.query.trim() : "";

    const snapshot = [];
    positiveImages.forEach((id) => {
      snapshot.push({ kind: "gallery", imageId: id, negative: false });
    });
    negativeImages.forEach((id) => {
      snapshot.push({ kind: "gallery", imageId: id, negative: true });
    });
    uploads.forEach((entry) => {
      if (!entry || typeof entry.token !== "string" || !entry.token) return;
      const cache = ClipState.readUpload(entry.token, { touch: true });
      snapshot.push({
        kind: "upload",
        token: entry.token,
        negative: !!entry.negative,
        label:
          typeof entry.label === "string" && entry.label
            ? entry.label
            : cache && typeof cache.label === "string"
              ? cache.label
              : "",
      });
    });

    clearClipChips({ silent: true });
    if (snapshot.length) {
      rebuildClipChipsFromSnapshot(snapshot);
    } else {
      renderClipChips();
    }
    if (clipSearchInput) {
      clipSearchInput.value = text;
    }
    updateClipSearchClearVisibility();
    console.warn("[clip] applyDecodedState rebuilt chips", {
      positiveImages,
      negativeImages,
      uploadCount: uploads.length,
      snapshotSize: snapshot.length,
    });
    return {
      query: text,
      positiveImages,
      negativeImages,
      tagQuery,
      updateInput: text,
      chipsSnapshot: exportClipChips(),
    };
  };

  if (decoded.mode === "legacy") {
    return applyDecodedState(decoded);
  }

  if (decoded.mode === "tokens" || decoded.mode === "empty") {
    return applyDecodedState(decoded);
  }

  return null;
}

function parseStateFromLocation() {
  const params = new URLSearchParams(window.location.search);
  const query = (params.get("q") || "").trim();
  const detailParam = params.get("detail");
  const posParam = params.get("pos");
  const clipParam = params.get("clip");
  const snapshot = ClipState.readSnapshotForUrl(
    `${window.location.pathname}${window.location.search}`,
  );
  return {
    query,
    detail: normalizeDetail(detailParam),
    pos: normalizeIndex(posParam),
    clip: clipParam || null,
    clipSnapshot: snapshot,
  };
}

function buildUrlFromState(state) {
  const params = new URLSearchParams();
  if (state.query) params.set("q", state.query);
  if (state.detail !== null && state.detail !== undefined) {
    const normalizedDetail = normalizeDetail(state.detail);
    if (normalizedDetail !== null) {
      params.set("detail", String(normalizedDetail));
    }
  }
  const normalizedPos = normalizeIndex(state.pos);
  if (normalizedPos !== null && normalizedPos > 0) {
    params.set("pos", String(normalizedPos));
  }
  if (state.clip) {
    params.set("clip", state.clip);
  }
  const search = params.toString();
  return `${window.location.pathname}${search ? `?${search}` : ""}`;
}

function buildDetailLink(imageId) {
  const numericId = Number(imageId);
  if (!Number.isFinite(numericId) || numericId <= 0) {
    return "/";
  }
  const baseState = currentHistoryState || {};
  const state = {
    query: typeof baseState.query === "string" ? baseState.query : "",
    detail: numericId,
    pos: 0,
    clip: baseState.clip || null,
  };
  const url = buildUrlFromState(state);
  return url || `/?detail=${encodeURIComponent(numericId)}`;
}

function pushHistoryState(state, { replace = false } = {}) {
  const queryValue = (state.query ?? currentHistoryState.query ?? "").trim();
  const detailValue =
    state.detail !== undefined
      ? normalizeDetail(state.detail)
      : normalizeDetail(currentHistoryState.detail);
  const posCandidate =
    state.pos !== undefined
      ? normalizeIndex(state.pos)
      : normalizeIndex(currentHistoryState.pos);
  const clipValue =
    state.clip !== undefined ? state.clip : (currentHistoryState.clip ?? null);
  const clipSnapshotValue =
    state.clipSnapshot !== undefined
      ? state.clipSnapshot
      : clipModeActive
        ? exportClipChips()
        : null;
  const normalizedSnapshot =
    Array.isArray(clipSnapshotValue) && clipSnapshotValue.length
      ? clipSnapshotValue
      : null;
  const normalizedState = {
    query: queryValue,
    detail: detailValue,
    pos: posCandidate ?? 0,
    clip: clipValue || null,
    clipSnapshot: normalizedSnapshot,
  };
  const url = buildUrlFromState(normalizedState);
  if (replace) {
    history.replaceState(normalizedState, "", url);
  } else {
    history.pushState(normalizedState, "", url);
  }
  currentHistoryState = normalizedState;
  currentClipToken = normalizedState.clip;
  ClipState.stashSnapshotForUrl(url, normalizedSnapshot);
}
copyPositiveBtn.disabled = true;
copyNegativeBtn.disabled = true;
detailPromptsSection.style.display = "none";

function copyText(text) {
  if (!text) return;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard
      .writeText(text)
      .catch((err) => console.error("Clipboard error", err));
  } else {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    try {
      document.execCommand("copy");
    } catch (err) {
      console.error("Clipboard fallback failed", err);
    }
    document.body.removeChild(textarea);
  }
}

function setActiveSuggestion(index) {
  suggestionIndex = index;
  suggestionItems.forEach((item, idx) => {
    if (!item) return;
    if (idx === index) {
      item.classList.add("active");
    } else {
      item.classList.remove("active");
    }
  });
  if (index >= 0 && suggestionItems[index]) {
    suggestionItems[index].scrollIntoView({ block: "nearest" });
  }
}

function rebuildSuggestionItems() {
  suggestionItems = Array.from(suggestionsEl.querySelectorAll("li"));
}

function formatFileSize(bytes) {
  if (!Number.isFinite(bytes)) return "–";
  const thresh = 1024;
  if (bytes < thresh) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let u = -1;
  do {
    bytes /= thresh;
    ++u;
  } while (bytes >= thresh && u < units.length - 1);
  return `${bytes.toFixed(bytes >= 10 ? 0 : 1)} ${units[u]}`;
}

const RATING_CLASSES = ["general", "sensitive", "questionable", "explicit"];
const RATING_DISPLAY_NAMES = {
  general: "General",
  sensitive: "Sensitive",
  questionable: "Questionable",
  explicit: "Explicit",
};

function getSearchTokensList() {
  const current = searchBox.value ? searchBox.value.trim() : "";
  if (!current) {
    return [];
  }
  return current
    .split(",")
    .map((token) => token.trim())
    .filter(Boolean);
}

function stripRatingTokens(tokens) {
  return tokens.filter((token) => !/^[-!]?rating:/i.test(token));
}

function syncRatingFiltersFromQuery() {
  if (!ratingFilterMeta.length) {
    return;
  }
  const tokens = getSearchTokensList();
  const positives = new Set();
  const negatives = new Set();
  tokens.forEach((token) => {
    const lowered = token.toLowerCase();
    if (lowered.startsWith("-rating:") || lowered.startsWith("!rating:")) {
      const value = lowered.slice(8);
      if (RATING_CLASSES.includes(value)) {
        negatives.add(value);
      }
    } else if (lowered.startsWith("rating:")) {
      const value = lowered.slice(7);
      if (RATING_CLASSES.includes(value)) {
        positives.add(value);
      }
    }
  });
  ratingFilterMeta.forEach(({ input, value }) => {
    if (!RATING_CLASSES.includes(value)) {
      return;
    }
    let checked;
    if (positives.size > 0) {
      checked = positives.has(value) && !negatives.has(value);
    } else {
      checked = !negatives.has(value);
    }
    input.checked = checked;
  });
}

function applyRatingFiltersToQuery(options = {}) {
  const { pushHistory = true } = options;
  if (!ratingFilterMeta.length) {
    return;
  }
  const currentTokens = getSearchTokensList();
  const baseTokens = stripRatingTokens(currentTokens);
  const unchecked = Array.from(
    new Set(
      ratingFilterMeta
        .filter((meta) => !meta.input.checked)
        .map((meta) => meta.value)
        .filter((value) => RATING_CLASSES.includes(value)),
    ),
  );
  const nextTokens = [...baseTokens];
  unchecked.forEach((value) => {
    nextTokens.push(`-rating:${value}`);
  });
  const nextQuery = nextTokens.join(", ");
  commitSearch(nextQuery, { pushHistory });
}

function updateRatingFilterCounts(countsOverride) {
  if (!ratingFilterMeta.length) {
    return;
  }
  const counts = new Map();
  if (countsOverride && typeof countsOverride === "object") {
    Object.entries(countsOverride).forEach(([key, value]) => {
      const normKey = String(key).toLowerCase();
      const numeric = Number(value);
      if (Number.isFinite(numeric)) {
        counts.set(normKey, numeric);
      }
    });
  } else {
    // Use cached tag stats for rating counts
    tagStatsCache.forEach((stats, key) => {
      if (stats.kind === "rating") {
        const norm =
          typeof stats.norm === "string" ? stats.norm.toLowerCase() : "";
        if (norm) {
          counts.set(norm, stats.freq);
        }
      }
    });
  }
  ratingFilterMeta.forEach(({ label, countEl, value }) => {
    const freq = counts.get(value) || 0;
    if (countEl) {
      countEl.textContent = freq.toLocaleString();
    }
    if (label) {
      if (freq > 0) {
        label.classList.add("rating-has-results");
      } else {
        label.classList.remove("rating-has-results");
      }
      label.setAttribute("data-count", String(freq));
    }
  });
}

const STATUS_LABELS = {
  ready: "Done",
  done: "Done",
  pending: "Queued",
  processing: "Processing",
  error: "Failed",
  failed: "Failed",
  skipped: "Done",
  disabled: "Disabled",
  missing: "Not queued",
  unknown: "Unknown",
};

const STATUS_CLASS_MAP = {
  ready: "done",
  done: "done",
  pending: "queued",
  processing: "processing",
  error: "failed",
  failed: "failed",
  skipped: "done",
  disabled: "disabled",
  missing: "missing",
  unknown: "unknown",
};

function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value).replace(/[&<>"']/g, (ch) => {
    switch (ch) {
      case "&":
        return "&amp;";
      case "<":
        return "&lt;";
      case ">":
        return "&gt;";
      case '"':
        return "&quot;";
      case "'":
        return "&#39;";
      default:
        return ch;
    }
  });
}

function normaliseStatus(state) {
  if (!state || state.enabled === false) {
    return "disabled";
  }
  const raw =
    typeof state.status === "string" ? state.status.trim().toLowerCase() : "";
  if (raw) return raw;
  if (state.has_embedding) return "ready";
  if (state.has_tags) return "ready";
  if (state.has_rating) return "ready";
  return "unknown";
}

function buildStatusChip(title, state) {
  if (!state) return "";
  const status = normaliseStatus(state);
  let label = STATUS_LABELS[status] || "Unknown";
  if (
    (status === "pending" || status === "queued") &&
    typeof state.position === "number" &&
    state.position > 0
  ) {
    label = `${label} (#${state.position})`;
  }
  if (status === "ready" && typeof state.rating === "string" && state.rating) {
    const ratingText = state.rating.replace(/_/g, " ");
    label = `${label} (${ratingText})`;
  }
  const statusClass = STATUS_CLASS_MAP[status] || "unknown";
  return `<span class="status-chip status-${statusClass}">${escapeHtml(title)} • ${escapeHtml(label)}</span>`;
}

function buildStatusChips(processing) {
  const clipState =
    processing && typeof processing === "object" && processing.clip
      ? { ...processing.clip }
      : { enabled: false, status: "disabled" };
  const autoState =
    processing && typeof processing === "object" && processing.auto
      ? { ...processing.auto }
      : { enabled: false, status: "disabled" };
  const ratingState =
    processing && typeof processing === "object" && processing.rating
      ? { ...processing.rating }
      : { enabled: false, status: "disabled" };

  if (clipState && clipState.has_embedding) {
    clipState.status = clipState.status || "ready";
  }
  if (autoState && autoState.has_tags) {
    autoState.status = autoState.status || "ready";
    autoState.has_tags = true;
  }
  if (ratingState && ratingState.has_rating) {
    ratingState.status = ratingState.status || "ready";
  }

  const chips = [
    buildStatusChip("CLIP", clipState),
    buildStatusChip("Auto Tags", autoState),
    buildStatusChip("Rating", ratingState),
  ].filter(Boolean);
  return chips.join("");
}

function uniqueStrings(items) {
  const seen = new Set();
  return items
    .map((item) => (typeof item === "string" ? item.trim() : ""))
    .filter((item) => {
      if (!item) return false;
      const key = item.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

function buildTagStrings(tagList, style) {
  const results = [];
  tagList.forEach((tag) => {
    if (!tag || typeof tag !== "object") return;
    if (tag.kind === "negative" || tag.kind === "rating") return;
    const label = typeof tag.tag === "string" ? tag.tag : "";
    if (!label) return;
    if (style === "danbooru") {
      results.push(label.replace(/\s+/g, "_").trim());
    } else {
      const source = tag.source || "embedded";
      if (source === "auto") {
        results.push(label.replace(/_/g, " ").trim());
      } else {
        const raw =
          typeof tag.raw === "string" && tag.raw.trim() ? tag.raw : label;
        results.push(raw.replace(/_/g, " ").trim());
      }
    }
  });
  return uniqueStrings(results);
}

function buildAllNaiString(positivePrompt, embeddedStrings, autoStrings) {
  const basePrompt =
    typeof positivePrompt === "string" ? positivePrompt.trim() : "";
  const embedList = uniqueStrings(embeddedStrings);
  const autoList = uniqueStrings(autoStrings);
  if (!basePrompt && !embedList.length && !autoList.length) {
    return "";
  }
  if (!basePrompt) {
    return uniqueStrings([...embedList, ...autoList]).join(", ");
  }
  const extraAuto = autoList.filter(
    (token) => !basePrompt.toLowerCase().includes(token.toLowerCase()),
  );
  if (!extraAuto.length) {
    return basePrompt;
  }
  return `${basePrompt}${basePrompt.trim().endsWith(",") ? " " : ", "}${extraAuto.join(", ")}`;
}

function buildDanbooruString(embeddedStrings, autoStrings) {
  return uniqueStrings([...embeddedStrings, ...autoStrings]).join(" ");
}

function setCopyButton(button, value, description) {
  if (!button) return;
  const trimmed = typeof value === "string" ? value.trim() : "";
  if (!trimmed) {
    button.disabled = true;
    button.onclick = null;
    if (description) {
      button.title = `${description} (unavailable)`;
    }
    return;
  }
  button.disabled = false;
  if (description) {
    button.title = description;
  }
  button.onclick = () => copyText(trimmed);
}

function updateCopyButtons({ positivePrompt, tags }) {
  const buttons = [
    copyAllNaiBtn,
    copyAllDanbooruBtn,
    copyEmbeddedNaiBtn,
    copyEmbeddedDanbooruBtn,
    copyAutoNaiBtn,
    copyAutoDanbooruBtn,
  ];
  if (!buttons.some(Boolean)) {
    return;
  }
  const tagList = Array.isArray(tags) ? tags : [];
  const nonNegative = tagList.filter(
    (tag) => tag && tag.kind !== "negative" && tag.kind !== "rating",
  );
  const embeddedTags = nonNegative.filter(
    (tag) => (tag.source || "embedded") !== "auto",
  );
  const autoTags = nonNegative.filter(
    (tag) => (tag.source || "embedded") === "auto",
  );

  const naiEmbedded = buildTagStrings(embeddedTags, "nai");
  const naiAuto = buildTagStrings(autoTags, "nai");
  const danEmbedded = buildTagStrings(embeddedTags, "danbooru");
  const danAuto = buildTagStrings(autoTags, "danbooru");

  const allNai = buildAllNaiString(positivePrompt, naiEmbedded, naiAuto);
  const allDan = buildDanbooruString(danEmbedded, danAuto);
  const embeddedNai = naiEmbedded.join(", ");
  const embeddedDan = danEmbedded.join(" ");
  const autoNai = naiAuto.join(", ");
  const autoDan = danAuto.join(" ");

  setCopyButton(copyAllNaiBtn, allNai, "Copy all tags (NovelAI)");
  setCopyButton(copyAllDanbooruBtn, allDan, "Copy all tags (Danbooru)");
  setCopyButton(
    copyEmbeddedNaiBtn,
    embeddedNai,
    "Copy embedded tags (NovelAI)",
  );
  setCopyButton(
    copyEmbeddedDanbooruBtn,
    embeddedDan,
    "Copy embedded tags (Danbooru)",
  );
  setCopyButton(copyAutoNaiBtn, autoNai, "Copy auto tags (NovelAI)");
  setCopyButton(copyAutoDanbooruBtn, autoDan, "Copy auto tags (Danbooru)");
}

function renderCard(item) {
  const width = Number.isFinite(item.width) ? item.width : "–";
  const height = Number.isFinite(item.height) ? item.height : "–";
  const fallback = getFallbackLabel(item);
  const metaParts = [`${width}×${height}`];
  if (item.seed) {
    metaParts.push(`Seed ${item.seed}`);
  } else {
    metaParts.push(fallback);
  }
  if (item.model) {
    metaParts.push(item.model);
  } else if (item.seed) {
    metaParts.push(fallback);
  }
  const meta = metaParts.join(" • ");
  const thumb = item.thumb_url || item.file_url;
  const scoreLine =
    typeof item.score === "number"
      ? `<div class="clip-score">score ${item.score.toFixed(3)}</div>`
      : "";
  const detailHref = buildDetailLink(item.id);
  const similarButton = clipEnabled
    ? `<button class="card-action-similar" data-id="${item.id}" title="Find similar" aria-label="Find similar">≈</button>`
    : "";
  return `
    <article class="card" data-id="${item.id}">
        <a class="card-link" href="${detailHref}" draggable="false">
            <div class="image-wrap">
                <img src="${thumb}" data-full="${item.file_url}" loading="lazy" alt="${fallback}">
            </div>
        </a>
        ${similarButton}
        <div class="info">
            <div class="info-row">
                <div class="meta">${meta}</div>
            </div>
            ${scoreLine}
        </div>
    </article>`;
}

function registerCardElement(cardEl, item) {
  cardEl.tabIndex = 0;
  cardElements.set(item.id, cardEl);
  applyTagsToCard(item.id, Array.isArray(item.tags) ? item.tags : []);
  cardEl.addEventListener("mouseenter", () => {
    highlightFromCard(item.id);
  });
  cardEl.addEventListener("mouseleave", () => {
    clearHighlights();
  });
  cardEl.addEventListener("focus", () => {
    highlightFromCard(item.id);
  });
  const similarBtn = cardEl.querySelector(".card-action-similar");
  if (similarBtn) {
    similarBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      event.preventDefault();
      const imageId = Number(similarBtn.dataset.id);
      if (!Number.isFinite(imageId)) return;
      if (!clipEnabled) return;
      removeClipChips(
        (chip) => chip.kind === "gallery" && chip.imageId === imageId,
        { silent: true },
      );
      clearClipChips();
      if (clipSearchInput) {
        clipSearchInput.value = "";
      }
      updateClipSearchClearVisibility();
      addClipChip({
        kind: "gallery",
        imageId,
        label: `image:${imageId}`,
        status: "ready",
      });
      runClipSearch({
        positiveImages: [imageId],
        tagQuery: searchBox.value.trim(),
        updateInput: "",
        chipsSnapshot: exportClipChips(),
      });
    });
  }
  cardEl.addEventListener("blur", () => {
    clearHighlights();
  });
}

const activeFacetKeys = new Set();
const activeCardIds = new Set();

function clearHighlights() {
  activeFacetKeys.forEach((key) => {
    const facet = facetLookup.get(key);
    if (facet) facet.classList.remove("facet-highlight");
  });
  activeFacetKeys.clear();
  activeCardIds.forEach((id) => {
    const card = cardElements.get(id);
    if (card) card.classList.remove("card-highlight");
  });
  activeCardIds.clear();
}

function highlightFromCard(cardId) {
  clearHighlights();
  const tags = searchState.imageTags.get(cardId) || [];
  const tagKeys = Array.from(
    new Set(
      tags
        .map((tag) => {
          if (!tag || typeof tag !== "object") return null;
          const norm = typeof tag.norm === "string" ? tag.norm : "";
          if (!norm) return null;
          const kind = typeof tag.kind === "string" ? tag.kind : "prompt";
          return `${kind}|${norm}`;
        })
        .filter(Boolean),
    ),
  );
  tagKeys.forEach((key) => {
    const facet = facetLookup.get(key);
    if (facet) {
      facet.classList.add("facet-highlight");
      activeFacetKeys.add(key);
    }
  });
  const card = cardElements.get(cardId);
  if (card) {
    card.classList.add("card-highlight");
    activeCardIds.add(cardId);
  }
}

function highlightFromFacet(key) {
  clearHighlights();
  const facet = facetLookup.get(key);
  if (facet) {
    facet.classList.add("facet-highlight");
    activeFacetKeys.add(key);
  }
  const ids = tagToCards.get(key);
  if (ids) {
    ids.forEach((id) => {
      const card = cardElements.get(id);
      if (card) {
        card.classList.add("card-highlight");
        activeCardIds.add(id);
      }
    });
  }
}

function updateStatus() {
  if (clipModeActive) {
    const total = clipTotal || searchState.total || 0;
    statusEl.textContent = total
      ? `CLIP ${searchState.images.length}/${total}`
      : `CLIP ${searchState.images.length}`;
  } else {
    statusEl.textContent = `${searchState.images.length}/${searchState.total}`;
  }
}

function resetState(query, { clearClip = true } = {}) {
  if (clearClip) {
    clipModeActive = false;
    lastClipPayload = null;
    currentClipToken = null;
    clipOffset = 0;
    clipTotal = 0;
  }
  searchState.query = query;
  searchState.images = [];
  searchState.index = new Map();
  searchState.imageTags = new Map();
  searchState.total = 0;
  searchState.done = false;
  gridEl.innerHTML = "";
  facetLookup.clear();
  tagToCards.clear();
  cardElements.clear();
  suggestionItems = [];
  suggestionIndex = -1;
  clearHighlights();
  updateStatus();
}

async function fetchImages(reset = false) {
  if (searchState.loading) return;
  if (reset) {
    resetState(lastQuery);
  } else if (clipModeActive) {
    return;
  }
  if (searchState.done && !reset) return;
  searchState.loading = true;
  statusEl.textContent = "Loading…";
  let queueMoreForScroll = false;
  try {
    const params = new URLSearchParams({
      q: lastQuery,
      offset: String(searchState.images.length),
      limit: String(PAGE_SIZE),
    });
    const res = await fetch(`/api/images?${params.toString()}`);
    if (!res.ok) throw new Error("Request failed");
    const data = await res.json();
    if (reset) {
      gridEl.innerHTML = "";
    }
    data.images.forEach((item) => {
      const idx = searchState.images.length;
      searchState.images.push(item);
      searchState.index.set(item.id, idx);
      searchState.imageTags.set(item.id, item.tags || []);
      const template = document.createElement("template");
      template.innerHTML = renderCard(item).trim();
      const cardEl = template.content.firstElementChild;
      registerCardElement(cardEl, item);
      gridEl.appendChild(cardEl);
    });
    if (autoObserver) {
      autoObserver.unobserve(sentinel);
      autoObserver.observe(sentinel);
    }
    clearHighlights();
    facetCache = computeFacetsFromCurrentImages();
    renderFacets(facetCache);
    searchState.total = data.total;
    searchState.done = searchState.images.length >= data.total;
    if (!autoObserver) {
      loadMoreBtn.style.display = searchState.done ? "none" : "block";
    }
    if (
      scrollRestorePending &&
      pendingScrollIndex !== null &&
      pendingScrollIndex > 0 &&
      searchState.images.length <= pendingScrollIndex &&
      !searchState.done
    ) {
      queueMoreForScroll = true;
    }
    updateStatus();
    maybeOpenPendingDetail();
  } catch (err) {
    console.error(err);
    statusEl.textContent = "Error";
  } finally {
    searchState.loading = false;
    if (scrollRestorePending) {
      if (queueMoreForScroll) {
        setTimeout(() => fetchImages(), 0);
      } else {
        maybeRestoreScrollPosition();
      }
    } else {
      scheduleScrollSave();
    }
  }
}

async function runClipSearch(
  {
    query = "",
    positiveImages = [],
    negativeImages = [],
    tagQuery = searchBox.value.trim(),
    updateInput,
    positiveVectors = [],
    negativeVectors = [],
    chipsSnapshot = null,
  } = {},
  { append = false, updateHistory = true } = {},
) {
  if (!clipEnabled) {
    statusEl.textContent = "CLIP disabled";
    return;
  }
  if (searchState.loading) {
    return;
  }
  if (clipSearchTimer) {
    clearTimeout(clipSearchTimer);
    clipSearchTimer = null;
  }

  const originalQuery = typeof query === "string" ? query : "";
  const trimmedQuery = originalQuery.trim();
  const posIds = Array.from(
    new Set(
      (Array.isArray(positiveImages) ? positiveImages : [])
        .map(Number)
        .filter(Number.isFinite),
    ),
  );
  const negIds = Array.from(
    new Set(
      (Array.isArray(negativeImages) ? negativeImages : [])
        .map(Number)
        .filter(Number.isFinite),
    ),
  );
  const normalizeVectorInput = (input) => {
    const result = [];
    const enqueue = (value) => {
      if (!value) return;
      if (value instanceof Float32Array) {
        const encoded = float32ToBase64(value);
        if (encoded) result.push(encoded);
        return;
      }
      if (Array.isArray(value)) {
        value.forEach(enqueue);
        return;
      }
      if (typeof value === "string" && value) {
        result.push(value);
      }
    };
    enqueue(input);
    return result;
  };

  const positiveVectorList = normalizeVectorInput(positiveVectors);
  const negativeVectorList = normalizeVectorInput(negativeVectors);

  if (
    !trimmedQuery &&
    posIds.length === 0 &&
    negIds.length === 0 &&
    positiveVectorList.length === 0 &&
    negativeVectorList.length === 0
  ) {
    statusEl.textContent = "Provide CLIP input";
    return;
  }
  if (updateInput !== undefined && clipSearchInput) {
    clipSearchInput.value = updateInput;
  }
  updateClipSearchClearVisibility();

  if (Array.isArray(chipsSnapshot)) {
    rebuildClipChipsFromSnapshot(chipsSnapshot);
  }
  const chipStateSnapshot = exportClipChips();

  clipModeActive = true;
  const historyClipToken =
    ClipState.encodeQuery({
      query: trimmedQuery,
      chips: chipStateSnapshot,
    }) || null;
  ClipState.stashSnapshotForUrl(
    `${window.location.pathname}${window.location.search}`,
    chipStateSnapshot && chipStateSnapshot.length ? chipStateSnapshot : null,
  );
  const tagFilter = (tagQuery ?? lastQuery ?? "").trim();
  if (!append) {
    clipOffset = 0;
    clipTotal = 0;
    lastQuery = tagFilter;
    resetState(lastQuery, { clearClip: false });
    if (!scrollRestorePending) {
      pendingScrollIndex = 0;
      scrollRestorePending = true;
      lastAnchorIndex = 0;
    }
    if (autoObserver) {
      autoObserver.unobserve(sentinel);
    }
    facetCache = computeFacetsFromCurrentImages();
    renderFacets(facetCache);
  } else {
    if (tagFilter) {
      lastQuery = tagFilter;
    }
    statusEl.textContent = "Loading clip results…";
  }

  currentClipToken = historyClipToken ?? currentClipToken ?? null;
  pendingDetailId = null;
  searchState.loading = true;
  if (!append) {
    statusEl.textContent = "CLIP search…";
  }
  if (detailSimilarBtn) detailSimilarBtn.disabled = true;
  if (clipSearchClear) clipSearchClear.disabled = true;

  const payload = {
    limit: PAGE_SIZE,
    offset: append ? clipOffset : 0,
    include_tags: false,
  };
  if (lastQuery) payload.tag_query = lastQuery;
  if (trimmedQuery) payload.query = trimmedQuery;
  if (posIds.length) payload.positive_images = posIds;
  if (negIds.length) payload.negative_images = negIds;
  if (positiveVectorList.length) {
    payload.positive_vectors = positiveVectorList;
  }
  if (negativeVectorList.length) {
    payload.negative_vectors = negativeVectorList;
  }
  delete payload.positiveVectors;
  delete payload.negativeVectors;
  lastClipPayload = {
    query: trimmedQuery,
    positiveImages: posIds.slice(),
    negativeImages: negIds.slice(),
    tagQuery: lastQuery,
    updateInput:
      updateInput !== undefined
        ? updateInput
        : originalQuery,
    positiveVectors: positiveVectorList.slice(),
    negativeVectors: negativeVectorList.slice(),
    chipsSnapshot: chipStateSnapshot,
  };

  let queueMoreForScroll = false;

  try {
    const res = await fetch("/api/search/clip", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`clip search failed: ${res.status}`);
    const data = await res.json();
    const results = Array.isArray(data.results) ? data.results : [];

    if (!append) {
      gridEl.innerHTML = "";
      searchState.images = [];
      searchState.index = new Map();
      searchState.imageTags = new Map();
      requestAnimationFrame(() =>
        window.scrollTo({ top: 0, behavior: "auto" }),
      );
    }

    const newImageIds = [];
    results.forEach((item) => {
      const idx = searchState.images.length;
      searchState.images.push(item);
      searchState.index.set(item.id, idx);
      const template = document.createElement("template");
      template.innerHTML = renderCard(item).trim();
      const cardEl = template.content.firstElementChild;
      registerCardElement(cardEl, item);
      gridEl.appendChild(cardEl);
      if (Number.isFinite(item.id)) {
        newImageIds.push(Number(item.id));
      }
    });

    clipTotal = data.total ?? clipTotal ?? 0;
    clipOffset += results.length;

    const computedFacets = buildClipFacetSummaryFromImageTags(
      searchState.imageTags,
    );
    if (computedFacets.length) {
      facetCache = computedFacets;
    } else {
      facetCache = computeFacetsFromCurrentImages();
    }
    renderFacets(facetCache);
    searchState.total = clipTotal;
    searchState.done = clipOffset >= clipTotal;

    loadMoreBtn.style.display = searchState.done ? "none" : "block";
    if (autoObserver) {
      autoObserver.unobserve(sentinel);
      if (!searchState.done) {
        autoObserver.observe(sentinel);
      }
    }

    if (!append && updateHistory) {
      const anchorIndexForHistory =
        scrollRestorePending && pendingScrollIndex !== null
          ? pendingScrollIndex
          : 0;
      pushHistoryState({
        query: lastQuery,
        detail: null,
        pos: anchorIndexForHistory,
        clip: historyClipToken ?? null,
        clipSnapshot: chipStateSnapshot,
      });
    }

    if (clipModeActive && newImageIds.length) {
      loadTagsForImageIds(newImageIds);
    }

    if (
      scrollRestorePending &&
      pendingScrollIndex !== null &&
      pendingScrollIndex > 0 &&
      searchState.images.length <= pendingScrollIndex &&
      !searchState.done
    ) {
      queueMoreForScroll = true;
    }

    updateStatus();
    maybeOpenPendingDetail();
  } catch (err) {
    console.error(err);
    statusEl.textContent = "CLIP search failed";
  } finally {
    const queuedOptions = pendingClipSearchOptions;
    searchState.loading = false;
    if (clipSearchClear) clipSearchClear.disabled = false;
    if (detailSimilarBtn) detailSimilarBtn.disabled = false;
    updateStatus();
    if (scrollRestorePending) {
      if (queueMoreForScroll && lastClipPayload) {
        setTimeout(() => {
          runClipSearch(lastClipPayload, {
            append: true,
            updateHistory: false,
          });
        }, 0);
      } else {
        maybeRestoreScrollPosition();
      }
    } else if (!append) {
      scheduleScrollSave();
    }
    if (!clipSearchTimer && queuedOptions) {
      pendingClipSearchOptions = null;
      scheduleClipSearch({
        debounce: false,
        append: queuedOptions.append,
        updateHistory: queuedOptions.updateHistory,
        payloadOverrides: queuedOptions.payloadOverrides,
      });
    }
  }
}

function rerunLastClipSearch() {
  if (lastClipPayload) {
    runClipSearch(lastClipPayload, { append: false, updateHistory: false });
  }
}

function maybeOpenPendingDetail() {
  if (pendingDetailId === null || pendingDetailId === undefined) {
    return;
  }
  const targetId = Number(pendingDetailId);
  if (!Number.isFinite(targetId)) {
    pendingDetailId = null;
    return;
  }
  const normalizedId = Math.trunc(targetId);
  if (normalizedId < 0) {
    pendingDetailId = null;
    return;
  }
  if (
    detailOverlay.classList.contains("active") &&
    currentDetailId === normalizedId
  ) {
    pendingDetailId = null;
    return;
  }
  pendingDetailId = null;
  openDetail(normalizedId, { pushState: false }).catch((err) =>
    console.error(err),
  );
}

function getAnchorIndex() {
  if (!searchState.images.length) return 0;
  const threshold = window.scrollY + (headerEl ? headerEl.offsetHeight + 8 : 0);
  let closestIndex = 0;
  let closestTop = -Infinity;
  cardElements.forEach((card, id) => {
    const index = searchState.index.get(Number(id));
    if (index === undefined || index === null) return;
    const top = card.offsetTop;
    if (top <= threshold && top > closestTop) {
      closestTop = top;
      closestIndex = index;
    }
  });
  return closestIndex;
}

function maybeRestoreScrollPosition() {
  if (!scrollRestorePending) return;
  if (pendingScrollIndex === null) {
    scrollRestorePending = false;
    return;
  }
  if (pendingScrollIndex >= searchState.images.length) {
    if (searchState.done && searchState.images.length > 0) {
      pendingScrollIndex = searchState.images.length - 1;
    } else if (searchState.done && searchState.images.length === 0) {
      scrollRestorePending = false;
      pendingScrollIndex = null;
      requestAnimationFrame(() =>
        window.scrollTo({ top: 0, behavior: "auto" }),
      );
      return;
    } else {
      return;
    }
  }
  if (pendingScrollIndex === 0) {
    scrollRestorePending = false;
    pendingScrollIndex = null;
    requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: "auto" }));
    return;
  }
  if (pendingScrollIndex < searchState.images.length) {
    const target = searchState.images[pendingScrollIndex];
    if (!target) {
      return;
    }
    const card = cardElements.get(target.id);
    if (!card) {
      return;
    }
    scrollRestorePending = false;
    pendingScrollIndex = null;
    requestAnimationFrame(() => {
      const offset = headerEl ? headerEl.offsetHeight + 8 : 0;
      const top = card.getBoundingClientRect().top + window.scrollY - offset;
      window.scrollTo({ top: Math.max(0, top), behavior: "auto" });
    });
  }
}

function scheduleScrollSave() {
  if (scrollRestorePending) return;
  if (scrollSaveScheduled) return;
  scrollSaveScheduled = true;
  requestAnimationFrame(() => {
    scrollSaveScheduled = false;
    if (!searchState.images.length) return;
    const anchorIndex = getAnchorIndex();
    const activeDetail = detailOverlay.classList.contains("active")
      ? currentDetailId
      : null;
    if (
      anchorIndex === (currentHistoryState.pos ?? 0) &&
      activeDetail === currentHistoryState.detail &&
      lastQuery === (currentHistoryState.query ?? "")
    ) {
      return;
    }
    lastAnchorIndex = anchorIndex;
    const clipTokenForHistory = getActiveClipToken();
    const clipSnapshotForHistory = clipModeActive ? exportClipChips() : null;
    pushHistoryState(
      {
        query: lastQuery,
        detail: activeDetail,
        pos: anchorIndex,
        clip: clipTokenForHistory,
        clipSnapshot: clipSnapshotForHistory,
      },
      { replace: true },
    );
  });
}

function renderFacets(facets) {
  facetListEl.innerHTML = "";
  facetLookup.clear();
  clearHighlights();
  const source = Array.isArray(facets) ? facets : [];
  const filtered = source.filter((facet) => {
    if (facet.kind === "rating") return false; // Hide rating tags from sidebar
    return hideUCTags ? facet.kind !== "negative" : true;
  });
  if (filtered.length === 0) {
    const empty = document.createElement("li");
    empty.textContent = "No tags";
    empty.style.opacity = "0.5";
    facetListEl.appendChild(empty);
    return;
  }
  filtered.slice(0, 80).forEach((facet) => {
    const li = document.createElement("li");
    li.dataset.kind = facet.kind;
    li.innerHTML = `<span>${facet.tag}</span><span class="count">${facet.freq}</span>`;
    li.addEventListener("click", () => applyFacet(facet));
    const key = `${facet.kind}|${facet.norm}`;
    facetLookup.set(key, li);
    li.dataset.key = key;
    li.tabIndex = 0;
    li.addEventListener("mouseenter", () => highlightFromFacet(key));
    li.addEventListener("mouseleave", () => clearHighlights());
    li.addEventListener("focus", () => highlightFromFacet(key));
    li.addEventListener("blur", () => clearHighlights());
    facetListEl.appendChild(li);
  });
  updateRatingFilterCounts();
}

function applyFacet(facet) {
  let token;
  if (facet.kind === "negative") {
    token = `uc:${facet.tag}`;
  } else if (facet.kind === "character") {
    token = `char:${facet.tag}`;
  } else {
    token = facet.tag;
  }
  applyToken(token, { skipSuggestions: true });
  clearHighlights();
}

function commitSearch(rawValue, { pushHistory = true } = {}) {
  const tokens = (rawValue || "")
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
  const normalized = tokens.join(", ");
  const nextQuery = normalized.trim();
  pendingDetailId = null;
  if (detailOverlay.classList.contains("active")) {
    closeDetail({ skipHistory: true });
  }
  if (searchBox.value !== normalized) {
    searchBox.value = normalized;
  }
  syncClearButton(searchBox, searchClearBtn);
  pendingScrollIndex = 0;
  scrollRestorePending = true;
  lastAnchorIndex = 0;
  requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: "auto" }));
  const sameQuery = nextQuery === lastQuery;
  lastQuery = nextQuery;
  syncRatingFiltersFromQuery();
  if (clipModeActive && lastClipPayload) {
    const payload = {
      ...lastClipPayload,
      tagQuery: nextQuery,
    };
    lastClipPayload = payload;
    const clipToken = getActiveClipToken();
    const clipSnapshotForHistory = exportClipChips();
    if (pushHistory) {
      pushHistoryState(
        {
          query: nextQuery,
          detail: null,
          pos: 0,
          clip: clipToken,
          clipSnapshot: clipSnapshotForHistory,
        },
        { replace: sameQuery },
      );
    } else {
      pushHistoryState(
        {
          query: nextQuery,
          detail: null,
          pos: 0,
          clip: clipToken,
          clipSnapshot: clipSnapshotForHistory,
        },
        { replace: true },
      );
    }
    runClipSearch(payload, { append: false, updateHistory: false });
    return;
  }
  if (sameQuery) {
    if (pushHistory) {
      pushHistoryState(
        { query: nextQuery, detail: null, pos: 0, clip: null, clipSnapshot: null },
        { replace: true },
      );
    }
    return;
  }
  if (pushHistory) {
    pushHistoryState({
      query: nextQuery,
      detail: null,
      pos: 0,
      clip: null,
      clipSnapshot: null,
    });
  } else {
    pushHistoryState(
      { query: nextQuery, detail: null, pos: 0, clip: null, clipSnapshot: null },
      { replace: true },
    );
  }
  fetchImages(true);
}

function applyToken(token, options = {}) {
  const { skipSuggestions = false } = options;
  const current = searchBox.value.trim();
  const tokens = current
    ? current
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean)
    : [];
  if (!tokens.includes(token)) {
    tokens.push(token);
    suggestionsEl.style.display = "none";
    suggestionItems = [];
    suggestionIndex = -1;
    commitSearch(tokens.join(", "));
    if (!skipSuggestions) {
      searchBox.focus();
    }
  }
}

searchBox.addEventListener("input", () => {
  syncClearButton(searchBox, searchClearBtn);
  maybeSuggest();
});

searchBox.addEventListener("focus", () => {
  syncClearButton(searchBox, searchClearBtn);
  maybeSuggest();
});

searchBox.addEventListener("blur", () => {
  setTimeout(() => {
    suggestionsEl.style.display = "none";
    suggestionItems = [];
    suggestionIndex = -1;
  }, 120);
});

if (searchClearBtn) {
  searchClearBtn.addEventListener("click", () => {
    suggestionsEl.style.display = "none";
    suggestionItems = [];
    suggestionIndex = -1;
    commitSearch("");
    searchBox.focus();
  });
}

if (ratingFilterMeta.length) {
  ratingFilterMeta.forEach(({ input, label, countEl, value }) => {
    input.addEventListener("change", () => {
      applyRatingFiltersToQuery();
    });

    // Add highlighting to entire rating filter label
    if (label) {
      const ratingKey = `rating|${value}`;
      label.addEventListener("mouseenter", () => {
        highlightFromFacet(ratingKey);
        label.classList.add("rating-filter-highlight");
      });
      label.addEventListener("mouseleave", () => {
        clearHighlights();
        label.classList.remove("rating-filter-highlight");
      });
      label.style.cursor = "pointer";
    }
  });
}

searchBox.addEventListener("keydown", async (event) => {
  if (event.key === "ArrowDown") {
    event.preventDefault();
    if (suggestionsEl.style.display !== "block") {
      await maybeSuggest(true);
    }
    if (!suggestionItems.length) {
      suggestionItems = Array.from(suggestionsEl.querySelectorAll("li"));
      if (suggestionItems.length) {
        setActiveSuggestion(0);
        return;
      }
    }
    if (suggestionItems.length) {
      const next =
        suggestionIndex + 1 < suggestionItems.length ? suggestionIndex + 1 : 0;
      setActiveSuggestion(next);
    }
    return;
  }
  if (event.key === "ArrowUp") {
    event.preventDefault();
    if (suggestionsEl.style.display !== "block") {
      await maybeSuggest(true);
    }
    if (!suggestionItems.length) {
      suggestionItems = Array.from(suggestionsEl.querySelectorAll("li"));
      if (suggestionItems.length) {
        setActiveSuggestion(suggestionItems.length - 1);
        return;
      }
    }
    if (suggestionItems.length) {
      const prev =
        suggestionIndex > 0 ? suggestionIndex - 1 : suggestionItems.length - 1;
      setActiveSuggestion(prev);
    }
    return;
  }
  if (event.key === "Enter") {
    if (suggestionIndex >= 0 && suggestionItems[suggestionIndex]) {
      event.preventDefault();
      suggestionItems[suggestionIndex].click();
      return;
    }
    event.preventDefault();
    suggestionsEl.style.display = "none";
    suggestionItems = [];
    suggestionIndex = -1;
    commitSearch(searchBox.value);
  }
  if (event.key === "Escape") {
    suggestionsEl.style.display = "none";
    setActiveSuggestion(-1);
    suggestionItems = [];
    suggestionIndex = -1;
  }
});

const legacyClearBtn = document.getElementById("clear");
if (legacyClearBtn) {
  legacyClearBtn.addEventListener("click", () => {
    suggestionsEl.style.display = "none";
    suggestionItems = [];
    suggestionIndex = -1;
    commitSearch("");
  });
}

loadMoreBtn.addEventListener("click", () => {
  if (clipModeActive) {
    if (!searchState.loading && lastClipPayload) {
      runClipSearch(lastClipPayload, { append: true, updateHistory: false });
    }
  } else {
    fetchImages();
  }
});

if (clipSearchInput) {
  clipSearchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      if (!clipEnabled) return;
      const rawQuery = clipSearchInput.value;
      const hasChips = clipChipState.items.length > 0;
      if (!rawQuery.trim() && !hasChips) {
        if (lastClipPayload) {
          runClipSearch(lastClipPayload, { append: false, updateHistory: false });
        }
        return;
      }
      scheduleClipSearch({ debounce: false, append: false, updateHistory: true });
    }
  });
  clipSearchInput.addEventListener("input", () => {
    if (!clipEnabled) return;
    updateClipSearchClearVisibility();
    const rawQuery = clipSearchInput.value;
    if (!rawQuery.trim()) {
      updateClipSearchClearVisibility();
      if (clipChipState.items.length === 0) {
        if (clipModeActive && !searchState.loading) {
          exitClipMode({ fetch: true });
        }
      } else {
        scheduleClipSearch({ debounce: false, append: false, updateHistory: true });
      }
      return;
    }
    scheduleClipSearch({ debounce: true, append: false, updateHistory: true });
  });
  clipSearchInput.addEventListener("paste", async (event) => {
    if (!clipEnabled) return;
    const clipboard = event.clipboardData;
    if (!clipboard) return;
    const files = Array.from(clipboard.files || []).filter(
      (file) =>
        file && typeof file.type === "string" && file.type.toLowerCase().startsWith("image/"),
    );
    if (!files.length) return;
    event.preventDefault();
    for (const file of files) {
      // eslint-disable-next-line no-await-in-loop
      await startClipUploadSearch(file);
    }
  });
  updateClipSearchClearVisibility();
}
if (clipSearchClear) {
  clipSearchClear.addEventListener("click", () => {
    if (clipSearchInput) {
      clipSearchInput.value = "";
    }
    clearClipChips();
    if (clipSearchTimer) {
      clearTimeout(clipSearchTimer);
      clipSearchTimer = null;
    }
    pendingClipSearchOptions = null;
    updateClipSearchClearVisibility();
    if (clipModeActive && !searchState.loading) {
      exitClipMode({ fetch: true });
    } else {
      exitClipMode({ fetch: false });
    }
    clipSearchInput?.focus();
  });
}

if (hideUCToggleBtn) {
  hideUCToggleBtn.addEventListener("click", () => {
    hideUCTags = !hideUCTags;
    hideUCToggleBtn.setAttribute("aria-pressed", hideUCTags ? "true" : "false");
    hideUCToggleBtn.textContent = hideUCTags ? "UC Hidden" : "UC Visible";
    renderFacets(facetCache);
    if (detailNegSection) {
      if (hideUCTags) {
        detailNegSection.style.display = "none";
      } else if (detailNegTags.children.length) {
        detailNegSection.style.display = "";
      }
    }
  });
  hideUCToggleBtn.textContent = hideUCTags ? "UC Hidden" : "UC Visible";
  hideUCToggleBtn.setAttribute("aria-pressed", hideUCTags ? "true" : "false");
}

facetListEl.addEventListener("mouseleave", () => clearHighlights());
gridEl.addEventListener("mouseleave", () => clearHighlights());

copyPositiveBtn.addEventListener("click", () => {
  if (!copyPositiveBtn.disabled) {
    copyText(currentPrompts.positive);
  }
});

copyNegativeBtn.addEventListener("click", () => {
  if (!copyNegativeBtn.disabled) {
    copyText(currentPrompts.negative);
  }
});

function isFileDrag(event) {
  const dt = event.dataTransfer;
  if (!dt) return false;
  return Array.from(dt.types || []).includes("Files");
}

window.addEventListener("dragenter", (event) => {
  if (!isFileDrag(event)) return;
  event.preventDefault();
  dragCounter += 1;
  if (dropOverlay) dropOverlay.classList.add("active");
});

window.addEventListener("dragover", (event) => {
  if (!isFileDrag(event)) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = "copy";
  if (dropOverlay && !dropOverlay.classList.contains("active")) {
    dropOverlay.classList.add("active");
  }
});

window.addEventListener("dragleave", (event) => {
  if (!isFileDrag(event)) return;
  event.preventDefault();
  dragCounter = Math.max(0, dragCounter - 1);
  if (dragCounter === 0 && dropOverlay) {
    dropOverlay.classList.remove("active");
  }
});

window.addEventListener("drop", async (event) => {
  if (!isFileDrag(event)) return;
  event.preventDefault();
  dragCounter = 0;
  if (dropOverlay) dropOverlay.classList.remove("active");
  const files = event.dataTransfer
    ? Array.from(event.dataTransfer.files || [])
    : [];
  if (!files.length) return;
  for (const file of files) {
    if (!file || !file.type || !file.type.toLowerCase().startsWith("image/")) {
      continue;
    }
    // eslint-disable-next-line no-await-in-loop
    await startClipUploadSearch(file);
  }
});

gridEl.addEventListener("click", (event) => {
  const link = event.target.closest(".card-link");
  if (link) {
    if (
      event.button === 0 &&
      !event.metaKey &&
      !event.ctrlKey &&
      !event.shiftKey &&
      !event.altKey
    ) {
      event.preventDefault();
    } else {
      return;
    }
  }
  const card = event.target.closest(".card");
  if (!card) return;
  const id = Number(card.dataset.id);
  if (!Number.isFinite(id)) return;
  openDetail(id);
});

if (detailSimilarBtn) {
  detailSimilarBtn.addEventListener("click", () => {
    const imageId = Number(currentDetailId);
    if (!Number.isFinite(imageId)) return;
    if (!clipEnabled) return;
    const tagFilter = searchBox.value.trim();
    closeDetail({ skipHistory: true });
    clearClipChips();
    if (clipSearchInput) {
      clipSearchInput.value = "";
    }
    updateClipSearchClearVisibility();
    addClipChip({
      kind: "gallery",
      imageId,
      label: `image:${imageId}`,
      status: "ready",
    });
    runClipSearch({
      positiveImages: [imageId],
      tagQuery: tagFilter,
      updateInput: "",
      chipsSnapshot: exportClipChips(),
    });
  });
}

detailCloseBtn.addEventListener("click", () => closeDetail());

detailOverlay.addEventListener("click", (event) => {
  if (event.target === detailOverlay) {
    closeDetail();
  }
});

detailPrevBtn.addEventListener("click", () => showSibling(-1));
detailNextBtn.addEventListener("click", () => showSibling(1));
detailImage.addEventListener("click", () => {
  if (!detailImage.src) return;
  window.open(detailImage.src, "_blank", "noopener");
});

window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (detailOverlay.classList.contains("active")) {
      closeDetail();
      event.preventDefault();
      return;
    }
    if (desktopMediaQuery.matches) {
      if (statusCardVisible) {
        statusCardVisible = false;
        applySidebarState();
        event.preventDefault();
        return;
      }
    } else if (sidebarVisible) {
      sidebarVisible = false;
      applySidebarState();
      event.preventDefault();
      return;
    }
  }
  if (!detailOverlay.classList.contains("active")) return;
  if (event.key === "ArrowLeft") {
    showSibling(-1);
  } else if (event.key === "ArrowRight") {
    showSibling(1);
  }
});

window.addEventListener("scroll", () => {
  scheduleScrollSave();
});

async function maybeSuggest(selectFirst = false) {
  const value = searchBox.value;
  const atComma = value.lastIndexOf(",");
  const prefix = atComma >= 0 ? value.slice(atComma + 1).trim() : value.trim();
  const base = atComma >= 0 ? value.slice(0, atComma + 1).trim() : "";
  const leadingNegMatch = prefix.match(/^[!-]+/);
  const leadingNegation = leadingNegMatch ? leadingNegMatch[0] : "";
  let remainder = prefix.slice(leadingNegation.length).trimStart();
  let kind = "";
  let kindPrefix = "";
  const lowered = remainder.toLowerCase();
  if (lowered.startsWith("uc:")) {
    kind = "negative";
    kindPrefix = "uc:";
    remainder = remainder.slice(3).trimStart();
  } else if (lowered.startsWith("char:")) {
    kind = "character";
    kindPrefix = "char:";
    remainder = remainder.slice(5).trimStart();
  } else if (lowered.startsWith("character:")) {
    kind = "character";
    kindPrefix = "char:";
    remainder = remainder.slice(10).trimStart();
  } else if (lowered.startsWith("prompt:")) {
    kind = "prompt";
    kindPrefix = "prompt:";
    remainder = remainder.slice(7).trimStart();
  }
  const innerNegMatch = remainder.match(/^[!-]+/);
  const innerNegation = innerNegMatch ? innerNegMatch[0] : "";
  remainder = remainder.slice(innerNegation.length).trimStart();
  const allowEmptyLookup = Boolean(kindPrefix);
  const lookupLength =
    leadingNegation.length + innerNegation.length + remainder.length;
  if (!allowEmptyLookup && (lookupLength < 2 || remainder.length === 0)) {
    suggestionsEl.style.display = "none";
    suggestionItems = [];
    suggestionIndex = -1;
    return;
  }
  let lookup = remainder;
  const res = await fetch(
    `/api/tags?q=${encodeURIComponent(lookup)}&kind=${kind}`,
  );
  if (!res.ok) {
    suggestionsEl.style.display = "none";
    suggestionItems = [];
    suggestionIndex = -1;
    return;
  }
  const data = await res.json();
  if (!Array.isArray(data.tags) || data.tags.length === 0) {
    suggestionsEl.style.display = "none";
    suggestionItems = [];
    suggestionIndex = -1;
    return;
  }
  suggestionsEl.innerHTML = "";
  suggestionItems = [];
  suggestionIndex = -1;
  data.tags.forEach((tag, idx) => {
    const li = document.createElement("li");
    li.innerHTML = `<span>${tag.tag}</span><span class="kind">${tag.kind} • ${tag.freq}</span>`;
    li.addEventListener("click", () => {
      let prefixPart = kindPrefix;
      if (!prefixPart) {
        if (tag.kind === "negative") {
          prefixPart = "uc:";
        } else if (tag.kind === "character") {
          prefixPart = "char:";
        } else {
          prefixPart = "";
        }
      }
      const decorated = `${leadingNegation}${prefixPart}${innerNegation}${tag.tag}`;
      const newValue = base ? `${base} ${decorated}`.trim() : decorated;
      suggestionsEl.style.display = "none";
      suggestionItems = [];
      suggestionIndex = -1;
      commitSearch(newValue);
      searchBox.focus();
    });
    li.addEventListener("mouseenter", () => setActiveSuggestion(idx));
    li.addEventListener("mouseleave", () => setActiveSuggestion(-1));
    suggestionsEl.appendChild(li);
    suggestionItems.push(li);
  });
  const rect = searchBox.getBoundingClientRect();
  suggestionsEl.style.left = `${rect.left + window.scrollX}px`;
  suggestionsEl.style.top = `${rect.bottom + window.scrollY}px`;
  suggestionsEl.style.display = "block";
  setActiveSuggestion(selectFirst && suggestionItems.length ? 0 : -1);
}

async function openDetail(id, options = {}) {
  const detailId = Number(id);
  if (!Number.isFinite(detailId)) {
    return;
  }
  const { pushState = true, replaceState = false } = options;
  const clipTokenForHistory = getActiveClipToken();
  if (
    detailOverlay.classList.contains("active") &&
    currentDetailId === detailId
  ) {
    if (pushState) {
      pushHistoryState(
        {
          query: lastQuery,
          detail: detailId,
          clip: clipTokenForHistory,
          clipSnapshot: clipModeActive ? exportClipChips() : null,
        },
        { replace: true },
      );
    } else if (replaceState) {
      pushHistoryState(
        {
          query: lastQuery,
          detail: detailId,
          clip: clipTokenForHistory,
          clipSnapshot: clipModeActive ? exportClipChips() : null,
        },
        { replace: true },
      );
    }
    return;
  }
  pendingDetailId = null;
  try {
    const res = await fetch(`/api/images/${detailId}`);
    if (!res.ok) throw new Error("Failed to load image");
    const data = await res.json();
    const item = data.image;
    currentPrompts = data.prompts || { positive: "", negative: "" };
    copyPositiveBtn.disabled = !currentPrompts.positive;
    copyNegativeBtn.disabled = !currentPrompts.negative;
    const hasPositive = !!(
      currentPrompts.positive && currentPrompts.positive.trim()
    );
    const hasNegative = !!(
      currentPrompts.negative && currentPrompts.negative.trim()
    );
    detailPromptsSection.style.display =
      hasPositive || hasNegative ? "block" : "none";
    positiveBlock.style.display = hasPositive ? "block" : "none";
    negativeBlock.style.display = hasNegative ? "block" : "none";
    copyPositiveBtn.disabled = !hasPositive;
    copyNegativeBtn.disabled = !hasNegative;
    positivePreview.textContent = hasPositive ? currentPrompts.positive : "—";
    negativePreview.textContent = hasNegative ? currentPrompts.negative : "—";
    const fallbackLabel = getFallbackLabel(item);
    const displayModel = item.model || fallbackLabel;
    const displaySeed = item.seed || fallbackLabel;
    const titleParts = [];
    if (item.model) titleParts.push(item.model);
    if (item.seed) titleParts.push(`Seed ${item.seed}`);
    if (!titleParts.length) {
      titleParts.push(fallbackLabel);
    }
    detailTitle.textContent = titleParts.join(" • ");
    detailImage.src = item.file_url;
    detailImage.alt = fallbackLabel;
    detailImage.parentElement.style.removeProperty("--image-aspect");
    detailImage.parentElement.style.removeProperty("aspect-ratio");
    detailImage.style.removeProperty("aspect-ratio");
    let infoFields = [];

    // Enhanced AI metadata fields
    if (item.generator)
      infoFields.push({ label: "Generator", value: item.generator });
    if (item.model) infoFields.push({ label: "Model", value: item.model });
    if (item.sampler)
      infoFields.push({ label: "Sampler", value: item.sampler });
    if (item.scheduler)
      infoFields.push({ label: "Scheduler", value: item.scheduler });

    // Generation parameters
    if (item.steps) infoFields.push({ label: "Steps", value: item.steps });
    if (item.cfg_scale)
      infoFields.push({ label: "CFG Scale", value: item.cfg_scale });
    if (item.seed) infoFields.push({ label: "Seed", value: item.seed });

    // Basic image info
    infoFields.push(
      {
        label: "Dimensions",
        value: `${Number.isFinite(item.width) ? item.width : "–"}×${Number.isFinite(item.height) ? item.height : "–"}`,
      },
      { label: "File Size", value: formatFileSize(item.size) },
    );
    const statusChipsHtml = buildStatusChips(data.processing || null);
    detailInfo.innerHTML = `
            <div class="info-card">
                <div class="info-fields">
                    ${infoFields
                      .map(
                        (field) =>
                          `<div class="info-chip"><span>${escapeHtml(field.label)}</span><strong>${escapeHtml(field.value)}</strong></div>`,
                      )
                      .join("")}
                </div>
                ${statusChipsHtml ? `<div class="status-chips">${statusChipsHtml}</div>` : ""}
              </div>
            `;
    const tagList = Array.isArray(data.tags) ? data.tags : [];
    updateDetailRating(data.rating || null);
    const characterDetails = Array.isArray(data.characters)
      ? data.characters
      : [];
    renderDetailTags(tagList, characterDetails);
    renderCharacterDetails(characterDetails);
    updateCopyButtons({
      positivePrompt: currentPrompts.positive,
      tags: tagList,
    });
    currentDetailId = detailId;
    if (detailSimilarBtn) {
      detailSimilarBtn.disabled = !clipEnabled;
      detailSimilarBtn.dataset.id = String(detailId);
    }
    currentDetailIndex = searchState.index.has(detailId)
      ? searchState.index.get(detailId)
      : -1;
    updateDetailControls();
    detailOverlay.classList.add("active");
    detailOverlay.setAttribute("aria-hidden", "false");
    const anchorIndexForHistory =
      scrollRestorePending && pendingScrollIndex !== null
        ? pendingScrollIndex
        : getAnchorIndex();
    if (pushState) {
      pushHistoryState({
        query: lastQuery,
        detail: detailId,
        pos: anchorIndexForHistory,
        clip: clipTokenForHistory,
        clipSnapshot: clipModeActive ? exportClipChips() : null,
      });
    } else if (replaceState) {
      pushHistoryState(
        {
          query: lastQuery,
          detail: detailId,
          pos: anchorIndexForHistory,
          clip: clipTokenForHistory,
          clipSnapshot: clipModeActive ? exportClipChips() : null,
        },
        { replace: true },
      );
    }
  } catch (err) {
    console.error(err);
  }
}

function updateDetailRating(ratingData) {
  if (!detailRatingSection || !detailRatingLabel) {
    return;
  }
  const scoreMapRaw =
    ratingData && typeof ratingData === "object" && ratingData.scores
      ? ratingData.scores
      : null;
  const scoreMap = {};
  if (scoreMapRaw && typeof scoreMapRaw === "object") {
    Object.entries(scoreMapRaw).forEach(([key, value]) => {
      const normKey = String(key).toLowerCase();
      const numeric = Number(value);
      if (Number.isFinite(numeric)) {
        scoreMap[normKey] = Math.max(0, Math.min(1, numeric));
      }
    });
  }

  let value =
    ratingData && typeof ratingData.value === "string" ? ratingData.value : "";
  let confidence =
    ratingData && typeof ratingData.confidence === "number"
      ? ratingData.confidence
      : null;

  if ((!value || !value.trim()) && Object.keys(scoreMap).length) {
    const best = RATING_CLASSES.map((key) => ({
      key,
      score: scoreMap[key] ?? -1,
    })).reduce(
      (prev, current) => (current.score > prev.score ? current : prev),
      {
        key: "",
        score: -1,
      },
    );
    if (best.key) {
      value = best.key;
      confidence = best.score;
    }
  }

  if (!value) {
    detailRatingSection.style.display = "none";
    detailRatingLabel.textContent = "";
    detailRatingLabel.className = "rating-label";
    detailRatingLabel.removeAttribute("title");
    if (ratingBarsContainer) {
      ratingBarsContainer.style.display = "none";
      ratingBarsContainer.innerHTML = "";
    }
    return;
  }

  const normalized = value.toLowerCase();
  const displayName = RATING_DISPLAY_NAMES[normalized] || value;
  detailRatingSection.style.display = "flex";
  detailRatingLabel.textContent = displayName;
  detailRatingLabel.className = "rating-label";
  detailRatingLabel.classList.add(`rating-${normalized}`);

  if (typeof confidence === "number" && Number.isFinite(confidence)) {
    const pct = Math.round(confidence * 1000) / 10;
    detailRatingLabel.title = `Confidence ${pct.toFixed(1)}%`;
    detailRatingLabel.textContent = `${displayName} (${pct.toFixed(1)}%)`;
  } else {
    detailRatingLabel.removeAttribute("title");
  }

  if (ratingBarsContainer) {
    const rows = RATING_CLASSES.map((key) => {
      const score = scoreMap[key] ?? 0;
      return { key, score };
    });
    if (rows.some((row) => row.score > 0)) {
      ratingBarsContainer.style.display = "flex";
      ratingBarsContainer.innerHTML = "";
      rows.forEach(({ key, score }) => {
        const rowEl = document.createElement("div");
        rowEl.className = "rating-bar";

        const labelEl = document.createElement("span");
        labelEl.className = "rating-bar-label";
        labelEl.textContent = RATING_DISPLAY_NAMES[key] || key;

        const trackEl = document.createElement("div");
        trackEl.className = "rating-bar-track";

        const fillEl = document.createElement("div");
        fillEl.className = "rating-bar-fill";
        const width = Math.max(0, Math.min(100, Math.round(score * 100)));
        fillEl.style.width = `${width}%`;

        const scoreEl = document.createElement("span");
        scoreEl.className = "rating-bar-score";
        scoreEl.textContent = `${width}%`;

        trackEl.appendChild(fillEl);
        rowEl.appendChild(labelEl);
        rowEl.appendChild(trackEl);
        rowEl.appendChild(scoreEl);
        ratingBarsContainer.appendChild(rowEl);
      });
    } else {
      ratingBarsContainer.style.display = "none";
      ratingBarsContainer.innerHTML = "";
    }
  }
}

function renderDetailTags(tags, characterDetails) {
  detailTags.innerHTML = "";
  detailNegTags.innerHTML = "";
  let hasNeg = false;
  const hasCharacterDetails =
    Array.isArray(characterDetails) && characterDetails.length > 0;
  tags.forEach((tag) => {
    const span = document.createElement("span");
    span.className = "tag-pill";
    span.dataset.kind = tag.kind;
    span.dataset.emphasis = tag.emphasis;
    const source =
      typeof tag.source === "string" && tag.source ? tag.source : "embedded";
    span.dataset.source = source;
    if (Number.isFinite(tag.weight)) {
      span.dataset.weight = Number(tag.weight).toFixed(1);
    } else {
      span.dataset.weight = "";
    }
    const label = tag.count ? `${tag.tag} (${tag.count})` : tag.tag;
    span.textContent = label;
    if (source === "auto") {
      span.title = "Auto-generated tag";
    } else {
      span.title = "Embedded tag";
    }
    span.addEventListener("click", () => {
      let token;
      if (tag.kind === "negative") {
        token = `uc:${tag.tag}`;
      } else if (tag.kind === "character") {
        token = `char:${tag.tag}`;
      } else {
        token = tag.tag;
      }
      applyToken(token, { skipSuggestions: true });
    });
    if (tag.kind === "negative") {
      hasNeg = true;
      detailNegTags.appendChild(span);
    } else if (tag.kind === "character" && hasCharacterDetails) {
      // Character metadata will render separately; avoid duplicates.
      return;
    } else if (tag.kind === "rating") {
      return;
    } else {
      detailTags.appendChild(span);
    }
  });
  detailNegSection.style.display = hasNeg && !hideUCTags ? "" : "none";
}

function renderCharacterDetails(characters) {
  clearHotspots();
  detailCharacters.innerHTML = "";
  if (!Array.isArray(characters) || characters.length === 0) {
    detailCharSection.style.display = "none";
    return;
  }
  detailCharSection.style.display = "";
  characters.forEach((char, idx) => {
    const block = document.createElement("div");
    block.className = "char-block";
    block.tabIndex = 0;
    const centers = (char.centers || []).map((center) => ({
      x:
        typeof center?.x === "number"
          ? center.x
          : Array.isArray(center)
            ? center[0]
            : 0.5,
      y:
        typeof center?.y === "number"
          ? center.y
          : Array.isArray(center)
            ? center[1]
            : 0.5,
    }));
    const locLabel = centers.length
      ? centers
          .map(
            (c) =>
              `${Math.round((c.x ?? 0.5) * 100)}% × ${Math.round((c.y ?? 0.5) * 100)}%`,
          )
          .join(" · ")
      : "Location unknown";
    const metaRow = document.createElement("div");
    metaRow.className = "char-meta";
    const locSpan = document.createElement("span");
    locSpan.className = "char-loc";
    locSpan.textContent = locLabel;
    const copyBtn = document.createElement("button");
    copyBtn.className = "copy-btn";
    copyBtn.innerHTML = `<span class="sr-only">Copy character ${idx + 1} prompt</span>📋`;
    copyBtn.disabled = !char.caption;
    copyBtn.setAttribute("title", "Copy character prompt");
    copyBtn.setAttribute("aria-label", `Copy character ${idx + 1} prompt`);
    copyBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      copyText(char.caption || "");
    });
    metaRow.appendChild(locSpan);
    metaRow.appendChild(copyBtn);
    block.appendChild(metaRow);

    const wrap = document.createElement("div");
    wrap.className = "tag-pills";
    (char.tags || []).forEach((tag) => {
      const span = document.createElement("span");
      span.className = "tag-pill";
      span.dataset.kind = tag.kind || "character";
      span.dataset.emphasis = tag.emphasis || "normal";
      const source =
        typeof tag.source === "string" && tag.source ? tag.source : "embedded";
      span.dataset.source = source;
      const weight = typeof tag.weight === "number" ? tag.weight : 1;
      span.dataset.weight = weight.toFixed(1);
      const label = tag.count ? `${tag.tag} (${tag.count})` : tag.tag;
      span.textContent = label;
      if (source === "auto") {
        span.title = "Auto-generated tag";
      } else {
        span.title = "Embedded tag";
      }
      span.addEventListener("click", () => {
        const token =
          tag.kind === "negative" ? `uc:${tag.tag}` : `char:${tag.tag}`;
        applyToken(token, { skipSuggestions: true });
      });
      wrap.appendChild(span);
    });
    block.appendChild(wrap);

    block.addEventListener("mouseenter", () => showHotspots(centers));
    block.addEventListener("mouseleave", () => clearHotspots());
    block.addEventListener("focus", () => showHotspots(centers));
    block.addEventListener("blur", () => clearHotspots());

    detailCharacters.appendChild(block);
  });
}

function clearHotspots() {
  currentHotspotCenters = null;
  currentHotspotDots = [];
  detailHotspots.innerHTML = "";
}

function showHotspots(centers) {
  if (!Array.isArray(centers) || centers.length === 0) {
    clearHotspots();
    return;
  }
  currentHotspotCenters = centers;
  detailHotspots.innerHTML = "";
  currentHotspotDots = centers.map(() => {
    const dot = document.createElement("div");
    dot.className = "hotspot-dot visible";
    detailHotspots.appendChild(dot);
    return dot;
  });
  positionHotspots();
  requestAnimationFrame(() => positionHotspots());
}

function positionHotspots() {
  if (!currentHotspotCenters || currentHotspotCenters.length === 0) {
    return;
  }
  const overlayRect = detailHotspots.getBoundingClientRect();
  const imageRect = detailImage.getBoundingClientRect();
  if (
    !overlayRect.width ||
    !overlayRect.height ||
    !imageRect.width ||
    !imageRect.height
  ) {
    return;
  }
  const offsetX = imageRect.left - overlayRect.left;
  const offsetY = imageRect.top - overlayRect.top;
  const displayedWidth = imageRect.width;
  const displayedHeight = imageRect.height;
  currentHotspotCenters.forEach((center, idx) => {
    const dot = currentHotspotDots[idx];
    if (!dot) return;
    const xNorm = Math.min(Math.max(center?.x ?? 0.5, 0), 1);
    const yNorm = Math.min(Math.max(center?.y ?? 0.5, 0), 1);
    const xPx = offsetX + xNorm * displayedWidth;
    const yPx = offsetY + yNorm * displayedHeight;
    dot.style.left = `${xPx}px`;
    dot.style.top = `${yPx}px`;
  });
}

async function showSibling(delta) {
  if (currentDetailIndex === -1) return;
  let targetIndex = currentDetailIndex + delta;
  if (targetIndex >= searchState.images.length && !searchState.done) {
    await fetchImages();
  }
  targetIndex = Math.min(
    Math.max(0, targetIndex),
    searchState.images.length - 1,
  );
  if (targetIndex === currentDetailIndex) return;
  const target = searchState.images[targetIndex];
  if (target) {
    await openDetail(target.id);
  }
}

function updateDetailControls() {
  detailPrevBtn.disabled = currentDetailIndex <= 0;
  detailNextBtn.disabled =
    currentDetailIndex < 0 ||
    (currentDetailIndex >= searchState.total - 1 && searchState.done);
  detailCounter.textContent =
    currentDetailIndex >= 0
      ? `${currentDetailIndex + 1} / ${searchState.total}`
      : "";
}

function closeDetail({ skipHistory = false } = {}) {
  pendingDetailId = null;
  if (!detailOverlay.classList.contains("active")) {
    return;
  }
  detailOverlay.classList.remove("active");
  detailOverlay.setAttribute("aria-hidden", "true");
  if (detailSimilarBtn) {
    detailSimilarBtn.disabled = true;
    detailSimilarBtn.dataset.id = "";
  }
  currentDetailId = null;
  currentDetailIndex = -1;
  clearHotspots();
  currentPrompts = { positive: "", negative: "" };
  copyPositiveBtn.disabled = true;
  copyNegativeBtn.disabled = true;
  detailPromptsSection.style.display = "none";
  positiveBlock.style.display = "none";
  negativeBlock.style.display = "none";
  positivePreview.textContent = "";
  negativePreview.textContent = "";
  updateDetailRating(null);
  const imageContainer = detailImage.parentElement;
  if (imageContainer) {
    imageContainer.style.removeProperty("--image-aspect");
    imageContainer.style.removeProperty("aspect-ratio");
  }
  detailImage.style.removeProperty("aspect-ratio");
  updateCopyButtons({ positivePrompt: "", tags: [] });
  if (!skipHistory) {
    const anchorIndexForHistory =
      scrollRestorePending && pendingScrollIndex !== null
        ? pendingScrollIndex
        : getAnchorIndex();
    const clipTokenForHistory = getActiveClipToken();
    pushHistoryState({
      query: lastQuery,
      detail: null,
      pos: anchorIndexForHistory,
      clip: clipTokenForHistory,
      clipSnapshot: clipModeActive ? exportClipChips() : null,
    });
  }
}

function handleHistoryState(state) {
  const safeState = state || { query: "", detail: null, pos: 0, clip: null };
  const nextQuery = (safeState.query || "").trim();
  const nextDetail = normalizeDetail(safeState.detail);
  const nextPos = normalizeIndex(safeState.pos);
  const nextClipToken =
    typeof safeState.clip === "string" && safeState.clip
      ? safeState.clip
      : null;
  const snapshot =
    Array.isArray(safeState.clipSnapshot) && safeState.clipSnapshot.length
      ? safeState.clipSnapshot
      : null;
  const normalizedCurrentClip = currentClipToken || null;
  const clipChanged = nextClipToken !== normalizedCurrentClip;
  const queryChanged = nextQuery !== lastQuery;
  const wasClipModeActive = clipModeActive;
  const targetDetail = nextDetail;

  currentHistoryState = {
    query: nextQuery,
    detail: nextDetail,
    pos: nextPos ?? 0,
    clip: nextClipToken,
    clipSnapshot: snapshot,
  };

  if (searchBox.value !== nextQuery) {
    searchBox.value = nextQuery;
  }
  syncClearButton(searchBox, searchClearBtn);
  syncRatingFiltersFromQuery();

  pendingDetailId = targetDetail;
  pendingScrollIndex = nextPos !== null ? nextPos : 0;
  lastAnchorIndex = pendingScrollIndex;
  scrollRestorePending = true;

  if (nextClipToken) {
    const clipPayload = buildClipPayloadFromToken(nextClipToken, nextQuery);
    if (!clipPayload) {
      clipModeActive = false;
      lastClipPayload = null;
      currentClipToken = null;
      clipOffset = 0;
      clipTotal = 0;
      if (clipSearchInput) clipSearchInput.value = "";
      updateClipSearchClearVisibility();
      pushHistoryState({ clip: null, clipSnapshot: null }, { replace: true });
    } else {
      const wasClipMode = clipModeActive;
      clipModeActive = true;
      currentClipToken = nextClipToken;
      lastQuery = nextQuery;
      if (clipSearchInput) {
        clipSearchInput.value = clipPayload.updateInput || "";
        updateClipSearchClearVisibility();
      }

      const {
        payload: restoredPayload,
        removedUploads,
        pendingUploads,
      } = buildClipSearchPayloadFromState({
        tagQuery: nextQuery,
      });
      if (removedUploads.length) {
        showToast("clip-upload-removed", {
          title: "Removed cached uploads",
          body:
            removedUploads.length === 1
              ? `${removedUploads[0]} was removed because its cached data is unavailable.`
              : `${removedUploads.length} uploads were removed because their cached data was unavailable.`,
          variant: "error",
          autoDismiss: 0,
        });
        const sanitizedSnapshot = restoredPayload.chipsSnapshot || exportClipChips();
        const sanitizedToken =
          ClipState.encodeQuery({
            query: restoredPayload.query || nextQuery || "",
            chips: sanitizedSnapshot,
          }) || null;
        pushHistoryState(
          {
            clip: sanitizedToken,
            clipSnapshot: sanitizedSnapshot.length ? sanitizedSnapshot : null,
            pos: sanitizedToken ? currentHistoryState.pos : 0,
          },
          { replace: true },
        );
        currentClipToken = sanitizedToken;
        console.warn("[clip] History restore removed cached uploads", {
          removedUploads,
          sanitizedToken,
          sanitizedSnapshotLength: sanitizedSnapshot.length,
        });
        if (!sanitizedToken) {
          clipModeActive = false;
          lastClipPayload = null;
          currentClipToken = null;
          clipOffset = 0;
          clipTotal = 0;
          if (clipSearchInput) {
            clipSearchInput.value = "";
            updateClipSearchClearVisibility();
          }
          pendingScrollIndex = 0;
          scrollRestorePending = false;
          fetchImages(true);
          return;
        }
      }
      const restoredSnapshotSize = Array.isArray(restoredPayload.chipsSnapshot)
        ? restoredPayload.chipsSnapshot.length
        : 0;
      if (!restoredSnapshotSize) {
        console.warn("[clip] History restore empty snapshot", {
          nextClipToken,
          query: restoredPayload.query,
        });
        clipModeActive = false;
        lastClipPayload = null;
        currentClipToken = null;
        clipOffset = 0;
        clipTotal = 0;
        if (clipSearchInput) {
          clipSearchInput.value = "";
          updateClipSearchClearVisibility();
        }
        pendingScrollIndex = 0;
        scrollRestorePending = false;
        pushHistoryState({ clip: null, clipSnapshot: null, pos: 0 }, { replace: true });
        fetchImages(true);
        return;
      }
      if (pendingUploads || !restoredPayload) {
        if (pendingUploads) {
          statusEl.textContent = "Processing image…";
        }
        return;
      }

      if (targetDetail === null && detailOverlay.classList.contains("active")) {
        closeDetail({ skipHistory: true });
        pendingDetailId = targetDetail;
      }

      const needFreshFetch =
        clipChanged ||
        queryChanged ||
        !wasClipMode ||
        !searchState.images.length;
      if (needFreshFetch) {
        if (detailOverlay.classList.contains("active")) {
          closeDetail({ skipHistory: true });
        }
        pendingDetailId = targetDetail;
        runClipSearch(restoredPayload, { append: false, updateHistory: false });
        return;
      }

      if (targetDetail !== null) {
        if (
          !detailOverlay.classList.contains("active") ||
          currentDetailId !== targetDetail
        ) {
          pendingDetailId = targetDetail;
          maybeOpenPendingDetail();
        }
      }

      if (!searchState.images.length && !searchState.loading) {
        runClipSearch(restoredPayload, { append: false, updateHistory: false });
        return;
      }

      if (scrollRestorePending) {
        if (
          pendingScrollIndex !== null &&
          pendingScrollIndex >= searchState.images.length &&
          !searchState.done &&
          !searchState.loading
        ) {
          const payloadForAppend = lastClipPayload || restoredPayload;
          runClipSearch(payloadForAppend, {
            append: !!lastClipPayload,
            updateHistory: false,
          });
          return;
        }
        maybeRestoreScrollPosition();
      }
      return;
    }
  } else if (snapshot && snapshot.length) {
    clearClipChips({ silent: true });
    rebuildClipChipsFromSnapshot(snapshot);
    updateClipSearchClearVisibility();
    if (clipChipState.items.length) {
      clipModeActive = true;
      lastQuery = nextQuery;
      ClipState.stashSnapshotForUrl(
        `${window.location.pathname}${window.location.search}`,
        exportClipChips(),
      );
      if (clipSearchInput) {
        clipSearchInput.value = "";
        updateClipSearchClearVisibility();
      }
      const {
        payload,
        removedUploads,
        pendingUploads,
      } = buildClipSearchPayloadFromState({
        tagQuery: nextQuery,
      });
      if (removedUploads.length) {
        showToast("clip-upload-removed", {
          title: "Removed cached uploads",
          body:
            removedUploads.length === 1
              ? `${removedUploads[0]} was removed because its cached data is unavailable.`
              : `${removedUploads.length} uploads were removed because their cached data was unavailable.`,
          variant: "error",
          autoDismiss: 0,
        });
        const sanitizedSnapshot = payload?.chipsSnapshot || exportClipChips();
        const sanitizedToken =
          ClipState.encodeQuery({
            query: (payload && payload.query) || nextQuery || "",
            chips: sanitizedSnapshot,
          }) || null;
        pushHistoryState(
          {
            clip: sanitizedToken,
            clipSnapshot: sanitizedSnapshot.length ? sanitizedSnapshot : null,
            pos: sanitizedToken ? currentHistoryState.pos : 0,
          },
          { replace: true },
        );
        currentClipToken = sanitizedToken;
        console.warn("[clip] Snapshot restore removed cached uploads", {
          removedUploads,
          sanitizedToken,
          sanitizedSnapshotLength: sanitizedSnapshot.length,
        });
        if (!sanitizedToken) {
          clipModeActive = false;
          lastClipPayload = null;
          currentClipToken = null;
          clipOffset = 0;
          clipTotal = 0;
          if (clipSearchInput) {
            clipSearchInput.value = "";
            updateClipSearchClearVisibility();
          }
          pendingScrollIndex = 0;
          scrollRestorePending = false;
          fetchImages(true);
          return;
        }
      }
      const rebuiltSnapshotSize = Array.isArray(payload && payload.chipsSnapshot)
        ? payload.chipsSnapshot.length
        : 0;
      if (!rebuiltSnapshotSize) {
        console.warn("[clip] Snapshot restore empty snapshot", {
          query: (payload && payload.query) || nextQuery,
        });
        clipModeActive = false;
        lastClipPayload = null;
        currentClipToken = null;
        clipOffset = 0;
        clipTotal = 0;
        if (clipSearchInput) {
          clipSearchInput.value = "";
          updateClipSearchClearVisibility();
        }
        pendingScrollIndex = 0;
        scrollRestorePending = false;
        pushHistoryState({ clip: null, clipSnapshot: null, pos: 0 }, { replace: true });
        fetchImages(true);
        return;
      }
      if (pendingUploads || !payload) {
        if (pendingUploads) {
          statusEl.textContent = "Processing image…";
        }
        return;
      }
      runClipSearch(payload, { append: false, updateHistory: false });
      return;
    }
  } else if (clipModeActive || currentClipToken) {
    clipModeActive = false;
    lastClipPayload = null;
    currentClipToken = null;
    clipOffset = 0;
    clipTotal = 0;
    if (clipSearchInput) clipSearchInput.value = "";
    updateClipSearchClearVisibility();
  }

  if (targetDetail === null && detailOverlay.classList.contains("active")) {
    closeDetail({ skipHistory: true });
    pendingDetailId = targetDetail;
  }

  if (queryChanged || wasClipModeActive) {
    lastQuery = nextQuery;
    fetchImages(true);
    return;
  }

  if (!searchState.images.length && !searchState.loading) {
    fetchImages(true);
    return;
  }

  if (targetDetail !== null) {
    if (
      !detailOverlay.classList.contains("active") ||
      currentDetailId !== targetDetail
    ) {
      pendingDetailId = targetDetail;
      maybeOpenPendingDetail();
    }
  }

  if (scrollRestorePending) {
    if (
      pendingScrollIndex !== null &&
      pendingScrollIndex >= searchState.images.length &&
      !searchState.done &&
      !searchState.loading
    ) {
      fetchImages();
    } else {
      maybeRestoreScrollPosition();
    }
  }
}

const initialState = parseStateFromLocation();
const normalizedInitialState = {
  query: (initialState.query || "").trim(),
  detail: normalizeDetail(initialState.detail),
  pos: normalizeIndex(initialState.pos) ?? 0,
  clip:
    typeof initialState.clip === "string" && initialState.clip
      ? initialState.clip
      : null,
  clipSnapshot: Array.isArray(initialState.clipSnapshot)
    ? initialState.clipSnapshot
    : null,
};
lastQuery = normalizedInitialState.query;
if (searchBox.value !== lastQuery) {
  searchBox.value = lastQuery;
}
syncClearButton(searchBox, searchClearBtn);
updateClipSearchClearVisibility();
syncRatingFiltersFromQuery();
pendingDetailId = normalizedInitialState.detail;
pendingScrollIndex = normalizedInitialState.pos;
scrollRestorePending = pendingScrollIndex > 0;
lastAnchorIndex = pendingScrollIndex;
currentHistoryState = { ...normalizedInitialState };
pushHistoryState(normalizedInitialState, { replace: true });
handleHistoryState({ ...normalizedInitialState });

window.addEventListener("popstate", (event) => {
  handleHistoryState(event.state || parseStateFromLocation());
});

if ("IntersectionObserver" in window) {
  autoObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          if (clipModeActive) {
            if (!searchState.loading && !searchState.done && lastClipPayload) {
              runClipSearch(lastClipPayload, {
                append: true,
                updateHistory: false,
              });
            }
          } else {
            fetchImages();
          }
        }
      });
    },
    { rootMargin: "600px 0px" },
  );
  autoObserver.observe(sentinel);
} else {
  loadMoreBtn.style.display = "block";
}

detailImage.addEventListener("load", () => positionHotspots());
window.addEventListener("resize", () => positionHotspots());

// Initialize tag stats cache on page load
document.addEventListener("DOMContentLoaded", () => {
  fetchTagStats();
});

// Periodically refresh tag stats (every 60 seconds, server caches more frequently)
setInterval(() => {
  fetchTagStats();
}, 60000);

async function fetchTagStats() {
  if (tagStatsLoading) return;

  tagStatsLoading = true;
  try {
    const headers = {};
    if (tagStatsLastModified > 0) {
      headers["If-Modified-Since"] = new Date(
        tagStatsLastModified * 1000,
      ).toUTCString();
    }

    const res = await fetch("/api/tag-stats", { headers });

    if (res.status === 304) {
      // Not modified, cache is still valid
      return;
    }

    if (!res.ok) {
      console.error("Failed to fetch tag stats:", res.statusText);
      return;
    }

    const data = await res.json();

    // Update cache
    tagStatsCache.clear();
    if (Array.isArray(data.tags)) {
      data.tags.forEach((tag) => {
        const key = `${tag.norm}|${tag.kind}`;
        tagStatsCache.set(key, tag);
      });
    }

    tagStatsLastModified = data.last_modified || 0;

    // Update rating counts immediately
    updateRatingFilterCounts();

    // Recompute facets if we have current images
    if (searchState.images.length > 0) {
      facetCache = computeFacetsFromCurrentImages();
      renderFacets(facetCache);
    }
  } catch (err) {
    console.error("Error fetching tag stats:", err);
  } finally {
    tagStatsLoading = false;
  }
}

function computeFacetsFromCurrentImages() {
  const facetCounts = new Map();
  const seen = new Set();

  searchState.images.forEach((image) => {
    const tags = searchState.imageTags.get(image.id) || [];
    tags.forEach((tag) => {
      if (!tag || typeof tag !== "object") return;

      const key = `${tag.norm}|${tag.kind}`;
      const cacheKey = `${tag.norm}|${tag.kind}`;

      // Skip duplicates within this image
      if (seen.has(`${image.id}|${key}`)) return;
      seen.add(`${image.id}|${key}`);

      // Get global stats from cache
      const globalStats = tagStatsCache.get(cacheKey);
      if (globalStats) {
        facetCounts.set(key, {
          tag: globalStats.tag,
          norm: globalStats.norm,
          kind: globalStats.kind,
          freq: globalStats.freq, // Global frequency from cache
          localCount: (facetCounts.get(key)?.localCount || 0) + 1, // Local count in current results
        });
      }
    });
  });

  return Array.from(facetCounts.values());
}

async function pollClipStatus() {
  if (!clipSummary) return;
  try {
    const res = await fetch("/api/status/clip");
    if (!res.ok) throw new Error(`status ${res.status}`);
    const data = await res.json();
    const enabled = data.enabled !== false;
    clipEnabled = enabled;
    if (!enabled) {
      clipStatusSection?.classList.remove("status-error");
      clipStatusSection?.classList.add("status-disabled");
      clipSummary.textContent = "CLIP disabled";
      clipProgressBar.style.width = "0%";
      clipProgressBar.dataset.label = "0%";
      if (clipToggleBtn) {
        clipToggleBtn.hidden = true;
        clipToggleBtn.dataset.state = "paused";
      }
      if (clipSearchInput) clipSearchInput.disabled = true;
      if (clipSearchClear) clipSearchClear.disabled = true;
      updateClipSearchClearVisibility();
      if (detailSimilarBtn) {
        detailSimilarBtn.disabled = true;
        detailSimilarBtn.dataset.id = "";
      }
      dismissToast("clip-error");
      requestAnimationFrame(updateStatusCardHeight);
      return;
    }

    clipStatusSection?.classList.remove("status-disabled");
    if (clipSearchInput) clipSearchInput.disabled = false;
    if (clipSearchClear && !searchState.loading)
      clipSearchClear.disabled = false;
    updateClipSearchClearVisibility();
    if (detailSimilarBtn && Number.isFinite(currentDetailId))
      detailSimilarBtn.disabled = false;

    const total = Number.isFinite(Number(data.total)) ? Number(data.total) : 0;
    const completed = Number.isFinite(Number(data.completed))
      ? Number(data.completed)
      : 0;
    const processing = Number.isFinite(Number(data.processing))
      ? Number(data.processing)
      : 0;
    pushProgress(clipProgressHistory, completed, total);
    const ratePerMin = averageRatePerMinute(clipProgressHistory);
    const remaining = Math.max(total - completed, 0);
    const etaSeconds = computeEtaSeconds(remaining, ratePerMin);
    const percent = total ? Math.round((completed / total) * 100) : 0;
    clipProgressBar.style.width = `${percent}%`;
    clipProgressBar.dataset.label = `${percent}%`;
    const stateLabel = typeof data.state === "string" ? data.state : "idle";
    const errorCount = Number.isFinite(Number(data.error_count))
      ? Number(data.error_count)
      : 0;
    const clipLines = [
      `Completed: ${completed}/${total} (${percent}%)`,
      `Pending: ${processing}`,
      errorCount ? `Errors: ${errorCount}` : null,
      buildRateSummary(ratePerMin, etaSeconds),
    ].filter(Boolean);
    clipSummary.textContent = clipLines.join("\n");
    if (clipToggleBtn) {
      const isPaused = stateLabel === "paused";
      const isComplete = !isPaused && remaining === 0;
      updateStatusToggleButton(clipToggleBtn, {
        hidden: false,
        disabled: isComplete,
        state: isComplete ? "complete" : isPaused ? "paused" : "running",
        icon: isComplete ? "✔" : isPaused ? "▶" : "⏸",
        label: isComplete
          ? "CLIP indexing complete"
          : isPaused
            ? "Resume CLIP indexer"
            : "Pause CLIP indexer",
      });
    }

    const errors = Array.isArray(data.error_sample) ? data.error_sample : [];
    if (errors.length) {
      const latest = String(errors[errors.length - 1]);
      const fingerprint = toastFingerprint("CLIP indexer issue", latest);
      if (isToastSuppressed("clip-error", fingerprint)) {
        clipStatusSection?.classList.remove("status-error");
      } else {
        clipStatusSection?.classList.add("status-error");
        showToast("clip-error", {
          title: "CLIP indexer issue",
          body: latest,
          variant: "error",
          onDismiss: () => clipStatusSection?.classList.remove("status-error"),
        });
      }
    } else {
      clipStatusSection?.classList.remove("status-error");
      dismissToast("clip-error");
      requestAnimationFrame(updateStatusCardHeight);
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    clipSummary.textContent = "CLIP status unavailable";
    clipStatusSection?.classList.remove("status-disabled");
    clipStatusSection?.classList.add("status-error");
    showToast("clip-error", {
      title: "CLIP status unavailable",
      body: message,
      variant: "error",
      onDismiss: () => clipStatusSection?.classList.remove("status-error"),
    });
    requestAnimationFrame(updateStatusCardHeight);
  }
}

async function pollAutoStatus() {
  if (!autoStatusSection || !autoSummary || !autoErrorsList) return;
  try {
    const res = await fetch("/api/status/auto");
    autoStatusSection.hidden = false;
    if (res.status === 404) {
      autoStatusSection.classList.add("status-disabled");
      autoStatusSection.classList.remove("status-error");
      autoSummary.textContent = "Auto-tag status unavailable";
      autoErrorsList.innerHTML = "";
      if (autoProgressBar) {
        autoProgressBar.style.width = "0%";
        autoProgressBar.dataset.label = "0%";
      }
      dismissToast("auto-error");
      requestAnimationFrame(updateStatusCardHeight);
      return;
    }
    if (!res.ok) throw new Error(`status ${res.status}`);
    const data = await res.json();
    const enabled = data.enabled !== false;
    const stateLabel = typeof data.state === "string" ? data.state : "idle";
    const total = Number(data.total) || 0;
    const completed = Number(data.completed) || 0;
    const processing = Number(data.processing) || 0;
    pushProgress(autoProgressHistory, completed, total);
    const ratePerMin = averageRatePerMinute(autoProgressHistory);
    const remaining = Math.max(total - completed, 0);
    const etaSeconds = computeEtaSeconds(remaining, ratePerMin);
    const errors = Array.isArray(data.error_sample) ? data.error_sample : [];

    if (!enabled) {
      autoStatusSection.classList.add("status-disabled");
      autoStatusSection.classList.remove("status-error");
      autoSummary.textContent = "Auto-tagging disabled";
      autoErrorsList.innerHTML = "";
      if (autoProgressBar) {
        autoProgressBar.style.width = "0%";
        autoProgressBar.dataset.label = "0%";
      }
      if (autoToggleBtn) {
        updateStatusToggleButton(autoToggleBtn, {
          hidden: true,
          disabled: true,
        });
      }
      dismissToast("auto-error");
      requestAnimationFrame(updateStatusCardHeight);
      return;
    }

    autoStatusSection.classList.remove("status-disabled");

    const autoPercent = total ? Math.round((completed / total) * 100) : 0;
    const autoErrors = Number.isFinite(Number(data.error_count))
      ? Number(data.error_count)
      : 0;
    const autoLines = [
      `Completed: ${completed}/${total} (${autoPercent}%)`,
      `Pending: ${processing}`,
      autoErrors ? `Errors: ${autoErrors}` : null,
      buildRateSummary(ratePerMin, etaSeconds),
    ].filter(Boolean);
    autoSummary.textContent = autoLines.join("\n");
    if (autoToggleBtn) {
      const isPaused = data.paused === true || stateLabel === "paused";
      const isComplete = enabled && !isPaused && remaining === 0;
      updateStatusToggleButton(autoToggleBtn, {
        hidden: !enabled,
        disabled: isComplete,
        state: isComplete ? "complete" : isPaused ? "paused" : "running",
        icon: isComplete ? "✔" : isPaused ? "▶" : "⏸",
        label: isComplete
          ? "Auto tagger idle"
          : isPaused
            ? "Resume auto tagger"
            : "Pause auto tagger",
      });
    }
    if (autoProgressBar) {
      autoProgressBar.style.width = `${Math.max(0, Math.min(100, autoPercent))}%`;
      autoProgressBar.dataset.label = `${autoPercent}%`;
    }
    autoErrorsList.innerHTML = "";
    if (errors.length) {
      errors.slice(-3).forEach((errMsg) => {
        const li = document.createElement("li");
        li.textContent = String(errMsg);
        autoErrorsList.appendChild(li);
      });
      const latestAuto = String(errors[errors.length - 1]);
      const autoFingerprint = toastFingerprint(
        "Auto tagger issues",
        latestAuto,
      );
      if (isToastSuppressed("auto-error", autoFingerprint)) {
        autoStatusSection.classList.remove("status-error");
      } else {
        autoStatusSection.classList.add("status-error");
        showToast("auto-error", {
          title: "Auto tagger issues",
          body: latestAuto,
          variant: "error",
          onDismiss: () => autoStatusSection.classList.remove("status-error"),
        });
      }
    } else {
      autoStatusSection.classList.remove("status-error");
      dismissToast("auto-error");
    }
    requestAnimationFrame(updateStatusCardHeight);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    autoStatusSection.classList.add("status-error");
    autoStatusSection.classList.remove("status-disabled");
    autoSummary.textContent = "Auto-tag status unavailable";
    if (autoProgressBar) {
      autoProgressBar.style.width = "0%";
      autoProgressBar.dataset.label = "0%";
    }
    showToast("auto-error", {
      title: "Auto-tag status unavailable",
      body: message,
      variant: "error",
      onDismiss: () => autoStatusSection.classList.remove("status-error"),
    });
    requestAnimationFrame(updateStatusCardHeight);
  }
}

async function toggleClipIndexer() {
  if (!clipToggleBtn) return;
  const state = clipToggleBtn.dataset.state;
  if (state === "complete") return;
  const target = state === "paused" ? "resume" : "pause";
  try {
    const res = await fetch(`/api/clip/${target}`, { method: "POST" });
    if (!res.ok) throw new Error(res.statusText);
    setTimeout(pollClipStatus, 300);
  } catch (err) {
    clipSummary.textContent = "Unable to toggle CLIP indexer";
  }
}
if (clipToggleBtn) {
  clipToggleBtn.addEventListener("click", toggleClipIndexer);
}

async function toggleAutoIndexer() {
  if (!autoToggleBtn) return;
  const state = autoToggleBtn.dataset.state;
  if (state === "complete") return;
  const target = state === "paused" ? "resume" : "pause";
  try {
    const res = await fetch(`/api/auto/${target}`, { method: "POST" });
    if (!res.ok) throw new Error(res.statusText);
    setTimeout(pollAutoStatus, 300);
  } catch (err) {
    autoSummary.textContent = "Unable to toggle auto tagger";
  }
}
if (autoToggleBtn) {
  autoToggleBtn.addEventListener("click", toggleAutoIndexer);
}
setInterval(() => {
  pollClipStatus();
  pollAutoStatus();
}, 2000);
pollClipStatus();
pollAutoStatus();
