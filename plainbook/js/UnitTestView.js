import { ref, computed, watch, onMounted, nextTick } from './vue.esm-browser.js';
import UnitTestTabBar from './UnitTestTabBar.js';
import UnitTestSubCell from './UnitTestSubCell.js';
import ExplanationEditor from './ExplanationEditor.js';
import CodeCell from './CodeCell.js';
import CellCodeBar from './CellCodeBar.js';
import ValidationCell from './ValidationCell.js';
import OutputRenderer from './OutputRenderer.js';
import CellLabel from './CellLabel.js';
import UnitTestHelpModal from './UnitTestHelpModal.js';
import { outputsHaveError } from './errorUtils.js';

export default {
    components: { UnitTestTabBar, UnitTestSubCell, ExplanationEditor, CodeCell, CellCodeBar, ValidationCell, OutputRenderer, CellLabel, UnitTestHelpModal },
    props: ['notebook', 'targetCellIndex', 'authToken', 'running', 'runningActivity',
            'isLocked', 'mainLocked', 'lastValidCodeCellIndex', 'lastValidOutputCellIndex', 'unitTestValidity',
            'activeSubCell', 'activeTestName'],
    emits: ['exit',
            'save-unit-tests', 'save-unit-test-explanation', 'save-unit-test-code',
            'clear-unit-test-code', 'clear-unit-test-outputs', 'run-unit-test', 'run-unit-test-subcell', 'generate-unit-test-code',
            'validate-unit-test-code', 'dismiss-unit-test-validation',
            'add-unit-test', 'delete-unit-test', 'rename-unit-test',
            'save-explanation', 'save-code', 'gencode', 'clearcode', 'validate', 'dismiss-validation',
            'interrupt',
            'update:activeSubCell', 'update:activeTestName'],
    setup(props, { emit }) {
        const activeTestName = computed({
            get: () => props.activeTestName,
            set: (v) => emit('update:activeTestName', v),
        });
        const activeSubCell = computed({
            get: () => props.activeSubCell,
            set: (v) => emit('update:activeSubCell', v),
        });

        const targetCell = computed(() => {
            if (!props.notebook || !props.notebook.cells) return null;
            return props.notebook.cells[props.targetCellIndex];
        });

        const unitTests = computed(() => {
            if (!targetCell.value) return {};
            return targetCell.value.metadata?.unit_tests || {};
        });

        const activeTest = computed(() => {
            if (!activeTestName.value) return null;
            return unitTests.value[activeTestName.value] || null;
        });

        const hasTargetError = computed(() => outputsHaveError(targetCell.value && targetCell.value.outputs));

        // Description may be an array of lines (new cells start as []); normalize.
        const targetCanGenerate = computed(() => {
            const e = targetCell.value && targetCell.value.metadata && targetCell.value.metadata.explanation;
            const s = Array.isArray(e) ? e.join('') : (e || '');
            return s.trim().length > 0;
        });

        const targetCodeValid = computed(() => props.lastValidCodeCellIndex >= props.targetCellIndex);
        const targetOutputVisible = ref(true);
        const targetOpenPanel = ref('none');   // 'code' | 'none' (no explanation in unit tests)
        const targetDescEditing = ref(false);

        const activeTestValidity = computed(() => {
            if (!props.unitTestValidity || !activeTestName.value) return null;
            return props.unitTestValidity[activeTestName.value] || null;
        });

        const targetOutputValid = computed(() => activeTestValidity.value?.target?.output_valid ?? false);
        const setupCodeValid = computed(() => activeTestValidity.value?.setup?.code_valid ?? false);
        const setupOutputValid = computed(() => activeTestValidity.value?.setup?.output_valid ?? false);
        const testCodeValid = computed(() => activeTestValidity.value?.test?.code_valid ?? false);
        const testOutputValid = computed(() => activeTestValidity.value?.test?.output_valid ?? false);

        const targetTestOutputs = computed(() => {
            return activeTest.value?.cells?.target?.outputs || targetCell.value?.outputs || [];
        });

        // Keep activeTestName valid (fallback for renames, external changes, etc.)
        // deep: true is required because unitTests is a computed returning the same
        // reactive object reference — without deep, in-place mutations (delete/add key)
        // don't trigger the watcher.
        watch(unitTests, (tests) => {
            const names = Object.keys(tests);
            if (names.length === 0) {
                activeTestName.value = null;
            } else if (!activeTestName.value || !(activeTestName.value in tests)) {
                activeTestName.value = names[0];
            }
        }, { immediate: true, deep: true });

        const handleAdd = () => {
            // Predict the new test name (same logic as addUnitTest in nb.js)
            const tests = unitTests.value;
            let testNum = Object.keys(tests).length + 1;
            while (`Test ${testNum}` in tests) testNum++;
            const newName = `Test ${testNum}`;
            emit('add-unit-test', props.targetCellIndex);
            activeTestName.value = newName;
            // Force the setup sub-cell's isActive watch to fire so it enters edit mode
            activeSubCell.value = null;
            nextTick(() => { activeSubCell.value = 'setup'; });
        };

        const clearOutputs = () => {
            if (!activeTest.value || !activeTestName.value) return;
            activeTest.value.cells.setup.outputs = [];
            if (activeTest.value.cells.target) activeTest.value.cells.target.outputs = [];
            activeTest.value.cells.test.outputs = [];
            emit('clear-unit-test-outputs', props.targetCellIndex, activeTestName.value);
        };

        const handleDelete = (testName) => {
            const names = Object.keys(unitTests.value);
            const idx = names.indexOf(testName);
            // Pick predecessor, then successor, then exit
            if (names.length <= 1) {
                emit('delete-unit-test', props.targetCellIndex, testName);
                emit('exit');
                return;
            }
            if (idx > 0) {
                activeTestName.value = names[idx - 1];
            } else {
                activeTestName.value = names[idx + 1];
            }
            emit('delete-unit-test', props.targetCellIndex, testName);
        };

        const rootEl = ref(null);
        const focusRoot = () => {
            nextTick(() => {
                const active = document.activeElement;
                if (active && (active.tagName === 'TEXTAREA' || active.tagName === 'INPUT')) return;
                rootEl.value?.focus({ preventScroll: true });
            });
        };

        const showHelp = ref(false);

        // Focus root div when entering unit test mode
        onMounted(focusRoot);

        return {
            activeTestName, activeSubCell, targetCell, unitTests, activeTest,
            hasTargetError, targetCanGenerate, targetCodeValid, targetOutputValid, targetOutputVisible,
            targetOpenPanel, targetDescEditing,
            activeTestValidity, setupCodeValid, setupOutputValid, testCodeValid, testOutputValid,
            targetTestOutputs, handleAdd, handleDelete, clearOutputs,
            rootEl, focusRoot, showHelp
        };
    },
    template: /* html */ `
        <div v-if="targetCell" ref="rootEl" tabindex="-1" style="display: flex; flex-direction: column; flex-grow: 1; min-height: 0; outline: none;">
            <unit-test-tab-bar
                :tests="unitTests"
                :active-name="activeTestName"
                @select="activeTestName = $event"
                @add="handleAdd"
                @rename="(oldName, newName) => $emit('rename-unit-test', targetCellIndex, oldName, newName)"
                @exit="$emit('exit')"
            />

            <!-- Action buttons bar (between tab bar and scrollable area) -->
            <div v-if="activeTest" class="px-4 py-2" style="display: flex; justify-content: space-between; align-items: center; flex-shrink: 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <div style="display: flex; gap: 0.5rem;">
                    <button class="button is-success is-small" @click="showHelp = true">
                        <span class="icon"><i class="bx bx-info-circle"></i></span>
                        <span>Test help</span>
                    </button>
                    <button class="button is-small is-light"
                            :disabled="running"
                            @click="clearOutputs">
                        <span class="icon"><i class="bx bx-broom"></i></span>
                        <span>Clear outputs</span>
                    </button>
                    <button class="button is-small is-warning"
                            :disabled="running || isLocked"
                            @click="$emit('run-unit-test', targetCellIndex, activeTestName)">
                        <span class="icon"><i class="bx bx-play"></i></span>
                        <span>Run test</span>
                    </button>
                </div>
                <button class="button is-small is-danger is-outlined"
                        :disabled="running || isLocked"
                        @click="handleDelete(activeTestName)">
                    <span class="icon"><i class="bx bx-trash"></i></span>
                    <span>Delete test</span>
                </button>
            </div>

            <div class="section notebook-area" style="padding-top: 1rem; flex-grow: 1; overflow-y: auto;">
            <div v-if="activeTest" class="notebook-container px-2 py-2">

                <!-- Setup sub-cell -->
                <unit-test-sub-cell
                    :cell="activeTest.cells.setup"
                    role="setup"
                    :is-active="activeSubCell === 'setup'"
                    @activate="activeSubCell = 'setup'; focusRoot()"
                    :is-locked="isLocked"
                    :running="running"
                    :code-valid="setupCodeValid"
                    :output-valid="setupOutputValid"
                    @save-explanation="(content) => $emit('save-unit-test-explanation', targetCellIndex, activeTestName, 'setup', content)"
                    @save-code="(content) => $emit('save-unit-test-code', targetCellIndex, activeTestName, 'setup', content)"
                    @save-and-run="(content) => { $emit('save-unit-test-explanation', targetCellIndex, activeTestName, 'setup', content); $emit('run-unit-test-subcell', targetCellIndex, activeTestName, 'setup'); activeSubCell = 'target'; }"
                    @save-code-and-run="(content) => { $emit('save-unit-test-code', targetCellIndex, activeTestName, 'setup', content); $emit('run-unit-test-subcell', targetCellIndex, activeTestName, 'setup'); activeSubCell = 'target'; }"
                    @gencode="$emit('generate-unit-test-code', targetCellIndex, activeTestName, 'setup')"
                    @clearcode="$emit('clear-unit-test-code', targetCellIndex, activeTestName, 'setup')"
                    @validate="$emit('validate-unit-test-code', targetCellIndex, activeTestName, 'setup')"
                    @dismiss-validation="$emit('dismiss-unit-test-validation', targetCellIndex, activeTestName, 'setup')"
                    @run="$emit('run-unit-test-subcell', targetCellIndex, activeTestName, 'setup')"
                    @interrupt="$emit('interrupt')"
                />

                <!-- Target cell (read-only-ish display) -->
                <cell-label :name="targetCell.metadata.name" />
                <div class="notebook-cell box p-0 mb-5 is-clipped shadow-sm"
                     @click="activeSubCell = 'target'; focusRoot()"
                     :class="{ 'is-active-cell': activeSubCell === 'target' }"
                     style="cursor: pointer">
                    <div class="p-2 has-text-weight-semibold is-size-7 text-muted">
                        Target Cell
                    </div>
                    <div class="p-0 border-bottom">
                        <explanation-editor
                            v-model:source="targetCell.metadata.explanation"
                            :hasCode="(targetCell.source || '').trim().length > 0"
                            :isActive="activeSubCell === 'target'"
                            :isLocked="mainLocked"
                            :running="running"
                            :asRead="false"
                            :codeValid="targetCodeValid"
                            :outputValid="targetOutputValid"
                            :executed="false"
                            :hasError="hasTargetError"
                            :outputVisible="targetOutputVisible"
                            cellMode="target"
                            @save="(content) => $emit('save-explanation', content)"
                            @toggle-output="targetOutputVisible = !targetOutputVisible"
                            @update:editing="targetDescEditing = $event"
                            @run="$emit('run-unit-test-subcell', targetCellIndex, activeTestName, 'target')"
                            @interrupt="$emit('interrupt')"
                            @saveandrun="(content) => { $emit('save-explanation', content); $emit('run-unit-test-subcell', targetCellIndex, activeTestName, 'target'); activeSubCell = 'test'; }"
                            @gencode="$emit('gencode')"
                            @delete=""
                            @moveUp=""
                            @moveDown="" />
                    </div>

                    <validation-cell
                        v-if="targetCell.metadata?.validation && !targetCell.metadata?.validation.is_hidden"
                        :validation="targetCell.metadata.validation"
                        @dismiss_validation="$emit('dismiss-validation')" />

                    <cell-code-bar v-show="activeSubCell === 'target'"
                        v-model:open-panel="targetOpenPanel"
                        :has-explanation="false"
                        :has-code="(targetCell.source || '').trim().length > 0"
                        :can-generate="targetCanGenerate"
                        :code-valid="targetCodeValid"
                        :running="running"
                        :has-error="hasTargetError"
                        :is-locked="mainLocked"
                        :is-test-cell="false"
                        :show-explain="false"
                        :editing="targetDescEditing"
                        @gencode="$emit('gencode')"
                        @clearcode="$emit('clearcode')"
                        @validate="$emit('validate')"
                        @interrupt="$emit('interrupt')" />

                    <code-cell
                        v-model:source="targetCell.source"
                        :execution-count="targetCell.execution_count"
                        :is-active="activeSubCell === 'target'"
                        :is-locked="mainLocked"
                        :codeValid="targetCodeValid"
                        :outputValid="targetOutputValid"
                        :executed="false"
                        :hasError="hasTargetError"
                        :asRead="false"
                        :external-collapse="targetOpenPanel !== 'code'"
                        @save="(content) => $emit('save-code', content)"
                        @saveandrun="(content) => { $emit('save-code', content); $emit('run-unit-test-subcell', targetCellIndex, activeTestName, 'target'); activeSubCell = 'test'; }"
                        @activate="" />

                    <div v-if="targetOutputVisible && targetTestOutputs.length" class="p-2 border-top bg-scheme-main">
                        <output-renderer v-for="(out, oIdx) in targetTestOutputs" :key="oIdx" :output="out" />
                    </div>
                </div>

                <!-- Test sub-cell -->
                <unit-test-sub-cell
                    :cell="activeTest.cells.test"
                    role="test"
                    :is-active="activeSubCell === 'test'"
                    @activate="activeSubCell = 'test'; focusRoot()"
                    :is-locked="isLocked"
                    :running="running"
                    :code-valid="testCodeValid"
                    :output-valid="testOutputValid"
                    @save-explanation="(content) => $emit('save-unit-test-explanation', targetCellIndex, activeTestName, 'test', content)"
                    @save-code="(content) => $emit('save-unit-test-code', targetCellIndex, activeTestName, 'test', content)"
                    @save-and-run="(content) => { $emit('save-unit-test-explanation', targetCellIndex, activeTestName, 'test', content); $emit('run-unit-test-subcell', targetCellIndex, activeTestName, 'test'); }"
                    @save-code-and-run="(content) => { $emit('save-unit-test-code', targetCellIndex, activeTestName, 'test', content); $emit('run-unit-test-subcell', targetCellIndex, activeTestName, 'test'); }"
                    @gencode="$emit('generate-unit-test-code', targetCellIndex, activeTestName, 'test')"
                    @clearcode="$emit('clear-unit-test-code', targetCellIndex, activeTestName, 'test')"
                    @validate="$emit('validate-unit-test-code', targetCellIndex, activeTestName, 'test')"
                    @dismiss-validation="$emit('dismiss-unit-test-validation', targetCellIndex, activeTestName, 'test')"
                    @run="$emit('run-unit-test-subcell', targetCellIndex, activeTestName, 'test')"
                    @interrupt="$emit('interrupt')"
                />
            </div>

            <div v-else class="notification is-warning mt-4">
                No tests yet. Click the "+" button to add one.
            </div>
            </div>

            <!-- Teleported to <body>: .notebook-main is a query container, and
                 container-type makes it the containing block for position:fixed
                 descendants, which would otherwise pin this modal to the notebook
                 column instead of the viewport. -->
            <teleport to="body">
                <unit-test-help-modal :is-active="showHelp" @close="showHelp = false" />
            </teleport>
        </div>
    `
};
