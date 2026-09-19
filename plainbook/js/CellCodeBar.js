import { ref, computed, watch } from './vue.esm-browser.js';

// Reusable "code bar": the show/hide-code (and show/hide-code-explanation) tabs
// plus the code action buttons (Clear / Generate-Fix / Validate / Explain).
// Used by the main code & test cells (NotebookCell) and the unit-test views.
// Owns the transient AI busy-state so the interruptible "Stop" variants work.
export default {
    props: ['openPanel', 'hasExplanation', 'hasCode', 'canGenerate', 'codeValid',
            'running', 'hasError', 'isLocked', 'isTestCell', 'showExplain', 'editing'],
    emits: ['update:openPanel', 'gencode', 'clearcode', 'validate', 'explain', 'interrupt', 'dismiss-error'],
    setup(props, { emit }) {
        const togglePanel = (name) => {
            emit('update:openPanel', props.openPanel === name ? 'none' : name);
        };

        const generating = ref(false);
        const onGenCode = () => {
            generating.value = true;
            // Never an error-fix: on error this button is replaced by the
            // "Fix Code" button in the description toolbar (ExplanationEditor),
            // which is the one that asks the server to amend the description.
            emit('gencode', false);
        };
        const validating = ref(false);
        const onValidate = () => {
            validating.value = true;
            emit('validate');
        };
        const explaining = ref(false);
        const onExplain = () => {
            explaining.value = true;
            emit('explain');
        };
        watch(() => props.running, (val) => {
            if (!val) {
                generating.value = false;
                validating.value = false;
                explaining.value = false;
            }
        });

        const generateLabel = computed(() => props.hasCode ? 'Regenerate' : 'Generate');

        // Pressing a moved button still dismisses the top-level error bar.
        const onButtonPress = (event) => {
            if (event.target.closest('button')) emit('dismiss-error');
        };

        return { togglePanel, generating, onGenCode, validating, onValidate,
            explaining, onExplain, generateLabel, onButtonPress };
    },
    template: /* html */ `
        <div class="code-tabs">
            <button class="button is-ghost panel-tab code-tab"
                    :class="{ 'is-active': openPanel === 'code' }"
                    @click.stop="togglePanel('code')">
                <span class="icon is-small"><i class="bx" :class="openPanel === 'code' ? 'bx-caret-down' : 'bx-caret-right'"></i></span>
                <span>{{ openPanel === 'code' ? 'Hide code' : 'Show code' }}</span>
            </button>
            <template v-if="hasExplanation">
                <div class="panel-divider"></div>
                <button class="button is-ghost panel-tab code-tab"
                        :class="{ 'is-active': openPanel === 'explanation' }"
                        @click.stop="togglePanel('explanation')">
                    <span class="icon is-small"><i class="bx" :class="openPanel === 'explanation' ? 'bx-caret-down' : 'bx-caret-right'"></i></span>
                    <span>{{ openPanel === 'explanation' ? 'Hide explanation' : 'Show explanation' }}</span>
                </button>
            </template>

            <div v-if="!editing" class="code-bar-actions" style="display: flex; flex-wrap: wrap; gap: 0.25rem; align-items: center;"
                 @click.capture="onButtonPress">
                <button class="button is-small"
                        title="Clear code"
                        :disabled="isLocked || !hasCode" @click.stop="$emit('clearcode')">
                    <span class="icon"><i class="bx bx-eraser"></i></span>
                    <span>Clear</span>
                </button>
                <!-- On error/warning there is no Generate button here: the red
                     "Fix Code" button in the description toolbar takes over. -->
                <template v-if="!hasError">
                    <button v-if="generating" class="button is-small"
                            title="Stop code generation" @click.stop="$emit('interrupt')">
                        <span class="icon"><i class="bx bx-stop-circle"></i></span>
                        <span>Stop generating</span>
                    </button>
                    <button v-else class="button is-small"
                            title="Generate or regenerate the code"
                            :disabled="running || isLocked || !canGenerate" @click.stop="onGenCode">
                        <span class="icon"><i class="bx bx-cognition"></i></span>
                        <span>{{ generateLabel }}</span>
                    </button>
                </template>
                <button v-if="validating" class="button is-small"
                        title="Stop validation" @click.stop="$emit('interrupt')">
                    <span class="icon"><i class="bx bx-stop-circle"></i></span>
                    <span>Stop validation</span>
                </button>
                <button v-else :disabled="running || !codeValid" class="button is-small"
                        title="Validate code against description" @click.stop="onValidate">
                    <span class="icon"><i class="bx bx-check"></i></span><span>Validate</span>
                </button>
                <template v-if="showExplain">
                    <button v-if="explaining" class="button is-small"
                            title="Stop explaining" @click.stop="$emit('interrupt')">
                        <span class="icon"><i class="bx bx-stop-circle"></i></span>
                        <span>Stop explaining</span>
                    </button>
                    <button v-else class="button is-small"
                            title="Explain the code in natural language"
                            :disabled="running || isLocked || !hasCode" @click.stop="onExplain">
                        <span class="icon"><i class="bx bx-message-bubble-detail"></i></span>
                        <span>Explain</span>
                    </button>
                </template>
            </div>

            <span style="flex: 1;"></span>
        </div>
    `
};
