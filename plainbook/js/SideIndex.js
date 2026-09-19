import { ref, computed, onBeforeUnmount } from './vue.esm-browser.js';

const HEADER_RE = /^(#{1,3})\s+(.+)$/;
const PREVIEW_WORDS = 5;

function cellSource(cell) {
    const s = cell?.source;
    return Array.isArray(s) ? s.join('') : (s || '');
}

function explanationText(cell) {
    const e = cell?.metadata?.explanation;
    return Array.isArray(e) ? e.join('') : (e || '');
}

/** First few words of a description, with an ellipsis when truncated */
function previewText(text, wordCount = PREVIEW_WORDS) {
    const cleaned = (text || '').replace(/\s+/g, ' ').trim();
    if (!cleaned) return '';
    const words = cleaned.split(' ');
    if (words.length <= wordCount) return cleaned;
    return words.slice(0, wordCount).join(' ') + '...';
}

/**
 * Collect markdown headings and code cells in document order.
 * kind: 'h1' | 'h2' | 'h3' | 'code'
 */
function buildOutlineEntries(cells) {
    if (!cells || !cells.length) return [];

    const raw = [];
    cells.forEach((cell, cellIndex) => {
        if (cell.cell_type === 'markdown') {
            const source = cellSource(cell);
            const lines = source.split('\n');
            lines.forEach((line, lineIndex) => {
                const m = line.match(HEADER_RE);
                if (!m) return;
                const level = m[1].length;
                raw.push({
                    kind: level === 1 ? 'h1' : (level === 2 ? 'h2' : 'h3'),
                    level,
                    title: m[2].trim(),
                    cellIndex,
                    lineIndex,
                    id: `${cellIndex}-${lineIndex}`,
                });
            });
            return;
        }
        if (cell.cell_type === 'code') {
            const explanation = explanationText(cell);
            const preview = previewText(explanation);
            raw.push({
                kind: 'code',
                level: 2,
                title: preview || '(no description)',
                cellIndex,
                id: `code-${cellIndex}`,
            });
        }
    });
    return raw;
}

/**
 * Nest outline: H1 = main header; H2 / H3 / code cells nest under the
 * current H1 when present (otherwise appear at the root).
 */
function buildOutlineTree(entries) {
    const roots = [];
    let currentH1 = null;
    let currentH2 = null;

    for (const e of entries) {
        if (e.kind === 'h1') {
            currentH1 = { ...e, children: [] };
            currentH2 = null;
            roots.push(currentH1);
            continue;
        }

        if (e.kind === 'h2') {
            const node = { ...e, children: [] };
            currentH2 = node;
            if (currentH1) {
                currentH1.children.push(node);
            } else {
                roots.push(node);
            }
            continue;
        }

        if (e.kind === 'h3') {
            if (currentH2) {
                currentH2.children.push(e);
            } else if (currentH1) {
                currentH1.children.push(e);
            } else {
                roots.push(e);
            }
            continue;
        }

        // code cell — treat like a sub-item under the current main header. If there is a H2, goes under the H2.
        if (currentH2) {
            currentH2.children.push(e);
        } else if (currentH1) {
            currentH1.children.push(e);
        } else {
            roots.push(e);
        }
    }
    return roots;
}

function itemClass(item) {
    if (item.kind === 'code') return 'side-index-item side-index-code';
    if (item.kind === 'h1') return 'side-index-item side-index-h1';
    if (item.kind === 'h2') return 'side-index-item side-index-h2';
    if (item.kind === 'h3') return 'side-index-item side-index-h3';
    return 'side-index-item side-index-h2';
}

export default {
    props: {
        cells: { type: Array, default: () => [] },
        isOpen: { type: Boolean, default: true },
    },
    emits: ['toggle'],
    setup(props) {
        const width = ref(200);
        // H1 sections start expanded; ids present here are collapsed.
        const collapsed = ref({});
        const isResizing = ref(false);

        const tree = computed(() => buildOutlineTree(buildOutlineEntries(props.cells)));

        const isExpanded = (id) => !collapsed.value[id];

        const toggleExpanded = (id) => {
            collapsed.value = {
                ...collapsed.value,
                [id]: !collapsed.value[id],
            };
        };

        const scrollToCell = (cellIndex) => {
            const area = document.querySelector('.notebook-area');
            if (!area) return;
            const cells = area.querySelectorAll('.notebook-cell');
            const el = cells[cellIndex];
            if (el) {
                el.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        };

        let onMove = null;
        let onUp = null;

        const startResize = (ev) => {
            if (!props.isOpen) return;
            ev.preventDefault();
            isResizing.value = true;
            const startX = ev.clientX;
            const startWidth = width.value;

            onMove = (e) => {
                const next = startWidth + (e.clientX - startX);
                width.value = Math.min(400, Math.max(140, next));
            };
            onUp = () => {
                isResizing.value = false;
                window.removeEventListener('mousemove', onMove);
                window.removeEventListener('mouseup', onUp);
                onMove = null;
                onUp = null;
            };
            window.addEventListener('mousemove', onMove);
            window.addEventListener('mouseup', onUp);
        };

        onBeforeUnmount(() => {
            if (onMove) window.removeEventListener('mousemove', onMove);
            if (onUp) window.removeEventListener('mouseup', onUp);
        });

        return {
            width, isResizing, tree, itemClass,
            isExpanded, toggleExpanded, scrollToCell, startResize,
        };
    },
    template: /* html */ `
        <div class="side-index-wrap" :class="{ 'is-closed': !isOpen, 'is-resizing': isResizing }">
            <aside v-show="isOpen" class="side-index"
                :style="{ width: width + 'px' }">
                <div class="side-index-title">
                    <span class="side-index-title-icon" aria-hidden="true"><i class="bx bx-list-ul"></i></span>
                    <span class="side-index-title-text">Table of Contents</span>
                </div>

                <div class="side-index-body">
                    <p v-if="tree.length === 0" class="side-index-empty">
                        No headings or code cells yet. Add <code>#</code> / <code>##</code>
                        in a comment cell, or create a code cell.
                    </p>
                    <ul v-else class="side-index-list">
                        <li v-for="item in tree" :key="item.id" :class="itemClass(item)">
                            <div class="side-index-row">
                                <button v-if="item.children && item.children.length"
                                    type="button"
                                    class="side-index-expand"
                                    title="Show nested items"
                                    @click.stop="toggleExpanded(item.id)">
                                    <i class="bx"
                                       :class="isExpanded(item.id) ? 'bx-chevron-down' : 'bx-chevron-right'"></i>
                                </button>
                                <span v-else class="side-index-expand-spacer"></span>
                                <button type="button" class="side-index-link"
                                    @click="scrollToCell(item.cellIndex)">
                                    {{ item.title }}
                                </button>
                            </div>

                            <ul v-if="item.children && item.children.length && isExpanded(item.id)"
                                class="side-index-sublist">
                                <li v-for="child in item.children" :key="child.id"
                                    :class="itemClass(child)">
                                    <div class="side-index-row">
                                        <button v-if="child.children && child.children.length"
                                            type="button"
                                            class="side-index-expand"
                                            title="Show nested items"
                                            @click.stop="toggleExpanded(child.id)">
                                            <i class="bx"
                                            :class="isExpanded(child.id) ? 'bx-chevron-down' : 'bx-chevron-right'"></i>
                                        </button>
                                        <span v-else class="side-index-expand-spacer"></span>
                                        <button type="button" class="side-index-link"
                                            @click="scrollToCell(child.cellIndex)">
                                            {{ child.title }}
                                        </button>
                                    </div>
                                    <ul v-if="child.children && child.children.length && isExpanded(child.id)"
                                        class="side-index-sublist">
                                        <li v-for="grand in child.children" :key="grand.id"
                                            :class="itemClass(grand)">
                                            <div class="side-index-row">
                                                <button type="button" class="side-index-link"
                                                    @click="scrollToCell(grand.cellIndex)">
                                                    {{ grand.title }}
                                                </button>
                                            </div>
                                        </li>
                                    </ul>
                                </li>
                            </ul>
                        </li>
                    </ul>
                </div>

                <div class="side-index-resizer" @mousedown="startResize" title="Resize"></div>
            </aside>

            <button type="button"
                class="side-index-toggle"
                :title="isOpen ? 'Hide table of contents' : 'Show table of contents'"
                :aria-label="isOpen ? 'Hide table of contents' : 'Show table of contents'"
                :aria-expanded="isOpen ? 'true' : 'false'"
                @click="$emit('toggle')">
                <i class="bx" :class="isOpen ? 'bx-caret-left' : 'bx-caret-right'"></i>
            </button>
        </div>
    `,
};
