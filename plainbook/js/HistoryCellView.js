import { computed, ref } from './vue.esm-browser.js';
import OutputRenderer from './OutputRenderer.js';
import { createMarkdown } from './markdown.js';

const md = createMarkdown({ html: true });

function escapeHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function highlightPython(code) {
    const text = code || '';
    if (!window.Prism || !window.Prism.languages || !window.Prism.languages.python) {
        return escapeHtml(text);
    }
    try {
        return window.Prism.highlight(text, window.Prism.languages.python, 'python');
    } catch (e) {
        return escapeHtml(text);
    }
}

export default {
    components: { OutputRenderer },
    props: ['cell', 'index', 'isActive'],
    setup(props) {
        const cellType = computed(() => props.cell && props.cell.cell_type);
        const source = computed(() => (props.cell && props.cell.source) || '');
        const explanation = computed(() =>
            (props.cell && props.cell.metadata && props.cell.metadata.explanation) || '');
        const outputs = computed(() =>
            (props.cell && Array.isArray(props.cell.outputs)) ? props.cell.outputs : []);
        const renderedExplanation = computed(() =>
            explanation.value ? md.render(explanation.value) : '');
        const renderedMarkdown = computed(() =>
            source.value ? md.render(source.value) : '');
        const highlightedCode = computed(() => highlightPython(source.value));
        const shortId = computed(() => {
            const id = (props.cell && props.cell.id) || '';
            return id ? id.slice(0, 8) : '';
        });

        const renderSubCell = (sub) => {
            const src = (sub && sub.source) || '';
            const exp = (sub && sub.metadata && sub.metadata.explanation) || '';
            return {
                explanation: exp,
                source: src,
                renderedExplanation: exp ? md.render(exp) : '',
                highlightedCode: src ? highlightPython(src) : '',
            };
        };

        const unitTests = computed(() => {
            const ut = props.cell && props.cell.metadata && props.cell.metadata.unit_tests;
            if (!ut || typeof ut !== 'object') return [];
            return Object.entries(ut).map(([name, t]) => ({
                name,
                setup: renderSubCell(t && t.cells && t.cells.setup),
                test: renderSubCell(t && t.cells && t.cells.test),
            }));
        });

        const testsExpanded = ref(false);
        const toggleTests = () => { testsExpanded.value = !testsExpanded.value; };

        return {
            cellType, source, explanation, outputs,
            renderedExplanation, renderedMarkdown, highlightedCode, shortId,
            unitTests, testsExpanded, toggleTests,
        };
    },
    template: /* html */ `
        <div class="log-cell box p-0 mb-2 is-clipped shadow-sm"
             :class="{ 'is-active-in-replay': isActive }">
            <div class="log-cell-header px-3 py-1 is-size-7 has-text-grey"
                 style="display: flex; align-items: center; gap: 0.5rem; border-bottom: 1px solid #ececec;">
                <span class="tag is-light">#{{ index }}</span>
                <span class="tag"
                      :class="{
                          'is-info is-light': cellType === 'code',
                          'is-warning is-light': cellType === 'test',
                          'is-primary is-light': cellType === 'markdown'
                      }">{{ cellType }}</span>
                <span v-if="shortId" class="has-text-grey-light is-family-monospace">{{ shortId }}</span>
                <span style="flex: 1;"></span>
                <span v-if="isActive" class="tag is-info">
                    <span class="icon is-small"><i class="bx bx-target-lock"></i></span>
                    <span>active</span>
                </span>
            </div>

            <div v-if="cellType === 'markdown'" class="markdown-body content p-3" v-html="renderedMarkdown" v-mathjax></div>

            <template v-else>
                <div v-if="explanation" class="log-cell-explanation markdown-body content px-3 pt-2 pb-1"
                     v-html="renderedExplanation" v-mathjax></div>
                <div v-else class="log-cell-explanation-empty px-3 pt-2 pb-1 is-size-7 has-text-grey-light is-italic">
                    (no explanation)
                </div>

                <div v-if="source" class="log-cell-code px-3 py-2">
                    <pre class="language-python m-0"><code class="language-python" v-html="highlightedCode + '\\n'"></code></pre>
                </div>
                <div v-else class="px-3 py-2 is-size-7 has-text-grey-light is-italic">
                    (no code)
                </div>

                <div v-if="outputs.length" class="log-cell-outputs px-3 py-2 border-top bg-scheme-main">
                    <output-renderer v-for="(out, oIdx) in outputs" :key="oIdx" :output="out" />
                </div>

                <div v-if="unitTests.length" class="log-cell-unit-tests px-3 py-2 border-top">
                    <p class="is-size-7 has-text-grey has-text-weight-semibold mb-2"
                       style="cursor: pointer; user-select: none;"
                       @click="toggleTests">
                        <span class="icon is-small">
                            <i class="bx" :class="testsExpanded ? 'bx-chevron-down' : 'bx-chevron-right'"></i>
                        </span>
                        <i class="bx bx-test-tube mr-1"></i>Unit tests ({{ unitTests.length }})
                        <span class="has-text-grey-light ml-2">{{ testsExpanded ? 'click to collapse' : 'click to expand' }}</span>
                    </p>
                    <template v-if="testsExpanded">
                        <div v-for="t in unitTests" :key="t.name" class="log-unit-test mb-3">
                            <p class="is-size-7 has-text-weight-semibold mb-1">{{ t.name }}</p>
                            <div class="log-unit-subcell mb-2">
                                <p class="is-size-7 has-text-grey mb-1"><em>Setup</em></p>
                                <div v-if="t.setup.renderedExplanation" class="markdown-body content is-size-7 mb-1"
                                     v-html="t.setup.renderedExplanation" v-mathjax></div>
                                <pre v-if="t.setup.highlightedCode" class="language-python m-0"><code class="language-python" v-html="t.setup.highlightedCode + '\\n'"></code></pre>
                                <p v-if="!t.setup.renderedExplanation && !t.setup.highlightedCode"
                                   class="is-size-7 has-text-grey-light is-italic">(empty)</p>
                            </div>
                            <div class="log-unit-subcell">
                                <p class="is-size-7 has-text-grey mb-1"><em>Test</em></p>
                                <div v-if="t.test.renderedExplanation" class="markdown-body content is-size-7 mb-1"
                                     v-html="t.test.renderedExplanation" v-mathjax></div>
                                <pre v-if="t.test.highlightedCode" class="language-python m-0"><code class="language-python" v-html="t.test.highlightedCode + '\\n'"></code></pre>
                                <p v-if="!t.test.renderedExplanation && !t.test.highlightedCode"
                                   class="is-size-7 has-text-grey-light is-italic">(empty)</p>
                            </div>
                        </div>
                    </template>
                </div>
            </template>
        </div>
    `,
};
