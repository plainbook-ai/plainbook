import { ref, computed, watch, onMounted, nextTick } from './vue.esm-browser.js';
import ExplanationEditor from './ExplanationEditor.js';
import CodeCell from './CodeCell.js';
import CellCodeBar from './CellCodeBar.js';
import ValidationCell from './ValidationCell.js';
import OutputRenderer from './OutputRenderer.js';
import { outputsHaveError } from './errorUtils.js';

export default {
    components: { ExplanationEditor, CodeCell, CellCodeBar, ValidationCell, OutputRenderer },
    props: ['cell', 'role', 'isActive', 'isLocked', 'running', 'codeValid', 'outputValid'],
    emits: ['save-explanation', 'save-code', 'save-and-run', 'save-code-and-run', 'gencode', 'clearcode', 'validate', 'dismiss-validation', 'run', 'interrupt', 'activate'],
    setup(props) {
        const mode = computed(() => props.role === 'setup' ? 'unit_setup' : 'unit_test');
        const hasError = computed(() => outputsHaveError(props.cell && props.cell.outputs));
        const hasCode = computed(() => (props.cell.source || '').trim().length > 0);
        // Description may be an array of lines (new cells start as []); normalize.
        const canGenerate = computed(() => {
            const e = props.cell.metadata?.explanation;
            const s = Array.isArray(e) ? e.join('') : (e || '');
            return s.trim().length > 0;
        });
        const explanation = computed(() => props.cell.metadata?.explanation || '');
        const outputVisible = ref(true);
        const startEditKey = ref(undefined);
        const openPanel = ref('none');   // 'code' | 'none' (no explanation in unit tests)
        const descEditing = ref(false);

        // Auto-enter edit mode when cell becomes active with empty explanation
        watch(() => props.isActive, (active) => {
            if (active && !explanation.value) {
                startEditKey.value = Date.now();
            }
        });

        // Handle initial mount: if already active with empty explanation, trigger edit after children mount
        onMounted(() => {
            if (props.isActive && !explanation.value) {
                nextTick(() => { startEditKey.value = Date.now(); });
            }
        });

        const triggerEdit = () => {
            startEditKey.value = Date.now();
        };

        return { mode, hasError, hasCode, canGenerate, explanation, outputVisible, startEditKey, triggerEdit,
            openPanel, descEditing };
    },
    template: /* html */ `
        <div class="unit-test-sub-cell notebook-cell box p-0 mb-5 is-clipped shadow-sm"
             @click="$emit('activate')"
             :class="{ 'is-active-cell': isActive }"
             style="cursor: pointer">
            <div class="p-2 has-text-weight-semibold is-size-7 text-muted bg-warning-adaptive"
                 @dblclick="triggerEdit">
                {{ role === 'setup' ? 'Data Preparation' : 'Test' }}
            </div>
            <div class="p-0 border-bottom bg-warning-adaptive" @dblclick="triggerEdit">
                <explanation-editor
                    v-model:source="cell.metadata.explanation"
                    :hasCode="hasCode"
                    :isActive="isActive"
                    :isLocked="isLocked"
                    :running="running"
                    :asRead="false"
                    :codeValid="codeValid"
                    :outputValid="outputValid"
                    :executed="false"
                    :hasError="hasError"
                    :outputVisible="outputVisible"
                    :cellMode="mode"
                    :startEditKey="startEditKey"
                    @save="$emit('save-explanation', $event)"
                    @toggle-output="outputVisible = !outputVisible"
                    @update:editing="descEditing = $event"
                    @run="$emit('run')"
                    @interrupt="$emit('interrupt')"
                    @saveandrun="$emit('save-and-run', $event)"
                    @gencode="$emit('gencode')"
                    @delete=""
                    @moveUp=""
                    @moveDown="" />
            </div>

            <validation-cell
                v-if="cell.metadata?.validation && !cell.metadata?.validation.is_hidden"
                :validation="cell.metadata.validation"
                @dismiss_validation="$emit('dismiss-validation')" />

            <cell-code-bar v-show="isActive"
                v-model:open-panel="openPanel"
                :has-explanation="false"
                :has-code="hasCode"
                :can-generate="canGenerate"
                :code-valid="codeValid"
                :running="running"
                :has-error="hasError"
                :is-locked="isLocked"
                :is-test-cell="false"
                :show-explain="false"
                :editing="descEditing"
                @gencode="$emit('gencode')"
                @clearcode="$emit('clearcode')"
                @validate="$emit('validate')"
                @interrupt="$emit('interrupt')" />

            <code-cell
                v-model:source="cell.source"
                :execution-count="cell.execution_count"
                :is-active="isActive"
                :is-locked="isLocked"
                :codeValid="codeValid"
                :outputValid="outputValid"
                :executed="false"
                :hasError="hasError"
                :asRead="false"
                :external-collapse="openPanel !== 'code'"
                @save="$emit('save-code', $event)"
                @saveandrun="$emit('save-code-and-run', $event)"
                @activate="" />

            <div v-if="outputVisible && cell.outputs?.length" class="p-2 border-top bg-scheme-main">
                <output-renderer v-for="(out, oIdx) in cell.outputs" :key="oIdx" :output="out" />
            </div>
        </div>
    `
};
