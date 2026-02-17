import { createStore } from "/js/AlpineStore.js";
import { callJsonApi, fetchApi } from "/js/api.js";

const DEFAULT_PAGE_SIZE = 100;

const model = {
  initialized: false,
  activeTab: "governance",
  loading: false,
  error: "",
  comingSoon: false,
  comingSoonMessage: "",
  availableTypes: [],

  filters: {
    q: "",
    event_type: "",
    status: "",
    run_id: "",
    from_ts: "",
    to_ts: "",
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
    this.refresh();
  },

  setTab(tab) {
    this.activeTab = tab;
    this.error = "";
    this.comingSoon = false;
    this.comingSoonMessage = "";
    this.availableTypes = [];
    this.page = 1;
    this.total = 0;
    this.items = [];
    this.selectedCandidateIds = [];
    this.trainingNote = "";
    this.refresh();
  },

  get totalPages() {
    return Math.max(1, Math.ceil((this.total || 0) / this.pageSize));
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
    try {
      const contextId = globalThis.getContext?.() || "";
      const offset = Math.max(0, (this.page - 1) * this.pageSize);
      const resp = await callJsonApi(endpoint, {
        context_id: contextId,
        limit: this.pageSize,
        offset,
        ...this.filters,
      });
      this.items = Array.isArray(resp.events)
        ? resp.events
        : Array.isArray(resp.items)
          ? resp.items
          : [];
      this.total = Number(resp.total || this.items.length || 0);
      this.comingSoon = Boolean(resp.coming_soon);
      this.comingSoonMessage = String(resp.message || "");
      this.availableTypes = Array.isArray(resp.types) ? resp.types : [];
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
      const contextId = globalThis.getContext?.() || "";
      const payload = {
        context_id: contextId,
        candidate_ids: this.selectedCandidateIds,
        action,
      };
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
      const contextId = globalThis.getContext?.() || "";
      const offset = Math.max(0, (this.page - 1) * this.pageSize);
      const response = await fetchApi(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "same-origin",
        body: JSON.stringify({
          context_id: contextId,
          limit: this.pageSize,
          offset,
          export_format: fmt,
          ...this.filters,
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
    };
    this.page = 1;
    this.refresh();
  },
};

export const store = createStore("dataEvents", model);
