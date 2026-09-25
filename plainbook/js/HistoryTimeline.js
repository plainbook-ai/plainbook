import { computed, ref } from './vue.esm-browser.js';
import { opColor } from './HistoryReplay.js';

const LANE_COUNT = 6;
const LANE_LABELS = ['structural', 'edits', 'execute', 'AI', 'settings', 'active cell'];

const AMEND_OPS = new Set(['propose_amend', 'commit_amend', 'unfold']);

const UNIT_TEST_EDIT_OPS = new Set([
    'save_unit_tests',
    'save_unit_test_explanation',
    'save_unit_test_code',
    'clear_unit_test_code',
    'clear_unit_test_outputs',
]);

function opLane(op, isClient) {
    if (isClient) return 5;
    if (op === 'insert_cell' || op === 'delete_cell' || op === 'move_cell') return 0;
    if (op.startsWith('edit_') || op === 'clear_code') return 1;
    if (UNIT_TEST_EDIT_OPS.has(op)) return 1;
    // The amend family edits a cell's description, so it belongs beside the
    // other description changes rather than in the catch-all "settings" lane.
    // propose_amend goes here too although it commits nothing: what the user
    // typed is the interesting part, and it reads as one story with the
    // commit_amend that follows it.
    if (AMEND_OPS.has(op)) return 1;
    if (op.startsWith('execute_') || op === 'run_unit_test_cell') return 2;
    if (op.startsWith('generate_') || op.startsWith('validate_')) return 3;
    return 4;
}

// Strip keys ending in "_timestamp" at any depth so two unit-test dicts
// that differ only in timestamps compare equal.
function stripTimestamps(value) {
    if (Array.isArray(value)) return value.map(stripTimestamps);
    if (value && typeof value === 'object') {
        const out = {};
        for (const k of Object.keys(value)) {
            if (k.endsWith('_timestamp')) continue;
            out[k] = stripTimestamps(value[k]);
        }
        return out;
    }
    return value;
}

function canonicalUnitTests(unitTests) {
    return JSON.stringify(stripTimestamps(unitTests || {}));
}

function keyExp(cellId, testName, role) {
    return `${cellId}\x00${testName}\x00${role}\x00exp`;
}
function keySrc(cellId, testName, role) {
    return `${cellId}\x00${testName}\x00${role}\x00src`;
}
function keyUT(cellId) {
    return `${cellId}\x00_UT_`;
}

function seedPrev(initialState) {
    const prev = {};
    if (!initialState || !Array.isArray(initialState.cells)) return prev;
    for (const c of initialState.cells) {
        const cellId = c.id;
        if (!cellId) continue;
        const tests = (c.metadata && c.metadata.unit_tests) || {};
        prev[keyUT(cellId)] = canonicalUnitTests(tests);
        for (const [testName, t] of Object.entries(tests)) {
            const subs = (t && t.cells) || {};
            for (const role of ['setup', 'test']) {
                const sub = subs[role];
                if (!sub) continue;
                prev[keyExp(cellId, testName, role)] = (sub.metadata && sub.metadata.explanation) || '';
                prev[keySrc(cellId, testName, role)] = sub.source || '';
            }
        }
    }
    return prev;
}

// Decide whether an entry is a no-op edit (content unchanged vs tracked prior).
function isNoOpEdit(entry, prev) {
    const op = entry.op;
    const snap = entry.cell_snapshot;
    const params = entry.params || {};
    const cellId = entry.cell_id;

    if (op === 'edit_code' || op === 'edit_markdown'
            || op === 'edit_explanation' || op === 'clear_code') {
        return !!(snap && snap.changed === false);
    }
    if (op === 'save_unit_tests') {
        const key = keyUT(cellId);
        const canon = canonicalUnitTests(params.unit_tests);
        return key in prev && prev[key] === canon;
    }
    if (op === 'save_unit_test_explanation') {
        const key = keyExp(cellId, params.test_name, params.role);
        return key in prev && prev[key] === (params.explanation ?? '');
    }
    if (op === 'save_unit_test_code') {
        const key = keySrc(cellId, params.test_name, params.role);
        return key in prev && prev[key] === (params.source ?? '');
    }
    if (op === 'clear_unit_test_code') {
        const key = keySrc(cellId, params.test_name, params.role);
        return key in prev && prev[key] === '';
    }
    return false;
}

function updatePrev(entry, prev) {
    const op = entry.op;
    const params = entry.params || {};
    const cellId = entry.cell_id;
    if (op === 'save_unit_tests') {
        prev[keyUT(cellId)] = canonicalUnitTests(params.unit_tests);
        // Also seed sub-cell trackers from the new dict so later save_unit_test_*
        // comparisons have a baseline even if this was the first event.
        const tests = params.unit_tests || {};
        for (const [testName, t] of Object.entries(tests)) {
            const subs = (t && t.cells) || {};
            for (const role of ['setup', 'test']) {
                const sub = subs[role];
                if (!sub) continue;
                prev[keyExp(cellId, testName, role)] = (sub.metadata && sub.metadata.explanation) || '';
                prev[keySrc(cellId, testName, role)] = sub.source || '';
            }
        }
    } else if (op === 'save_unit_test_explanation') {
        prev[keyExp(cellId, params.test_name, params.role)] = params.explanation ?? '';
    } else if (op === 'save_unit_test_code') {
        prev[keySrc(cellId, params.test_name, params.role)] = params.source ?? '';
    } else if (op === 'clear_unit_test_code') {
        prev[keySrc(cellId, params.test_name, params.role)] = '';
    } else if (op === 'generate_unit_test_cell_code') {
        const result = entry.result || {};
        if (result && result.status === 'success' && typeof result.code === 'string') {
            prev[keySrc(cellId, params.test_name, params.role)] = result.code;
        }
    }
}

export default {
    props: ['log', 'current', 'initialState'],
    emits: ['seek', 'select'],
    setup(props, { emit }) {
        const zoom = ref(1);
        const zoomIn = () => { zoom.value = Math.min(zoom.value * 1.5, 32); };
        const zoomOut = () => { zoom.value = Math.max(zoom.value / 1.5, 1); };
        const zoomReset = () => { zoom.value = 1; };

        const dots = computed(() => {
            const prev = seedPrev(props.initialState);
            const kept = [];
            for (let i = 0; i < props.log.length; i++) {
                const e = props.log[i];
                if (isNoOpEdit(e, prev)) {
                    updatePrev(e, prev);
                    continue;
                }
                updatePrev(e, prev);
                kept.push({ e, i });
            }
            const denom = Math.max(1, kept.length - 1);
            return kept.map((item, k) => {
                const { e, i } = item;
                const pct = (k / denom) * 100;
                const isClient = e.source === 'client';
                const lane = opLane(e.op, isClient);
                const displayOp = UNIT_TEST_EDIT_OPS.has(e.op) ? 'unit test edit' : e.op;
                return {
                    idx: i,
                    op: e.op,
                    color: opColor(e.op),
                    left: pct,
                    top: ((lane + 1) / (LANE_COUNT + 1)) * 100,
                    isClient,
                    label: `${displayOp} · ${(e.ts_server || '').slice(11, 19)}`,
                };
            });
        });

        const lanes = computed(() =>
            LANE_LABELS.map((label, i) => ({
                label,
                idx: i,
                top: ((i + 1) / (LANE_COUNT + 1)) * 100,
            })));

        const onSlider = (ev) => emit('seek', Number(ev.target.value));
        const onDotClick = (i) => emit('select', i);

        const currentEntry = computed(() => props.log[props.current] || null);
        const currentLabel = computed(() => {
            const e = currentEntry.value;
            if (!e) return '';
            const ts = (e.ts_server || '').slice(11, 19);
            const n = props.log.length;
            return `Entry ${props.current + 1} of ${n} · ${ts} · ${e.op}`;
        });

        const trackStyle = computed(() => ({ width: `${100 * zoom.value}%` }));

        return {
            dots, lanes, onSlider, onDotClick, currentLabel,
            zoom, zoomIn, zoomOut, zoomReset, trackStyle,
        };
    },
    template: `
        <div class="log-timeline">
            <div class="log-timeline-label" style="display: flex; align-items: center; gap: 0.5rem;">
                <span style="flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{{ currentLabel }}</span>
                <span class="is-size-7 has-text-grey" style="white-space: nowrap;">zoom ×{{ zoom.toFixed(2) }}</span>
                <div class="buttons has-addons mb-0">
                    <button class="button is-small" @click="zoomOut" title="Zoom out" :disabled="zoom <= 1">
                        <span class="icon is-small"><i class="bx bx-minus"></i></span>
                    </button>
                    <button class="button is-small" @click="zoomReset" title="Reset zoom" :disabled="zoom === 1">
                        <span class="icon is-small"><i class="bx bx-reset"></i></span>
                    </button>
                    <button class="button is-small" @click="zoomIn" title="Zoom in">
                        <span class="icon is-small"><i class="bx bx-plus"></i></span>
                    </button>
                </div>
            </div>
            <div class="log-timeline-frame">
                <div class="log-timeline-lanes">
                    <div v-for="l in lanes" :key="l.idx" class="log-timeline-lane-label"
                         :style="{ top: l.top + '%' }">{{ l.label }}</div>
                </div>
                <div class="log-timeline-scroll">
                    <div class="log-timeline-track" :style="trackStyle">
                        <div v-for="l in lanes" :key="l.idx" class="log-timeline-laneline"
                             :style="{ top: l.top + '%' }"></div>
                        <div v-for="d in dots" :key="d.idx"
                             class="log-timeline-dot"
                             :class="{ 'is-client': d.isClient }"
                             :style="{ left: d.left + '%', top: d.top + '%', backgroundColor: d.color }"
                             :title="d.label"
                             @click="onDotClick(d.idx)"></div>
                    </div>
                    <input type="range" class="log-timeline-slider"
                           :style="trackStyle"
                           :min="0" :max="log.length - 1"
                           :value="current" @input="onSlider" />
                </div>
            </div>
        </div>
    `,
};
