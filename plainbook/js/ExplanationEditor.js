import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from './vue.esm-browser.js';
import { createMarkdown } from './markdown.js';

const ExplanationRenderer = {
    props: ['source', 'isActive', 'codeValid', 'outputValid', 'executed', 'hasError',
            'asRead', 'startEditKey', 'isLocked', 'running', 'hasCode', 'outputVisible', 'cellMode',
            'unitTestCount', 'clarifyState', 'foldState', 'hasPrefold'],
    emits: ['update:source', 'save', 'saveandrun', 'update:editing', 'gencode',
            'run', 'interrupt', 'delete', 'moveUp', 'moveDown', 'toggle-output', 'open-test-help',
            'open-unit-test', 'dismiss-error',
            'submit-clarification', 'dismiss-clarification',
            'amend-and-fold', 'accept-amend', 'save-amend', 'dismiss-fold', 'unfold'],
    setup(props, { emit }) {
        const mode = computed(() => props.cellMode || 'normal');
        const isTestCell = computed(() => mode.value === 'test');
        const showRun = computed(() => ['normal', 'test', 'unit_setup', 'target', 'unit_test'].includes(mode.value));
        const showMoveUpDown = computed(() => ['normal', 'test'].includes(mode.value));
        const showDelete = computed(() => ['normal', 'test'].includes(mode.value));
        const showTestHelp = computed(() => mode.value === 'test');
        const showUnitTest = computed(() => mode.value === 'normal');
        const showSaveAndRun = computed(() => ['normal', 'test', 'unit_setup', 'target', 'unit_test'].includes(mode.value));
        const isEditing = ref(false);
        // Let the host hide the code bar's buttons while the description is edited.
        watch(isEditing, (v) => emit('update:editing', v));
        const localSource = ref((Array.isArray(props.source) ? props.source.join('') : props.source) || '');
        const originalSource = ref(localSource.value);
        const md = createMarkdown({ html: true });
        const textareaEl = ref(null);
        const localIsLocked = ref(props.isLocked);


        const rendered = computed(() => md.render(localSource.value));

        const autoResize = () => {
            const el = textareaEl.value;
            if (!el) return;
            el.style.boxSizing = 'border-box';
            el.style.overflow = 'hidden';
            el.style.resize = 'none';
            el.style.height = 'auto';
            el.style.height = `${el.scrollHeight}px`;
        };

        // keep local copy in sync if parent changes
        watch(() => props.source, (val) => {
            localSource.value = (Array.isArray(val) ? val.join('') : val) || '';
            nextTick(autoResize);
        });

        watch(() => props.isActive, (newVal) => {
            if (!newVal && isEditing.value) {
                saveChanges();
            }
            if (newVal && isTestCell.value && !localSource.value.trim()) {
                enterEditMode();
            }
        });

        watch(() => props.isLocked, (newVal) => {
            localIsLocked.value = newVal;
            if (newVal) {
                cancelEdit();
            }
        });

        const enterEditMode = () => {
            originalSource.value = localSource.value;
            isEditing.value = true;
            nextTick(() => {
                autoResize();
                // if (textareaEl.value) textareaEl.value.scrollTop = 0;
            });
        };

        watch(() => props.startEditKey, (newVal) => {
            if (newVal !== undefined) {
                enterEditMode();
                // Force focus after autoResize
                nextTick(() => {
                    if (textareaEl.value) textareaEl.value.focus();
                });
            }
        });

        const saveChanges = () => {
            if (!isEditing.value) return;
            isEditing.value = false;
            emit('save', localSource.value);
        };

        const saveAndRun = () => {
            isEditing.value = false;
            emit('saveandrun', localSource.value);
        };

        // Handler for the flush-edits event: save if currently editing.
        const handleFlushEdits = () => {
            if (isEditing.value) {
                saveChanges();
            }
        };

        // On blur, dispatch the flush event (which this and other editors listen for).
        const onBlur = () => {
            window.dispatchEvent(new Event('plainbook:flush-edits'));
        };

        onMounted(() => {
            window.addEventListener('plainbook:flush-edits', handleFlushEdits);
        });
        onBeforeUnmount(() => {
            window.removeEventListener('plainbook:flush-edits', handleFlushEdits);
        });

        const cancelEdit = () => {
            const originalIsEmpty = !originalSource.value || originalSource.value.trim().length === 0;
            if (originalIsEmpty && !props.hasCode) {
                isEditing.value = false;
                emit('delete');
                return;
            }
            localSource.value = originalSource.value;
            isEditing.value = false;
        };

        const placeholderText = computed(() => {
            if (mode.value === 'unit_setup') return 'Describe how to prepare the data before running the target cell. For help on testing a cell, click on the green info button above.';
            if (mode.value === 'unit_test') return 'Describe what should be checked after the target cell runs.';
            if (isTestCell.value) return 'Describe what should be tested. For help on writing tests, click on the green information button below.';
            return 'Explain what the cell should do...';
        });

        // "Fix Code": shown in place of the code bar's Generate button while the
        // cell is in error. The `true` asks the parent to also amend the
        // description, not just regenerate the code from the current one.
        const generating = ref(false);
        const onGenCode = () => {
            generating.value = true;
            emit('gencode', true);
        };
        watch(() => props.running, (val) => { if (!val) generating.value = false; });

        // Pressing any toolbar or edit-mode button implies the user is acting
        // on the cell, so dismiss the top-level error bar. Use the capture phase
        // so this still fires for buttons that stop click propagation
        // (@click.stop); the closest('button') guard limits it to actual button
        // presses (not clicks on the textarea or empty toolbar space).
        const onButtonPress = (event) => {
            if (event.target.closest('button')) emit('dismiss-error');
        };

        // Grow a textarea to fit its content, keyed off the event target so it
        // works for the dynamically-rendered per-question answer fields.
        const autoGrowField = (e) => {
            const el = e.target;
            el.style.height = 'auto';
            el.style.height = `${el.scrollHeight}px`;
        };

        // Pending clarifying questions from the AI (action cells only), or null.
        const clarify = computed(() =>
            (props.clarifyState && Array.isArray(props.clarifyState.questions)
                && props.clarifyState.questions.length) ? props.clarifyState : null);
        // Answers, reset whenever the question set changes.
        const clarifyAnswers = ref([]);
        watch(clarify, (c) => {
            clarifyAnswers.value = c ? c.questions.map(() => '') : [];
        }, { immediate: true });
        const hasAnyAnswer = computed(() =>
            clarifyAnswers.value.some(a => a && a.trim()));
        const submitClarify = () => {
            if (!hasAnyAnswer.value) return;
            emit('submit-clarification', [...clarifyAnswers.value]);
        };
        const cancelClarify = () => emit('dismiss-clarification');

        // Only action cells get the amend workflow.
        const showFolding = computed(() => mode.value === 'normal');
        const foldReview = computed(() =>
            (props.foldState && props.foldState.status === 'review') ? props.foldState : null);

        const amendText = ref('');
        const foldEdit = ref('');
        const foldEl = ref(null);
        const amendEl = ref(null);
        const isAmending = ref(false);

        watch(foldReview, (fr) => {
            if (fr) {
                foldEdit.value = fr.proposed || '';
                nextTick(() => { if (foldEl.value) { foldEl.value.style.height = 'auto'; foldEl.value.style.height = `${foldEl.value.scrollHeight}px`; } });
            }
        });

        watch(() => props.isActive, (newVal) => {
            if (!newVal) isAmending.value = false;
        });
        watch(() => props.isLocked, (newVal) => {
            if (newVal) isAmending.value = false;
        });

        const startAmend = () => {
            if (localIsLocked.value) return;
            amendText.value = '';
            isAmending.value = true;
            nextTick(() => { if (amendEl.value) amendEl.value.focus(); });
        };
        const cancelAmend = () => {
            isAmending.value = false;
            amendText.value = '';
        };
        const submitAmend = () => {
            const t = amendText.value.trim();
            if (!t) return;
            emit('amend-and-fold', t);
            amendText.value = '';
            isAmending.value = false;
        };
        // Backs the Unfold button, which is commented out in the template below.
        // const onUnfold = () => emit('unfold');
        const acceptFold = () => emit('accept-amend', foldEdit.value);
        const saveFold = () => emit('save-amend', foldEdit.value);
        const dismissFoldReview = () => emit('dismiss-fold');
        const autoResizeFold = (e) => {
            const el = e.target; el.style.height = 'auto'; el.style.height = `${el.scrollHeight}px`;
        };

        return { isEditing, localSource, rendered, enterEditMode, saveChanges,
            cancelEdit, textareaEl, autoResize, saveAndRun, onBlur, localIsLocked,
            isTestCell, onButtonPress, generating, onGenCode,
            mode, showRun, showMoveUpDown, showDelete, showTestHelp, showUnitTest, showSaveAndRun,
            placeholderText, autoGrowField,
            clarify, clarifyAnswers, hasAnyAnswer, submitClarify, cancelClarify,
            showFolding, foldReview, amendText, foldEdit, foldEl, submitAmend,
            amendEl, isAmending, startAmend, cancelAmend,
            /* onUnfold, */ acceptFold, saveFold, dismissFoldReview, autoResizeFold };
    },

    template: /* html */ `
        <div class="explanation-container pt-3 pl-4 pr-4 pb-1">
            <div v-if="!isEditing"
                 class="explanation-body content"
                 v-html="rendered" v-mathjax @dblclick="enterEditMode">
            </div>
        </div>

        <!-- Clarifying questions from the AI (action cells only) -->
        <div v-if="clarify && !isEditing" class="px-4 pb-2">
            <div class="box mt-2 p-3">
                <p class="is-size-7 has-text-weight-semibold mb-2">
                    <span class="icon is-small"><i class="bx bx-help-circle"></i></span>
                    The AI needs a bit more information before writing the code:
                </p>
                <div v-for="(q, qi) in clarify.questions" :key="qi" class="mb-2">
                    <p class="is-size-7 mb-1">{{ qi + 1 }}. {{ q }}</p>
                    <textarea v-model="clarifyAnswers[qi]" class="textarea is-family-monospace" rows="1"
                        placeholder="Your answer..." @input="autoGrowField"></textarea>
                </div>
                <div class="is-flex is-justify-content-flex-end" style="gap:0.5rem;">
                    <button class="button is-small" @click.stop="cancelClarify">Cancel</button>
                    <button class="button is-small is-success"
                            :disabled="running || localIsLocked || !hasAnyAnswer" @click.stop="submitClarify">
                        <span class="icon"><i class="bx bx-merge"></i></span><span>Answer &amp; fold</span>
                    </button>
                </div>
            </div>
        </div>

        <!-- Amend mode -->
        <div v-if="showFolding && !isEditing && isAmending && isActive && hasCode && !foldReview"
             class="explanation-edit-mode px-2 pb-2">
            <textarea ref="amendEl" v-model="amendText" class="textarea is-family-monospace mb-2" rows="2"
                placeholder="Amend this cell, e.g. also drop rows with null revenue."
                @keydown.enter.exact.prevent="submitAmend"></textarea>
            <div style="display: flex; justify-content: flex-end; gap: 0.5rem;">
                <button class="button is-small" @mousedown.prevent @click.stop="cancelAmend">Cancel</button>
                <button class="button is-small is-info"
                        :disabled="!amendText.trim() || running || localIsLocked"
                        @mousedown.prevent @click.stop="submitAmend">
                    <span class="icon"><i class="bx bx-merge"></i></span><span>Fold</span>
                </button>
            </div>
        </div>

        <!-- Fold review -->
        <div v-if="showFolding && !isEditing && foldReview" class="px-4 pb-2">
            <div class="fold-review p-3">
                <p class="is-size-7 has-text-weight-semibold mb-2">
                    <span class="icon is-small"><i class="bx bx-merge"></i></span>
                    Review the amended description. Accepting regenerates the code from it.
                </p>
                <p class="is-size-7 has-text-grey mb-1">Current:</p>
                <!-- This pair is meant to be read against each other, so size and
                     family must match. Both sit at the 0.85rem $control-size that
                     Bulma controls default to here: the textarea gets it from
                     .textarea, and .fold-original is pinned to it in main.scss. -->
                <div class="fold-original is-family-monospace p-2 mb-2">{{ foldReview.original }}</div>
                <p class="is-size-7 has-text-grey mb-1">Amended (editable):</p>
                <textarea ref="foldEl" v-model="foldEdit" class="textarea is-family-monospace mb-2" rows="3" @input="autoResizeFold"></textarea>
                <div class="is-flex is-justify-content-flex-end" style="gap:0.5rem;">
                    <button class="button is-small" @click.stop="dismissFoldReview">Cancel</button>
                    <button class="button is-small is-info" :disabled="!foldEdit.trim()" @click.stop="saveFold">
                        <span>Save</span>
                    </button>
                    <button class="button is-small is-primary" :disabled="!foldEdit.trim()" @click.stop="acceptFold">
                        <span class="icon"><i class="bx bx-play"></i></span><span>Save and Run</span>
                    </button>
                </div>
            </div>
        </div>

        <div v-if="!isEditing && !isAmending && isActive && !foldReview"
                class="explanation-toolbar pl-3 pr-3"
                style="flex-wrap: wrap;"
                @click.capture="onButtonPress">
            <div class="toolbar-left">
                <template v-if="showRun">
                    <button v-if="running" class="button run-button is-small mr-1 is-primary"
                            title="Interrupt execution" @click.stop="$emit('interrupt')">
                        <span class="icon"><i class="bx bx-stop-circle"></i></span>
                        <span>Interrupt</span>
                    </button>
                    <!-- Run, with a "force" addon for code cells: a cell whose
                         output is already up to date is otherwise a no-op, so
                         this is the only way to make it run again. Test cells
                         have no execution skip, so they get no addon. -->
                    <div v-else class="buttons has-addons mb-0 mr-1" style="display: inline-flex;">
                        <button class="button run-button is-small"
                                :class="isTestCell ? 'is-warning' : 'is-primary'"
                                title="Run this cell and all necessary preceding cells (hold Shift to force a re-run)"
                                @click.stop="$emit('run', $event.shiftKey)">
                            <span class="icon"><i class="bx bx-play"></i></span>
                            <span v-if="!isTestCell">Run</span>
                            <span v-else>Run test</span>
                        </button>
                        <button v-if="!isTestCell" class="button run-button is-small is-primary"
                                style="border-left: 1px solid rgba(255, 255, 255, 0.45);
                                       --bulma-control-padding-horizontal: calc(1.1em - 1px);
                                       z-index: 5;"
                                title="Force run: re-execute this cell even if nothing it depends on has changed"
                                @click.stop="$emit('run', true)">
                            <span class="icon" style="width: 1.25em;"><i class="bx bx-refresh-cw"></i></span>
                            <span class="icon" style="width: 1.25em;"><i class="bx bx-play"></i></span>
                            <span>Force Run</span>
                        </button>
                    </div>
                </template>
                <button v-if="showTestHelp" class="button is-success is-small mr-1" title="Test Help" @click.stop="$emit('open-test-help')">
                    <span class="icon"><i class="bx bx-info-circle"></i></span>
                </button>
                <button class="button is-small" style="opacity: 0.6;"
                    title="Toggle output visibility"
                    @click.stop="$emit('toggle-output')">
                    <span class="icon">
                        <i :class="outputVisible ? 'bx bx-eye-slash' : 'bx bx-eye'"></i>
                    </span>
                    <span>Output:&nbsp;</span>
                    <span v-if="!codeValid">Stale</span>
                    <span v-else-if="!outputValid">Stale</span>
                    <span v-else-if="asRead">Unmodified</span>
                    <span v-else>Up to date</span>
                </button>
            </div>
            <div class="toolbar-right" style="display: flex; flex-wrap: wrap; gap: 0.25rem;">
                <template v-if="hasError">
                    <button v-if="generating" class="button is-small is-danger"
                            title="Stop fixing the code" @click.stop="$emit('interrupt')">
                        <span class="icon"><i class="bx bx-stop-circle"></i></span>
                        <span>Stop fixing</span>
                    </button>
                    <button v-else class="button is-small is-danger"
                            title="Fix the code so it runs without errors"
                            :disabled="running || localIsLocked || !localSource.trim()"
                            @click.stop="onGenCode">
                        <span class="icon"><i class="bx bx-cognition"></i></span>
                        <span>Fix Code</span>
                    </button>
                </template>
                <button class="button is-small is-info" title="Edit action description"
                        :disabled="localIsLocked" @click.stop="enterEditMode">
                    <span class="icon"><i class="bx bx-pencil"></i></span><span>Edit</span>
                </button>
                <button v-if="showFolding && hasCode" class="button is-small is-info" title="Amend this cell"
                        :disabled="running || localIsLocked" @click.stop="startAmend">
                    <span class="icon"><i class="bx bx-merge"></i></span><span>Amend</span>
                </button>
                <button v-if="showMoveUpDown" class="button is-small is-info py-1 "
                        :disabled="localIsLocked"
                        title="Move cell up" aria-label="Move Up" @click.stop="$emit('moveUp')">
                    <span class="icon"><i class="bx bx-arrow-up"></i></span>
                </button>
                <button v-if="showMoveUpDown" class="button is-small is-info py-1 "
                        :disabled="localIsLocked"
                        title="Move cell down" aria-label="Move Down" @click.stop="$emit('moveDown')">
                    <span class="icon"><i class="bx bx-arrow-down"></i></span>
                </button>
                <button v-if="showUnitTest" class="button is-small is-warning" title="Unit Test"
                        @click.stop="$emit('open-unit-test')">
                    <span v-if="unitTestCount" class="unit-test-counter mr-1" style="font-weight: 600;">{{ unitTestCount }}</span>
                    <span class="icon"><i class="bx bx-medical-flask"></i></span>
                    <span>Test</span>
                </button>
                <!-- Unfold: hidden by request, never shown. The backing code in
                     setup() is commented out to match; the 'unfold' emit and the
                     hasPrefold prop are kept so the server-side undo and the
                     parent wiring stay intact for whenever it comes back.
                <button v-if="showFolding && hasPrefold" class="button is-small is-link is-light"
                        title="Undo the last amendment, restoring the description and code"
                        :disabled="running || localIsLocked" @click.stop="onUnfold">
                    <span class="icon"><i class="bx bx-expand"></i></span><span>Unfold</span>
                </button>
                -->
                <button v-if="showDelete" class="button is-small is-danger py-1 " title="Delete cell" aria-label="Delete"
                        :disabled="localIsLocked" @click.stop="$emit('delete')">
                    <span class="icon"><i class="bx bx-trash"></i></span>
                </button>
            </div>
        </div>

        <div v-if="isEditing" class="explanation-edit-mode px-2 pb-2"
                @click.capture="onButtonPress">
            <textarea 
                ref="textareaEl"
                v-model="localSource" 
                :placeholder="placeholderText"
                class="textarea is-family-monospace mb-2" 
                rows="1"
                style="overflow: hidden; resize: none; height: 0;"
                @input="autoResize"
                @blur="onBlur"
                @keydown.enter.shift.prevent="saveAndRun">
            </textarea>
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <button v-if="isTestCell" class="button is-success is-small" title="Test Help" @mousedown.prevent @click.stop="$emit('open-test-help')">
                        <span class="icon"><i class="bx bx-info-circle"></i></span>
                    </button>
                </div>
                <div style="display: flex; gap: 0.5rem;">
                <button class="button is-small" @mousedown.prevent @click="cancelEdit">
                    Cancel
                </button>
                <button class="button is-small is-info" :disabled="localIsLocked" @mousedown.prevent @click="saveChanges">
                    Save
                </button>
                <button v-if="showSaveAndRun" class="button is-small" :class="isTestCell ? 'is-warning' : 'is-primary'" :disabled="localIsLocked" @mousedown.prevent @click="saveAndRun">
                    <span class="icon"><i class="bx bx-play"></i></span>
                    <span>Save and Run</span>
                </button>
                </div>
            </div>
        </div>
    `
};

export default ExplanationRenderer;
