import { createApp, ref, computed, onMounted } from './vue.esm-browser.js';
import { mathjaxDirective } from './markdown.js';

import HistoryCellView from './HistoryCellView.js';
import HistoryTimeline from './HistoryTimeline.js';
import HistoryEntryPanel from './HistoryEntryPanel.js';
import { replay } from './HistoryReplay.js';
import { serverFetch } from './serverFetch.js';

const app = createApp({
    components: { HistoryCellView, HistoryTimeline, HistoryEntryPanel },
    setup() {
        const urlParams = new URLSearchParams(window.location.search);
        const authToken = urlParams.get('token');

        const loading = ref(true);
        const error = ref(null);
        const log = ref([]);
        const initialState = ref(null);
        const hasInitialState = ref(false);
        const notebookName = ref('');
        const sliderIdx = ref(0);
        const selectedIdx = ref(null);

        const reconstruction = computed(() => {
            if (!log.value.length && !initialState.value) {
                return { cells: [], activeCellId: null, lastExecutedByCellId: {} };
            }
            return replay(initialState.value, log.value, sliderIdx.value);
        });

        const cells = computed(() => reconstruction.value.cells);
        const activeCellId = computed(() => reconstruction.value.activeCellId);
        const activeAiProvider = computed(() => reconstruction.value.activeAiProvider);
        const replayIsLocked = computed(() => reconstruction.value.isLocked);
        const shareOutputWithAi = computed(() => reconstruction.value.shareOutputWithAi);

        const selectedEntry = computed(() =>
            (selectedIdx.value !== null && log.value[selectedIdx.value]) || log.value[sliderIdx.value] || null);

        const fetchData = async () => {
            try {
                const res = await serverFetch(`/get_notebook?token=${authToken}`);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const r = await res.json();
                const nb = r.nb;
                notebookName.value = (r.state && r.state.name) || '';
                const meta = (nb && nb.metadata) || {};
                log.value = Array.isArray(meta.log) ? meta.log : [];
                if (meta.log_initial_state) {
                    initialState.value = meta.log_initial_state;
                    hasInitialState.value = true;
                } else {
                    initialState.value = {
                        cells: (nb.cells || []).map(c => ({
                            id: c.id, cell_type: c.cell_type, source: c.source || '',
                            metadata: Object.assign({}, c.metadata || {}),
                        })),
                        metadata: {},
                    };
                    hasInitialState.value = false;
                }
                if (log.value.length > 0) sliderIdx.value = log.value.length - 1;
            } catch (err) {
                error.value = err.message || String(err);
            } finally {
                loading.value = false;
            }
        };

        const onSeek = (i) => { sliderIdx.value = i; };
        const onSelect = (i) => { selectedIdx.value = i; sliderIdx.value = i; };
        const backToEditor = () => { window.location.href = `/?token=${authToken}`; };

        onMounted(fetchData);

        return {
            loading, error, log, cells, sliderIdx, selectedEntry, hasInitialState,
            initialState, notebookName, activeCellId,
            activeAiProvider, replayIsLocked, shareOutputWithAi,
            onSeek, onSelect, backToEditor,
        };
    },
    template: `
        <div class="log-view-root">
            <div class="log-view-navbar">
                <div class="log-view-title">
                    <i class="bx bx-history"></i>
                    <span class="ml-2">Log viewer</span>
                    <span v-if="notebookName" class="has-text-grey-lighter ml-3">— {{ notebookName }}</span>
                </div>
                <div class="log-view-status">
                    <span class="tag is-info is-light mr-2" v-if="activeAiProvider">
                        <i class="bx bx-bot mr-1"></i> AI: {{ activeAiProvider }}
                    </span>
                    <span class="tag is-warning is-light mr-2" v-if="replayIsLocked">
                        <i class="bx bx-lock mr-1"></i> notebook locked
                    </span>
                    <span class="tag is-light mr-2" v-if="!shareOutputWithAi">
                        outputs not shared w/ AI
                    </span>
                    <button class="button is-small is-light" @click="backToEditor">
                        <span class="icon is-small"><i class="bx bx-edit"></i></span>
                        <span>Back to editor</span>
                    </button>
                </div>
            </div>
            <div v-if="loading" class="notification is-info is-light m-4">Loading...</div>
            <div v-else-if="error" class="notification is-danger m-4">Error: {{ error }}</div>
            <div v-else-if="log.length === 0" class="notification is-warning is-light m-4">
                This notebook has no action log. Run with <code>--log</code> and make some changes to record a session.
            </div>
            <template v-else>
                <div v-if="!hasInitialState" class="notification is-warning is-light px-3 py-2 m-2 is-size-7">
                    No <code>log_initial_state</code> in this notebook — replay begins from the current notebook state and may be inaccurate before the first logged event.
                </div>
                <history-timeline :log="log" :current="sliderIdx" :initial-state="initialState" @seek="onSeek" @select="onSelect" />
                <history-entry-panel :entry="selectedEntry" />
                <div class="log-view-cells">
                    <p class="is-size-7 has-text-grey mb-2">
                        Reconstructed state at entry {{ sliderIdx + 1 }} of {{ log.length }}.
                        Outputs are not replayable — only errors/stderr recorded in <code>cell_snapshot</code> are shown.
                    </p>
                    <history-cell-view
                        v-for="(cell, i) in cells"
                        :key="cell.id || i"
                        :cell="cell"
                        :index="i"
                        :is-active="cell.id === activeCellId" />
                </div>
            </template>
        </div>
    `,
});
app.directive('mathjax', mathjaxDirective);
app.mount('#log-view-app');
