import { createStore } from "/js/AlpineStore.js";
import { callJsonApi, fetchApi } from "/js/api.js";
import { store as chatsStore } from "/components/sidebar/chats/chats-store.js";

const DEFAULT_PAGE_SIZE = 100;
const ALLOWED_TABS = new Set(["governance", "training", "system"]);
const ALLOWED_SCOPES = new Set(["global", "project", "chat"]);

const model = {
  initialized: false,
  isOpen: false,
  activeTab: "governance",
  scope: "global",
  loading: false,
  error: "",
  comingSoon: false,
  comingSoonMessage: "",
  availableTypes: [],
  summary: {},
  trackCounts: {
    llm_training: 0,
    agent_tooling: 0,
    harness_improvement: 0,
  },

  filters: {
    q: "",
    event_type: "",
    status: "",
    run_id: "",
    from_ts: "",
    to_ts: "",
    candidate_track: "",
    consent_scope: "",
  },

  page: 1,
  pageSize: DEFAULT_PAGE_SIZE,
  total: 0,
  items: [],
  selectedCandidateIds: [],
  trainingNote: "",

  init() {
    if (this.initialized) return;
    this.initialized = true;
  },

  open(options = {}) {
    this.init();
    this.isOpen = true;

    const nextTab = String(options.tab || "").trim().toLowerCase();
    if (ALLOWED_TABS.has(nextTab)) {
      this.activeTab = nextTab;
    }

    const nextScope = String(options.scope || "").trim().toLowerCase();
    if (ALLOWED_SCOPES.has(nextScope)) {
      this.scope = nextScope;
    }

    this.refresh();
  },

  close() {
    this.isOpen = false;
  },

  get totalPages() {
    return Math.max(1, Math.ceil((this.total || 0) / this.pageSize));
  },

  get selectedContextId() {
    return String(globalThis.getContext?.() || "").trim();
  },

  get selectedProjectName() {
    const fromContext = String(chatsStore?.selectedContext?.project_name || "").trim();
    if (fromContext) return fromContext;
    return String(chatsStore?.selectedContext?.project || "").trim();
  },

  get scopeContextLabel() {
    if (this.scope === "chat") {
      return this.selectedContextId || "No chat selected";
    }
    if (this.scope === "project") {
      return this.selectedProjectName || "No project active";
    }
    return "All data";
  },

  get scopeWarning() {
    if (this.scope === "chat" && !this.selectedContextId) {
      return "Chat scope requires an active chat context.";
    }
    if (this.scope === "project" && !this.selectedProjectName) {
      return "Project scope requires a context with an active project.";
    }
    return "";
  },

  setScope(scope) {
    const next = String(scope || "").trim().toLowerCase();
    if (!ALLOWED_SCOPES.has(next)) return;
    this.scope = next;
    this.page = 1;
    this.refresh();
  },

  setTab(tab) {
    const next = String(tab || "").trim().toLowerCase();
    if (!ALLOWED_TABS.has(next)) return;
    this.activeTab = next;
    this.error = "";
    this.comingSoon = false;
    this.comingSoonMessage = "";
    this.availableTypes = [];
    this.page = 1;
    this.total = 0;
    this.items = [];
    this.selectedCandidateIds = [];
    this.trainingNote = "";
    this.trackCounts = {
      llm_training: 0,
      agent_tooling: 0,
      harness_improvement: 0,
    };
    this.summary = {};
    this.refresh();
  },

  _scopePayload() {
    if (this.scope === "chat") {
      const contextId = this.selectedContextId;
      if (!contextId) return { context_id: "" };
      return { context_id: contextId };
    }
    if (this.scope === "project") {
      const projectName = this.selectedProjectName;
      if (!projectName) return { project_name: "" };
      return { project_name: projectName };
    }
    return {};
  },

  _requestPayload() {
    const payload = {
      limit: this.pageSize,
      offset: Math.max(0, (this.page - 1) * this.pageSize),
      q: this.filters.q,
      event_type: this.filters.event_type,
      status: this.filters.status,
      run_id: this.filters.run_id,
      from_ts: this.filters.from_ts,
      to_ts: this.filters.to_ts,
      candidate_track: this.filters.candidate_track,
      consent_scope: this.filters.consent_scope,
      ...this._scopePayload(),
    };
    return payload;
  },

  async refresh() {
    const endpointByTab = {
      governance: "/governance_events",
      training: "/training_candidates",
      system: "/system_trace",
    };
    const endpoint = endpointByTab[this.activeTab];
    if (!endpoint) return;

    this.loading = true;
    this.error = "";
    this.comingSoon = false;
    this.comingSoonMessage = "";
    this.availableTypes = [];
    this.trackCounts = {
      llm_training: 0,
      agent_tooling: 0,
      harness_improvement: 0,
    };

    try {
      const payload = this._requestPayload();
      const resp = await callJsonApi(endpoint, payload);
      this.items = Array.isArray(resp.events)
        ? resp.events
        : Array.isArray(resp.items)
          ? resp.items
          : [];
      this.total = Number(resp.total || this.items.length || 0);
      this.comingSoon = Boolean(resp.coming_soon);
      this.comingSoonMessage = String(resp.message || "");
      this.availableTypes = Array.isArray(resp.types) ? resp.types : [];
      this.summary = typeof resp.summary === "object" && resp.summary ? resp.summary : {};

      if (resp.track_counts && typeof resp.track_counts === "object") {
        this.trackCounts = {
          llm_training: Number(resp.track_counts.llm_training || 0),
          agent_tooling: Number(resp.track_counts.agent_tooling || 0),
          harness_improvement: Number(resp.track_counts.harness_improvement || 0),
        };
      }
    } catch (e) {
      this.error = e?.message || String(e);
      this.items = [];
      this.total = 0;
    } finally {
      this.loading = false;
    }
  },

  isSelected(candidateId) {
    const cid = String(candidateId || "").trim();
    if (!cid) return false;
    return this.selectedCandidateIds.includes(cid);
  },

  toggleSelect(candidateId) {
    const cid = String(candidateId || "").trim();
    if (!cid) return;
    if (this.selectedCandidateIds.includes(cid)) {
      this.selectedCandidateIds = this.selectedCandidateIds.filter((x) => x !== cid);
    } else {
      this.selectedCandidateIds = [...this.selectedCandidateIds, cid];
    }
  },

  selectAllVisible() {
    if (this.activeTab !== "training") return;
    const ids = this.items
      .map((x) => String(x?.candidate_id || "").trim())
      .filter(Boolean);
    this.selectedCandidateIds = Array.from(new Set([...this.selectedCandidateIds, ...ids]));
  },

  clearSelection() {
    this.selectedCandidateIds = [];
  },

  async bulkUpdateTraining(action) {
    if (this.activeTab !== "training") return;
    if (!this.selectedCandidateIds.length) {
      this.error = "Select at least one candidate.";
      return;
    }
    this.error = "";
    try {
      const payload = {
        candidate_ids: this.selectedCandidateIds,
        action,
        ...this._scopePayload(),
      };
      if (this.scope !== "project") {
        const contextId = this.selectedContextId;
        if (contextId) payload.context_id = contextId;
      }
      const note = String(this.trainingNote || "").trim();
      if (note) payload.note = note;
      await callJsonApi("/training_candidates_update", payload);
      this.clearSelection();
      await this.refresh();
    } catch (e) {
      this.error = e?.message || String(e);
    }
  },

  async exportCurrent(format) {
    const endpointByTab = {
      governance: "/governance_events",
      training: "/training_candidates",
    };
    const endpoint = endpointByTab[this.activeTab];
    if (!endpoint) return;
    const fmt = String(format || "").toLowerCase();
    if (!["jsonl", "csv"].includes(fmt)) return;

    this.error = "";
    try {
      const response = await fetchApi(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "same-origin",
        body: JSON.stringify({
          ...this._requestPayload(),
          export_format: fmt,
        }),
      });

      if (!response.ok) {
        throw new Error(await response.text());
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const base = this.activeTab === "training" ? "training-candidates" : "governance-events";
      a.download = fmt === "csv" ? `${base}.csv` : `${base}.jsonl`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      this.error = e?.message || String(e);
    }
  },

  nextPage() {
    if (this.page < this.totalPages) {
      this.page += 1;
      this.refresh();
    }
  },

  prevPage() {
    if (this.page > 1) {
      this.page -= 1;
      this.refresh();
    }
  },

  resetFilters() {
    this.filters = {
      q: "",
      event_type: "",
      status: "",
      run_id: "",
      from_ts: "",
      to_ts: "",
      candidate_track: "",
      consent_scope: "",
    };
    this.page = 1;
    this.refresh();
  },
};

export const store = createStore("dataManager", model);
