import { createApp, ref, computed, onMounted, onBeforeUnmount, nextTick, getCurrentInstance } from './vue.esm-browser.js';
import { mathjaxDirective } from './markdown.js';

import AppNavbar from './AppNavbar.js';
import NotebookCell from './NotebookCell.js';
import CellInsertionZone from './CellInsertionZone.js';
import CellLabel from './CellLabel.js';
import SettingsModal from './SettingsModal.js';
import InfoModal from './InfoModal.js';
import TestHelpModal from './TestHelpModal.js';
import UiError from './UiError.js';
import PanelBar from './PanelBar.js';
import NotebookHelp from './NotebookHelp.js';
import UnitTestView from './UnitTestView.js';
import NotebookTitle from './NotebookTitle.js';
import NotebookFileModal from './NotebookFileModal.js';
import SideIndex from './SideIndex.js';
import AiSetupBanner from './AiSetupBanner.js';
import { outputsHaveStoppingError, getErrorInfo } from './errorUtils.js';
import { serverFetch, isServerDown, SERVER_DOWN_MESSAGE } from './serverFetch.js';

const app = createApp({
    components: { AppNavbar, NotebookCell, CellInsertionZone, CellLabel, SettingsModal, InfoModal, TestHelpModal, UiError, PanelBar, NotebookHelp, UnitTestView, NotebookTitle, NotebookFileModal, SideIndex, AiSetupBanner },
    setup() {
        // Extract token from URL
        const urlParams = new URLSearchParams(window.location.search);
        const authToken = urlParams.get('token');

        // 1. Initialize notebook as null
        const notebook = ref(null);
        const notebook_name = ref('');
        const loading = ref(true);
        const error = ref(null);
        const uiError = ref(null); // Error bar state
        const activeIndex = ref(-1);
        const markdownEditKey = ref({});
        const explanationEditKey = ref({});
        const isLocked = ref(false);
        const shareOutputWithAi = ref(true);
        // When true (Settings), the AI may reply with questions instead of code.
        const askQuestions = ref(false);
        // Questions awaiting answers: clarifyState[index] = { questions: [...] }.
        const clarifyState = ref({});
        // When true (Settings), a cell whose description and inputs are unchanged
        // is left alone instead of being regenerated.
        const skipRegeneration = ref(true);
        // Global "Explain code" options (stored in settings.yaml on the server).
        const explanationDetail = ref(1);      // 1 Brief .. 4 Expert
        const explanationBullets = ref(false);
        const explanationLatex = ref(false);
        // When true (Settings), "Fix Code" also rewrites the cell's description.
        // Global, like the options above; the server decides, this is display only.
        const fixErrorAmendsDescription = ref(true);
        const aiTokens = ref({input: 0, output: 0});
        const verificationStatus = ref('none');
        const debug = ref(false);
        // For running a notebook.
        const running = ref(false);
        const runningActivity = ref({ type: null, cellIndex: null });
        const last_executed_cell_index = ref(-1);
        const last_valid_code_cell_index = ref(-1);
        const last_valid_output_cell_index = ref(-1);
        const asRead = ref(true);
        // Track pending save operations so ui_* functions can wait for them.
        let pendingSaves = [];

        const trackSave = (savePromise) => {
            pendingSaves.push(savePromise);
            const cleanup = () => {
                const idx = pendingSaves.indexOf(savePromise);
                if (idx !== -1) pendingSaves.splice(idx, 1);
            };
            savePromise.then(cleanup, cleanup);
        };

        const waitForPendingSaves = async () => {
            if (pendingSaves.length > 0) {
                await Promise.allSettled([...pendingSaves]);
            }
        };

        // Dispatch flush-edits event so any in-progress editor saves its content.
        // dispatchEvent is synchronous: all listeners complete before this returns,
        // so tracked saves are visible to waitForPendingSaves() immediately after.
        const flushActiveEdits = () => {
            window.dispatchEvent(new Event('plainbook:flush-edits'));
        };

        // For settings modal
        const showSettings = ref(false);
        // TOC sidebar (open by default; toggled via divider triangle)
        const tocOpen = ref(true);
        // API keys are never stored client-side; only presence flags are used.
        const activeAiProvider = ref(null);
        const aiProviderRegistry = ref([]);
        const isCodespace = ref(false);
        const hasGeminiKey = ref(false);
        const hasClaudeKey = ref(false);
        const hasOpenaiKey = ref(false);
        const claudeViaBedrock = ref(false);
        const logEnabled = ref(false);
        const logviewEnabled = ref(false);
        const printAllEnabled = ref(false);
        // True when the server launched the UI as a chromeless window, which has
        // no browser toolbar; the navbar then offers its own Refresh button.
        const chromeless = ref(false);

        const availableAiProviders = computed(() => {
            const apiKeys = {
                'gemini_api_key': hasGeminiKey.value,
                'claude_api_key': hasClaudeKey.value,
                'openai_api_key': hasOpenaiKey.value,
            };
            // A provider without key_setting (the local model) needs no key.
            return aiProviderRegistry.value.filter(p => !p.key_setting || !!apiKeys[p.key_setting]);
        });

        // The Settings modal's local model panel changed the provider list.
        const onProvidersChanged = ({ ai_providers, active_ai_provider }) => {
            aiProviderRegistry.value = ai_providers || [];
            activeAiProvider.value = active_ai_provider;
        };

        // For info modal
        const showInfo = ref(false);

        // For test help modal
        const showTestHelp = ref(false);
        const showNewNotebook = ref(false);
        // Shown in the new-plainbook dialog: where the new file will be created.
        const newNotebookFolder = ref('');
        // The same dialog serves the "+", copy and open buttons: 'new', 'copy'
        // or 'open', with the name it opens prefilled with.
        const notebookModalMode = ref('new');
        const notebookModalDefaultName = ref('');

        // Test cell state
        const last_valid_test_cell_index = ref(-1);

        // Configure global error handler
        const app = getCurrentInstance().appContext.app;

        // Recovers from a failed operation: clears the run state and shows the
        // error. Vue routes errors here only from promises a handler hands back
        // (see onUnhandledRejection below), so any call site that floats a
        // promise must call this itself.
        const reportError = (err) => {
            running.value = false;
            runningActivity.value = { type: null, cellIndex: null };

            const formatError = (e) => {
                const msg = e.message || String(e);
                const stack = e.stack || '';
                return stack.includes(msg) ? stack : `${msg}\n${stack}`;
            };

            let display = formatError(err);
            // Recursively append the stack traces of the causes
            for (let cause = err.cause; cause; cause = cause.cause) {
                display += `\n\nCaused by: ${formatError(cause)}`;
            }
            console.log(display);
            // A dead server can surface under any number of wrapper messages
            // ("Failed to fetch files", "Error in loading notebook", ...); say
            // what actually went wrong instead.
            uiError.value = isServerDown(err) ? SERVER_DOWN_MESSAGE : (err.message || String(err));
            // Scroll to the cell that caused the error, if known.
            // Skip in unit test mode — the cell index refers to the main
            // notebook, and scrollIntoView can shift the page up, moving
            // the navbar and panel bar off-screen.
            if (err.cellIndex != null && unitTestTargetIndex.value === null) {
                nextTick(() => {
                    const cells = document.querySelectorAll('.notebook-cell');
                    if (cells[err.cellIndex]) {
                        cells[err.cellIndex].scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                });
            }
        };

        app.config.errorHandler = (err, instance, info) => {
            console.error("Global error:", err, instance, info);
            reportError(err);
        };

        // Owns the running / runningActivity lifecycle for the ui_* entry points
        // below. Everything that flips `running` on goes through here, so the
        // flag cannot survive a throw: a cell that raises is reported by
        // throwing (see runOneCell), and before this existed the reset was
        // written out by hand after the await and was skipped on that path,
        // leaving the navbar stuck on "Running cell N" with nothing to interrupt.
        // Returns false when it declined because a run is already in flight, so
        // callers can skip their follow-up steps; the body's error propagates.
        const withRunning = async (fn) => {
            if (running.value) return false;
            running.value = true;
            try {
                await fn();
                return true;
            } finally {
                running.value = false;
                runningActivity.value = { type: null, cellIndex: null };
            }
        };

        const updateState = (state) => {
            if (!state) return;
            console.log('Updating state:', state);
            notebook_name.value = state.name;
            last_executed_cell_index.value = state.last_executed_cell;
            last_valid_code_cell_index.value = state.last_valid_code_cell;
            last_valid_output_cell_index.value = state.last_valid_output_cell;
            last_valid_test_cell_index.value = state.last_valid_test_cell;
            isLocked.value = state.is_locked || logviewEnabled.value;
            shareOutputWithAi.value = state.share_output_with_ai;
            if (state.ai_tokens) {
                aiTokens.value = state.ai_tokens;
            }
            verificationStatus.value = state.verification_status || 'none';
            if (notebook.value && notebook.value.metadata) {
                notebook.value.metadata.is_locked = state.is_locked;
            }
        };

        const apiCall = async (url, method = 'GET', body = null) => {
            const options = {
                method,
                headers: { 'Content-Type': 'application/json' }
            };
            if (body) options.body = JSON.stringify(body);

            const separator = url.includes('?') ? '&' : '?';
            const response = await serverFetch(`${url}${separator}token=${authToken}`, options);
            if (!response.ok) throw new Error(`API Error: ${response.statusText}`);

            const r = await response.json();
            if (r.state) updateState(r.state);
            if (r.unit_test_state
                && r.unit_test_state.cell_index === unitTestTargetIndex.value) {
                unitTestValidity.value = r.unit_test_state.state;
            }
            return r;
        };

        // Action logger: emits 'active_cell_change' events to the server when
        // --log is enabled. Sends only when log_enabled is returned by
        // /get_notebook; otherwise all methods are no-ops.
        const ActionLogger = {
            enabled: false,
            activeCell: null,
            init(logEnabled) { this.enabled = !!logEnabled; },
            trackActiveCell(newIdx, newId) {
                if (!this.enabled) return;
                const now = Date.now();
                const prev = this.activeCell;
                if (prev && prev.cellId === newId) return;
                const payload = {
                    op: 'active_cell_change',
                    ts_client: new Date().toISOString(),
                    from_id: prev ? prev.cellId : null,
                    from_index: prev ? prev.cellIndex : null,
                    to_id: newId,
                    to_index: newIdx,
                    duration_on_prev_ms: prev ? now - prev.startTs : null,
                };
                this.activeCell = { cellId: newId, cellIndex: newIdx, startTs: now };
                fetch(`/log_client_event?token=${authToken}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                }).catch(() => { /* best-effort; swallow network errors */ });
            },
        };

        // 2. Define the fetch logic
        const fetchNotebook = async () => {
            try {
                loading.value = true;
                const r = await apiCall('/get_notebook');
                notebook.value = r.nb;
                activeAiProvider.value = r.active_ai_provider || null;
                aiProviderRegistry.value = r.ai_providers || [];
                debug.value = r.debug || false;
                isCodespace.value = r.is_codespace || false;
                hasGeminiKey.value = r.has_gemini_key || false;
                hasClaudeKey.value = r.has_claude_key || false;
                hasOpenaiKey.value = r.has_openai_key || false;
                claudeViaBedrock.value = r.claude_via_bedrock || false;
                if (r.explanation_detail !== undefined) explanationDetail.value = r.explanation_detail;
                explanationBullets.value = !!r.explanation_bullets;
                explanationLatex.value = !!r.explanation_latex;
                if (r.fix_error_amends_description !== undefined) {
                    fixErrorAmendsDescription.value = !!r.fix_error_amends_description;
                }
                askQuestions.value = !!r.ask_questions;
                if (r.skip_regeneration !== undefined) skipRegeneration.value = !!r.skip_regeneration;
                logEnabled.value = !!r.log_enabled;
                logviewEnabled.value = !!r.logview_enabled;
                printAllEnabled.value = !!r.print_all_enabled;
                chromeless.value = !!r.chromeless;
                document.body.classList.toggle('print-all', printAllEnabled.value);
                if (logviewEnabled.value) isLocked.value = true;
                ActionLogger.init(r.log_enabled);
            } catch (err) {
                error.value = isServerDown(err) ? SERVER_DOWN_MESSAGE : err.message;
                throw new Error("Error in loading notebook", { cause: err });
            } finally {
                loading.value = false;
                asRead.value = true;
            }
        };

        const reloadNotebook = async () => {
            // Refetching replaces notebook.value, which resets every cell's local
            // editing state, so let any open editor save first.
            flushActiveEdits();
            await waitForPendingSaves();
            await fetchNotebook();
        }

        const buildIpynb = (srcNb) => {
            const cells = [];
            for (const c of (srcNb && srcNb.cells) || []) {
                if (c.cell_type === 'test') continue;
                if (c.cell_type === 'markdown') {
                    cells.push({
                        cell_type: 'markdown',
                        metadata: {},
                        source: c.source ?? '',
                    });
                    continue;
                }
                if (c.cell_type === 'code') {
                    const explanation = (c.metadata && c.metadata.explanation) || '';
                    if (explanation.trim()) {
                        cells.push({
                            cell_type: 'markdown',
                            metadata: {},
                            source: explanation,
                        });
                    }
                    cells.push({
                        cell_type: 'code',
                        metadata: {},
                        execution_count: c.execution_count ?? null,
                        source: c.source ?? '',
                        outputs: c.outputs || [],
                    });
                }
            }
            const srcMeta = (srcNb && srcNb.metadata) || {};
            const metadata = {
                kernelspec: srcMeta.kernelspec || {
                    display_name: 'Python 3',
                    language: 'python',
                    name: 'python3',
                },
                language_info: srcMeta.language_info || { name: 'python' },
            };
            return {
                cells,
                metadata,
                nbformat: (srcNb && srcNb.nbformat) || 4,
                nbformat_minor: (srcNb && srcNb.nbformat_minor) || 5,
            };
        };

        const downloadIpynb = () => {
            if (!notebook.value) return;
            const ipynb = buildIpynb(notebook.value);
            const json = JSON.stringify(ipynb, null, 1);
            const blob = new Blob([json], { type: 'application/x-ipynb+json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${notebook_name.value || 'notebook'}.ipynb`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        };

        const bumpKey = (dictRef, idx) => {
            dictRef.value = { ...dictRef.value, [idx]: (dictRef.value[idx] || 0) + 1 };
        };

        const clearOutputs = async () => {
            try {
                await apiCall('/clear_outputs', 'POST');
                if (notebook.value) {
                    for (const cell of notebook.value.cells) {
                        if (cell.cell_type === 'code' || cell.cell_type === 'test') {
                            cell.outputs = [];
                            // Also clear unit test sub-cell outputs
                            for (const test of Object.values(cell.metadata?.unit_tests || {})) {
                                test.cells.setup.outputs = [];
                                if (test.cells.target) test.cells.target.outputs = [];
                                test.cells.test.outputs = [];
                            }
                        }
                    }
                }
                console.log('Outputs cleared');
            } catch (err) {
                throw new Error('Failed to clear outputs', { cause: err });
            }
        };

        const sendDebugRequest = async () => {
            try {
                await apiCall('/debug_request', 'POST', { notebook: notebook.value });
                console.log('Debug request sent');
            } catch (err) {
                throw new Error('Debug request error', { cause: err });
            }
        };

        const resetTokens = async () => {
            try {
                await apiCall('/reset_tokens', 'POST');
                aiTokens.value = { input: 0, output: 0 };
            } catch (err) {
                console.error('Failed to reset tokens:', err);
            }
        };

        const sendExplanationToServer = async (content, cellIndex) => {
            asRead.value = false;
            const savePromise = (async () => {
                try {
                    const response = await apiCall('/edit_explanation', 'POST', {
                        cell_index: cellIndex,
                        explanation: content
                    });
                    if (notebook.value && notebook.value.cells[cellIndex]) {
                        notebook.value.cells[cellIndex].metadata.explanation = content;
                        delete notebook.value.cells[cellIndex].metadata.validation;
                        if (response.cell_name) {
                            notebook.value.cells[cellIndex].metadata.name = response.cell_name;
                        }
                    }
                    console.log('Explanation saved:', cellIndex);
                    return response;
                } catch (err) {
                    throw new Error('Failed to save explanation', { cause: err });
                }
            })();
            trackSave(savePromise);
            return savePromise;
        };

        const lockNotebook = async (shouldLock) => {
            try {
                await apiCall('/lock_notebook', 'POST', { is_locked: shouldLock });
                console.log('Notebook locked:', shouldLock);
            } catch (err) {
                throw new Error('Failed to lock notebook', { cause: err });
            }
        };

        const toggleShareOutput = async () => {
            try {
                const newVal = !shareOutputWithAi.value;
                await apiCall('/set_share_output', 'POST', { share: newVal });
            } catch (err) {
                throw new Error('Failed to toggle output sharing', { cause: err });
            }
        };

        // Changing a cell's code invalidates any AI code explanation of it (the
        // server drops it, keyed on the code hash); mirror that in memory so the
        // rendered explanation / its tab disappear immediately.
        const dropCodeExplanation = (cellIndex) => {
            const c = notebook.value && notebook.value.cells[cellIndex];
            if (!c) return;
            delete c.metadata.ai_code_explanation;
            delete c.metadata.ai_code_explanation_timestamp;
            delete c.metadata.code_hash_for_code_explanation;
        };

        const sendCodeToServer = async (content, cellIndex) => {
            asRead.value = false;
            const savePromise = (async () => {
                try {
                    await apiCall('/edit_code', 'POST', {
                        cell_index: cellIndex,
                        source: content
                    });
                    if (notebook.value && notebook.value.cells[cellIndex]) {
                        // Mirror the saved text into the cell, as the markdown
                        // and explanation handlers do for their fields. CodeCell
                        // renders its own localSource and never emits
                        // update:source, so without this the cell we hold keeps
                        // the pre-edit code. Later assignments (a regeneration)
                        // would then be compared against a stale value, and an
                        // update back to that value would look like no change at
                        // all and never reach the screen.
                        notebook.value.cells[cellIndex].source = content;
                        delete notebook.value.cells[cellIndex].metadata.validation;
                        dropCodeExplanation(cellIndex);
                    }
                    console.log('Code saved:', cellIndex);
                } catch (err) {
                    throw new Error('Failed to save code', { cause: err });
                }
            })();
            trackSave(savePromise);
            return savePromise;
        };

        const clearCellCode = async (cellIndex) => {
            asRead.value = false;
            try {
                await apiCall('/clear_code', 'POST', { cell_index: cellIndex });
                if (notebook.value && notebook.value.cells[cellIndex]) {
                    notebook.value.cells[cellIndex].source = '';
                    notebook.value.cells[cellIndex].outputs = [];
                    delete notebook.value.cells[cellIndex].metadata.validation;
                    dropCodeExplanation(cellIndex);
                }
                console.log('Code cleared:', cellIndex);
            } catch (err) {
                throw new Error('Failed to clear code', { cause: err });
            }
        };

        const sendMarkdownToServer = async (content, cellIndex) => {
            asRead.value = false;
            try {
                await apiCall('/edit_markdown', 'POST', { 
                    cell_index: cellIndex, 
                    source: content 
                });
                console.log('Markdown saved:', cellIndex);
                if (notebook.value && notebook.value.cells[cellIndex]) {
                    notebook.value.cells[cellIndex].source = content;
                }
            } catch (err) {
                throw new Error('Failed to save markdown', { cause: err });
            }
        };


        const validateCode = async (cellIndex) => {
            if (!activeAiProvider.value) {
                throw new Error('No AI provider is active. Please set an API key in Settings.');
            };
            asRead.value = false;
            const cell = notebook.value.cells[cellIndex];
            runningActivity.value = { type: 'validating', cellIndex, cellName: cell.metadata.name || null };
            try {
                const r = await apiCall('/validate_code', 'POST', { cell_index: cellIndex });
                if (r.status === 'cancelled') {
                    console.log('Validation cancelled for cell:', cellIndex);
                } else if (r.status === 'error') {
                    throw new Error(r.message || 'Validation failed');
                } else if (notebook.value && notebook.value.cells[cellIndex]) {
                    notebook.value.cells[cellIndex].metadata.validation = r.validation;
                    console.log('Code validation received for cell:', cellIndex, r.validation);
                }
            } catch (err) {
                throw new Error(err.message || 'Failed to validate code', { cause: err });
            }
        };

        const ui_validateCode = async (cellIndex) => {
            await withRunning(() => validateCode(cellIndex));
        };

        const explainCode = async (cellIndex) => {
            if (!activeAiProvider.value) {
                throw new Error('No AI provider is active. Please set an API key in Settings.');
            };
            asRead.value = false;
            const cell = notebook.value.cells[cellIndex];
            runningActivity.value = { type: 'explaining', cellIndex, cellName: cell.metadata.name || null };
            try {
                const r = await apiCall('/explain_code', 'POST', { cell_index: cellIndex });
                if (r.status === 'cancelled') {
                    console.log('Explanation cancelled for cell:', cellIndex);
                } else if (r.status === 'error') {
                    throw new Error(r.message || 'Explanation failed');
                } else if (notebook.value && notebook.value.cells[cellIndex]) {
                    // Stored for the (later) display step; not rendered yet.
                    notebook.value.cells[cellIndex].metadata.ai_code_explanation = r.explanation;
                    console.log('Code explanation received for cell:', cellIndex);
                }
            } catch (err) {
                throw new Error(err.message || 'Failed to explain code', { cause: err });
            }
        };

        const ui_explainCode = async (cellIndex) => {
            await withRunning(() => explainCode(cellIndex));
        };

        const dismissValidation = async (cellIndex) => {
            try {
                await apiCall('/set_validation_visibility', 'POST', { cell_index: cellIndex, is_hidden: true });
                console.log('Validation dismissed:', cellIndex);
                if (notebook.value && notebook.value.cells[cellIndex]) {
                    notebook.value.cells[cellIndex].metadata.validation.is_hidden = true;
                }
            } catch (err) {
                throw new Error('Failed to dismiss validation', { cause: err });
            }
        };

        const validateUnitTestCode = async (cellIndex, testName, role) => {
            if (!activeAiProvider.value) {
                throw new Error('No AI provider is active. Please set an API key in Settings.');
            }
            const cell = notebook.value.cells[cellIndex];
            runningActivity.value = { type: `unit-test-validate-${role}`, cellIndex, testName };
            try {
                const r = await apiCall('/validate_unit_test_code', 'POST', {
                    cell_index: cellIndex, test_name: testName, role: role
                });
                if (r.status === 'cancelled') {
                    console.log('Unit test validation cancelled:', cellIndex, testName, role);
                } else if (r.status === 'error') {
                    throw new Error(r.message || 'Validation failed');
                } else {
                    const test = cell.metadata.unit_tests[testName];
                    test.cells[role].metadata.validation = r.validation;
                    console.log('Unit test validation received:', cellIndex, testName, role, r.validation);
                }
            } catch (err) {
                throw new Error(err.message || 'Failed to validate unit test code', { cause: err });
            }
        };

        const ui_validateUnitTestCode = async (cellIndex, testName, role) => {
            await withRunning(() => validateUnitTestCode(cellIndex, testName, role));
        };

        const dismissUnitTestValidation = async (cellIndex, testName, role) => {
            try {
                await apiCall('/set_unit_test_validation_visibility', 'POST', {
                    cell_index: cellIndex, test_name: testName, role: role, is_hidden: true
                });
                const test = notebook.value.cells[cellIndex].metadata.unit_tests[testName];
                test.cells[role].metadata.validation.is_hidden = true;
                console.log('Unit test validation dismissed:', cellIndex, testName, role);
            } catch (err) {
                throw new Error('Failed to dismiss unit test validation', { cause: err });
            }
        };

        const setActiveCell = (idx, shouldScroll = false) => {
            activeIndex.value = idx;
            const cell = notebook.value && notebook.value.cells && notebook.value.cells[idx];
            const cellId = cell ? cell.id : null;
            if (cellId) ActionLogger.trackActiveCell(idx, cellId);
            if (shouldScroll) {
                nextTick(() => {
                    const cells = document.querySelectorAll('.notebook-cell');
                    if (cells[idx]) {
                        cells[idx].scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                    }
                });
            }
        };

        const insertCell = async (position, cellType) => {
            flushActiveEdits();
            await waitForPendingSaves();
            asRead.value = false;
            try {
                const r = await apiCall('/insert_cell', 'POST', { 
                    cell_type: cellType, 
                    index: position 
                });
                if (r.status !== 'success') throw new Error(r.message || 'Insert failed');
                const { cell, index } = r;
                if (notebook.value) {
                    notebook.value.cells.splice(index, 0, cell);
                    activeIndex.value = index;
                    // Wait for Vue to render the new component before bumping the key
                    nextTick(() => {
                        if (cellType === 'markdown') {
                            bumpKey(markdownEditKey, index);
                        } else { // code or test
                            bumpKey(explanationEditKey, index);
                        }
                    });
                }
            } catch (err) {
                throw new Error('Failed to insert cell', { cause: err });
            }
        };

        const deleteCell = async (cellIndex) => {
            asRead.value = false;
            try {
                const r = await apiCall('/delete_cell', 'POST', { cell_index: cellIndex });
                if (r.status !== 'success') throw new Error(r.message || 'Delete failed');
                if (notebook.value) {
                    notebook.value.cells.splice(cellIndex, 1);
                    // Adjust active index
                    const total = notebook.value.cells.length;
                    if (total === 0) {
                        activeIndex.value = -1;
                    } else if (activeIndex.value >= total) {
                        activeIndex.value = total - 1;
                    }
                }
            } catch (err) {
                throw new Error('Failed to delete cell', { cause: err });
            }
        };

        const moveCell = async (cellIndex, direction) => {
            asRead.value = false;
            const newIndex = cellIndex + direction;
            const total = notebook.value?.cells?.length ?? 0;
            if (newIndex < 0 || newIndex >= total) return;
            try {
                const r = await apiCall('/move_cell', 'POST', { cell_index: cellIndex, new_index: newIndex });
                if (r.status !== 'success') throw new Error(r.message || 'Move failed');
                if (notebook.value) {
                    const [cell] = notebook.value.cells.splice(cellIndex, 1);
                    notebook.value.cells.splice(newIndex, 0, cell);
                    activeIndex.value = newIndex;
                }
            } catch (err) {
                throw new Error('Failed to move cell', { cause: err });
            }
        };

        const isEditingField = (el) => {
            if (!el) return false;
            const tag = el.tagName;
            return el.isContentEditable || tag === 'TEXTAREA' || tag === 'INPUT' || tag === 'SELECT' || tag === 'OPTION';
        };

        
        // Generate code up to the current cell. 
        const generateCode = async (cellIndex) => {
            if (!activeAiProvider.value) {
                throw new Error('No AI provider is active. Please set an API key in Settings.');
            };
            asRead.value = false;
            for (let i = last_valid_code_cell_index.value + 1; i <= cellIndex; i++) {
                if (!running.value) return; // Stop if running has been cancelled
                if (notebook.value.cells[i].cell_type !== 'code') continue; // Skip non-code cells
                await generateCodeOneCell(i);
                // The AI asked the user a question: stop rather than generate
                // later cells on top of a cell whose code is not settled.
                if (clarifyState.value[i]) return;
            }
        };
        
        
        // Function in charge of generating code for one cell.
        const generateCodeOneCell = async (cellIndex, force = false, validationFeedback = null, amend = false) => {
            const cell = notebook.value.cells[cellIndex];
            if (cell.cell_type !== 'code') return; // Only code cells
            if (!force && last_valid_code_cell_index.value >= cellIndex) return; // Already valid code
            // If I don't have valid outputs for the previous cell, I need to run it first.
            // Those outputs are needed as context for code generation.
            if (last_valid_output_cell_index.value < cellIndex - 1 && cellIndex > 0) {
                await runCells(cellIndex - 1);
                // An earlier cell is waiting on the user, and its outputs are
                // context for this one: stop instead of generating without them.
                if (clarificationPending(cellIndex - 1)) return;
            }
            if (!running.value) return; // Stop if running has been cancelled
            runningActivity.value = { type: 'generating', cellIndex, cellName: cell.metadata.name || null };
            asRead.value = false;
            const body = { cell_index: cellIndex };
            // An explicit user action (Regenerate / Fix Code / module rewrite):
            // tell the server to bypass its generation-skip, so the click always
            // calls the AI instead of silently returning the existing source.
            // The run-driven loop above leaves force false and keeps the skip.
            if (force) {
                body.force_regenerate = true;
            }
            if (validationFeedback) {
                body.validation_feedback = validationFeedback;
            }
            // "Fix Code" also asks the server to amend the description.
            if (amend) {
                body.amend_description = true;
            }
            const r = await apiCall('/generate_code', 'POST', body);
            if (r.status == 'success') {
                if (notebook.value && notebook.value.cells[cellIndex]) {
                    cell.source = r.code;
                    // Regenerated code invalidates the old outputs; the server
                    // clears them (plainbook.py generate_code_cell), so mirror
                    // that here. This also drops any prior error output, so a
                    // single "Fix Code" reverts the button to "Regenerate code".
                    // Guarded on the state the response just applied: when the
                    // server took the generation-skip fast path the code did not
                    // change, so it keeps both the output and its validity, and
                    // deleting it here would show an empty cell still labelled
                    // up to date.
                    if (last_valid_output_cell_index.value < cellIndex) {
                        cell.outputs = [];
                    }
                    delete cell.metadata.validation;
                    // A successful generation supersedes any pending questions.
                    dismissClarify(cellIndex);
                    // Regenerated code invalidates any AI code explanation of it.
                    dropCodeExplanation(cellIndex);
                    // The server amended the description (Fix Code only); reflect it.
                    if (r.explanation) {
                        cell.metadata.explanation = r.explanation;
                    }
                    console.log('Code generated for cell:', cellIndex);
                }
            } else if (r.status == 'needs_clarification') {
                // The AI asked questions; show them and leave the source as-is.
                clarifyState.value = { ...clarifyState.value,
                    [cellIndex]: { questions: r.questions || [] } };
                console.log('Clarification requested for cell:', cellIndex, r.questions);
            } else if (r.status == 'cancelled') {
                console.log('Code generation cancelled for cell:', cellIndex);
            } else {
                throw new Error(r.message || 'Code generation failed');
            }
        };


        // Executes cells up to the current cell.
        const runCells = async (cellIndex, force = false) => {
            asRead.value = false;
            // If this cell's output is already valid (e.g. after a Run All),
            // clicking run on it should be a no-op — match the server-side
            // caching condition in plainbook.py execute_cell. A forced run is
            // exactly the case where the user wants it re-run anyway.
            if (!force && cellIndex <= last_valid_output_cell_index.value) {
                return;
            }
            // First, to execute this cell we need to have valid code for it.
            if (last_valid_code_cell_index.value < cellIndex) {
                await generateCode(cellIndex);
                // Code generation stopped to ask the user a question; do not
                // execute anything until the question is answered.
                if (clarificationPending(cellIndex)) return;
            }
            if (last_executed_cell_index.value === cellIndex) {
                // We can be asked to rerun the same cell again.
                await runOneCell(cellIndex, force);
            } else if (last_executed_cell_index.value > cellIndex) {
                // Or, we may have executed further cells, and so be in need of a restart.
                // We need to run from the start up to cellIndex
                await ui_resetKernel();
                await runCells(cellIndex, force);
            } else {
                // We run from the last run cell to the current one. 
                for (let i = last_executed_cell_index.value + 1; i <= cellIndex; i++) {
                    if (!running.value) return; // Stop if running has been cancelled
                    // If the code is not valid, generate it first.
                    if (last_valid_code_cell_index.value < i) {
                        await generateCode(i);
                        if (clarificationPending(i)) return; // Waiting on the user
                    }
                    if (!running.value) return; // Stop if running has been cancelled
                    // Runs this specific cell. Force applies only to the cell the
                    // user asked for: the preceding ones may still be reconstructed
                    // if nothing they depend on changed.
                    await runOneCell(i, force && i === cellIndex);
                }
            }
        };


        // Function in charge of running one cell in the notebook.
        const runOneCell = async (cellIndex, force = false) => {
            if (cellIndex < 0 || cellIndex >= notebook.value.cells.length) return;
            const cell = notebook.value.cells[cellIndex];
            if (cell.cell_type !== 'code') return; // Only run code cells
            if (!running.value) return; // Stop if running has been cancelled
            runningActivity.value = { type: 'running', cellIndex, cellName: cell.metadata.name || null };
            asRead.value = false;
            const body = { cell_index: cellIndex };
            // Force Run: re-execute even when the skip heuristic sees no change.
            if (force) {
                body.force_reexecute = true;
            }
            const r = await apiCall('/execute_cell', 'POST', body);
            if (r.status === 'error') {
                throw new Error(r.message || 'Execution failed');
            }
            cell.outputs = r.outputs;
            console.log('Cell executed:', cellIndex, r.details);
            // The user hit Stop while this request was in flight. The kernel
            // reports its KeyboardInterrupt like any other cell error, so
            // without this check the cancellation they asked for came back at
            // them as "Execution error: KeyboardInterrupt" in the error bar.
            // The traceback is left in the outputs above, which is where a
            // cancelled cell should show it.
            if (!running.value) return;
            // Stop the run when the cell raised (CellExecutionError) or when
            // its output contains a real failure on stderr (an uncaught
            // traceback). A warning printed to stderr -- a pandas
            // DtypeWarning, say -- does not stop the run and does not raise
            // the app-level error bar: the cell ran. It still shows "Fix
            // Code", which is driven by the wider outputsHaveError().
            if (r.details === 'CellExecutionError' || outputsHaveStoppingError(r.outputs)) {
                // Locate the actual error across all outputs (it may follow
                // normal output), rather than assuming outputs[0].
                const info = getErrorInfo(r.outputs) || {};
                let err;
                if (info.ename === 'ModuleNotFoundError') {
                    err = new Error('The code uses the Python module ' + (info.evalue || '').split("'")[1] + ', which is not installed. Use the options shown in the cell output to install it or rewrite the code.');
                } else if (info.ename === 'FileNotFoundError') {
                    err = new Error('The notebook cannot find a file it needs. Please select all the required input files using the selector at the top, so that the AI knows where to find them, and re-generate the code. If the files are already selected, you might want to refer to them in a more precise way, for instance citing their full name.');
                } else {
                    err = new Error("Execution error: " + (info.ename || 'Error') + (info.evalue ? ': ' + info.evalue : ''));
                }
                err.cellIndex = cellIndex;
                throw err;
            }
        };


        // These are the UI functions that cause the "running" to display. 
        // The important fact is that these cannot be re-entrant.

        const ui_saveExplanationAndRun = async (content, cellIndex) => {
            const response = await sendExplanationToServer(content, cellIndex);
            // Defensive: ensure cell name is stored even if a concurrent
            // blur-triggered save consumed the name from a parallel request.
            if (response && response.cell_name
                    && notebook.value && notebook.value.cells[cellIndex]) {
                notebook.value.cells[cellIndex].metadata.name = response.cell_name;
            }
            const ran = await withRunning(async () => {
                await generateCode(cellIndex);
                await runCells(cellIndex);
            });
            // Stay on the cell whose questions the user is answering.
            if (!ran || clarificationPending(cellIndex)) return;
            const total = notebook.value?.cells?.length ?? 0;
            const next = Math.min(cellIndex + 1, total - 1);
            if (next !== cellIndex) setActiveCell(next, true);
        };

        const ui_saveCodeAndRun = async (content, cellIndex) => {
            await sendCodeToServer(content, cellIndex);
            const ran = await withRunning(() => runCells(cellIndex));
            // Stay on the cell whose questions the user is answering.
            if (!ran || clarificationPending(cellIndex)) return;
            const total = notebook.value?.cells?.length ?? 0;
            const next = Math.min(cellIndex + 1, total - 1);
            if (next !== cellIndex) setActiveCell(next, true);
        };

        const ui_saveCodeAndRunTest = async (content, cellIndex) => {
            await sendCodeToServer(content, cellIndex);
            const ran = await withRunning(() => runOneTest(cellIndex));
            if (!ran) return;
            const total = notebook.value?.cells?.length ?? 0;
            const next = Math.min(cellIndex + 1, total - 1);
            if (next !== cellIndex) setActiveCell(next, true);
        };


        const ui_runCell = async (cellIndex, force = false) => {
            flushActiveEdits();
            await waitForPendingSaves();
            await withRunning(() => runCells(cellIndex, force));
        };


        const ui_resetAndRunAllCells = async () => {
            asRead.value = false;
            flushActiveEdits();
            await waitForPendingSaves();
            await withRunning(async () => {
                await ui_resetKernel();
                await runCells(notebook.value.cells.length - 1);
            });
        };


        const ui_verifyNotebook = async () => {
            if (!activeAiProvider.value) {
                uiError.value = 'No AI provider is active. Please set an API key in Settings.';
                return;
            }
            if (running.value) return;
            asRead.value = false;
            flushActiveEdits();
            await waitForPendingSaves();
            await withRunning(async () => {
                // Run the whole notebook first so variables and outputs are fresh.
                await ui_resetKernel();
                try {
                    await runCells(notebook.value.cells.length - 1);
                } catch (err) {
                    // Execution failed -- surface the error and abort verification
                    // so we don't audit a notebook that didn't actually run.
                    uiError.value = (err && err.message)
                        ? `Verification aborted: ${err.message}`
                        : 'Verification aborted: notebook failed to execute.';
                    return;
                }
                if (!running.value) return; // user interrupted
                runningActivity.value = { type: 'verifying' };
                const r = await apiCall('/verify_notebook', 'POST', {});
                if (r.status === 'cancelled') {
                    console.log('Verification cancelled');
                } else if (r.status === 'error') {
                    uiError.value = r.message || 'Verification failed';
                } else if (r.status === 'success') {
                    if (notebook.value && notebook.value.metadata) {
                        notebook.value.metadata.verification = r.verification;
                    }
                }
            });
        };


        const dismissVerification = async () => {
            try {
                await apiCall('/set_verification_visibility', 'POST', { is_hidden: true });
                if (notebook.value && notebook.value.metadata && notebook.value.metadata.verification) {
                    notebook.value.metadata.verification.is_hidden = true;
                }
            } catch (err) {
                throw new Error('Failed to dismiss verification', { cause: err });
            }
        };


        const ui_forceRegenerateCellCode = async (cellIndex, amend = false) => {
            asRead.value = false;
            flushActiveEdits();
            await waitForPendingSaves();
            await withRunning(async () => {
                // Check for failed validation to pass as context
                let validationFeedback = null;
                const cell = notebook.value.cells[cellIndex];
                const v = cell?.metadata?.validation;
                if (v && !v.is_hidden && !v.is_valid && v.message) {
                    validationFeedback = v.message;
                    dismissValidation(cellIndex);
                }
                // amend is true when triggered from the "Fix Code" button: also
                // amend the description so a clean-slate regeneration avoids the error.
                await generateCodeOneCell(cellIndex, true, validationFeedback, amend);
                // "Fix Code" runs the cell as well, so the fix is verified and the
                // output the regeneration discarded is replaced rather than left
                // blank. Plain "Regenerate" from the code bar does not: it leaves a
                // Stale cell for the user to run. Skipped when the AI asked a
                // question (the code is not settled) or the run was interrupted.
                if (amend && running.value && !clarificationPending(cellIndex)) {
                    await runCells(cellIndex);
                }
            });
        };

        const dismissClarify = (cellIndex) => {
            if (!clarifyState.value[cellIndex]) return;
            const next = { ...clarifyState.value };
            delete next[cellIndex];
            clarifyState.value = next;
        };

        // True when a cell at or before cellIndex is waiting on unanswered
        // questions. Such a cell has no code the user approved, so the run must
        // stop there instead of executing stale code or moving past it.
        const clarificationPending = (cellIndex) =>
            Object.keys(clarifyState.value).some((i) => Number(i) <= cellIndex);

        // The answers are handed to the amend -> fold pipeline as guidance, so the
        // AI rewrites the description to incorporate them. The question-and-answer
        // text is prompt input only: it is never stored in the description, and the
        // user reviews the rewritten description before it replaces the old one.
        const ui_submitClarification = async (cellIndex, answers) => {
            if (running.value) return;
            const cs = clarifyState.value[cellIndex];
            if (!cs) return;
            const lines = cs.questions.map((q, i) => {
                const a = (answers[i] || '').trim();
                return a ? `Q: ${q}\nA: ${a}` : null;
            }).filter(Boolean);
            if (!lines.length) return;
            dismissClarify(cellIndex);
            await ui_amendAndFold(cellIndex,
                'Answers to clarifying questions about this cell:\n' + lines.join('\n'));
        };


        // Folds awaiting review: foldState[index] = { status, original, proposed }.
        const foldState = ref({});

        const dismissFold = (cellIndex) => {
            const next = { ...foldState.value };
            delete next[cellIndex];
            foldState.value = next;
        };

        // Nothing is stored until the user accepts the review.
        const ui_amendAndFold = async (cellIndex, text) => {
            if (!text || !text.trim() || running.value) return;
            const cell = notebook.value?.cells?.[cellIndex];
            flushActiveEdits();
            await waitForPendingSaves();
            await withRunning(async () => {
                runningActivity.value = { type: 'folding', cellIndex,
                    cellName: cell?.metadata?.name || null };
                const r = await apiCall('/propose_amend', 'POST', {
                    cell_index: cellIndex, text: text.trim() });
                if (r.status !== 'success') throw new Error(r.message || 'Amend failed');
                const original = Array.isArray(cell.metadata.explanation)
                    ? cell.metadata.explanation.join('')
                    : (cell.metadata.explanation || '');
                foldState.value = { ...foldState.value,
                    [cellIndex]: { status: 'review', original, proposed: r.proposed } };
            });
        };

        // "Save": commit the amended description only (no regeneration/run). The
        // code becomes stale until the cell is regenerated.
        const ui_saveAmend = async (cellIndex, editedText) => {
            if (running.value) return;
            const r = await apiCall('/commit_amend', 'POST', {
                cell_index: cellIndex, explanation: editedText });
            if (r.status !== 'success') throw new Error(r.message || 'Commit failed');
            const cell = notebook.value?.cells?.[cellIndex];
            if (cell) {
                cell.metadata.explanation = editedText;
                // Marker so Unfold appears; the snapshot itself is server-side.
                cell.metadata.explanation_prefold = { committed: true };
            }
            dismissFold(cellIndex);
            asRead.value = false;
        };

        // "Save and Run": commit, then regenerate through the normal pipeline and
        // run, so the stored code is always code this explanation produced.
        const ui_acceptAmend = async (cellIndex, editedText) => {
            if (running.value) return;
            await ui_saveAmend(cellIndex, editedText);
            await withRunning(async () => {
                await generateCodeOneCell(cellIndex, true, null);
                await runCells(cellIndex);
            });
        };

        // Restores a pair that already ran together, so it needs no AI call.
        const ui_unfold = async (cellIndex) => {
            if (running.value) return;
            const r = await apiCall('/unfold', 'POST', { cell_index: cellIndex });
            if (r.status !== 'success') return;
            const cell = notebook.value?.cells?.[cellIndex];
            if (cell) {
                cell.metadata.explanation = r.explanation;
                delete cell.metadata.explanation_prefold;
                if (r.source !== null) cell.source = r.source;
            }
            asRead.value = false;
            await withRunning(async () => {
                // A legacy snapshot carries no code, so it must be regenerated.
                if (r.source === null) await generateCodeOneCell(cellIndex, true, null);
                await runCells(cellIndex);
            });
        };

        // Missing-module installation state, keyed by cell index:
        // undefined | { status: 'installing' } | { status: 'done', success, output }.
        // Displayed by the MissingModuleBar of the corresponding cell.
        const moduleInstall = ref({});

        const ui_installModule = async (cellIndex, moduleName) => {
            await withRunning(async () => {
                runningActivity.value = { type: 'installing', cellIndex, moduleName };
                moduleInstall.value = { ...moduleInstall.value, [cellIndex]: { status: 'installing' } };
                try {
                    const r = await apiCall('/install_package', 'POST', { module: moduleName });
                    if (r.status === 'error') throw new Error(r.message || 'Package installation failed');
                    moduleInstall.value = { ...moduleInstall.value,
                        [cellIndex]: { status: 'done', success: !!r.success, output: r.output || '' } };
                    console.log('Package installed for module:', moduleName, 'success:', r.success);
                } catch (err) {
                    // Back to the question state; the error bar reports the failure.
                    dismissModuleInstall(cellIndex);
                    throw new Error('Failed to install package for module ' + moduleName, { cause: err });
                }
            });
        };

        const dismissModuleInstall = (cellIndex) => {
            const next = { ...moduleInstall.value };
            delete next[cellIndex];
            moduleInstall.value = next;
        };

        const ui_interruptKernel = async () => {
            try {
                running.value = false;
                runningActivity.value = { type: null, cellIndex: null };
                await Promise.all([
                    apiCall('/interrupt_kernel', 'POST'),
                    apiCall('/cancel_ai_request', 'POST'),
                ]);
                console.log('Kernel interrupted');
            } catch (err) {
                throw new Error('Interrupt error', { cause: err });
            }
        };


        const ui_resetKernel = async () => {
            try {
                await apiCall('/reset_kernel', 'POST');
                console.log('Kernel reset');
            } catch (err) {
                throw new Error('Reset error', { cause: err });
            }
        };

        const restarting = ref(false);

        const ui_restart = async () => {
            restarting.value = true;
            try {
                await ui_resetKernel();
                await reloadNotebook();
            } finally {
                restarting.value = false;
            }
        };


        // Test cell functions

        const generateTestCodeOneCell = async (cellIndex, force = false, validationFeedback = null) => {
            const cell = notebook.value.cells[cellIndex];
            if (cell.cell_type !== 'test') return;
            if (!force && last_valid_test_cell_index.value >= cellIndex) return;
            if (!running.value) return;
            runningActivity.value = { type: 'generating', cellIndex, cellName: cell.metadata.name || null };
            asRead.value = false;
            const body = { cell_index: cellIndex };
            if (validationFeedback) {
                body.validation_feedback = validationFeedback;
            }
            const r = await apiCall('/generate_test_code', 'POST', body);
            if (r.status === 'success') {
                if (notebook.value && notebook.value.cells[cellIndex]) {
                    cell.source = r.code;
                    delete cell.metadata.validation;
                    console.log('Test code generated for cell:', cellIndex);
                }
            } else if (r.status === 'cancelled') {
                console.log('Test code generation cancelled for cell:', cellIndex);
            } else {
                throw new Error(r.message || 'Test code generation failed');
            }
        };

        const runOneTest = async (cellIndex) => {
            if (cellIndex < 0 || cellIndex >= notebook.value.cells.length) return;
            const cell = notebook.value.cells[cellIndex];
            if (cell.cell_type !== 'test') return;
            if (!running.value) return;
            // Ensure all previous code cells have valid code and output.
            // Find the last code cell before this test.
            let lastCodeIdx = -1;
            for (let i = cellIndex - 1; i >= 0; i--) {
                if (notebook.value.cells[i].cell_type === 'code') {
                    lastCodeIdx = i;
                    break;
                }
            }
            if (lastCodeIdx >= 0 && last_valid_output_cell_index.value < lastCodeIdx) {
                await runCells(lastCodeIdx);
            }
            if (!running.value) return;
            // Generate test code if needed
            if (last_valid_test_cell_index.value < cellIndex) {
                await generateTestCodeOneCell(cellIndex);
            }
            if (!running.value) return;
            // Execute the test cell
            runningActivity.value = { type: 'running', cellIndex, cellName: cell.metadata.name || null };
            asRead.value = false;
            const r = await apiCall('/execute_test_cell', 'POST', { cell_index: cellIndex });
            // Assigned before anything below can throw: a test that fails is
            // exactly the case whose output the user needs to see, and leaving
            // it unassigned left the cell showing the run before this one.
            if (r.outputs) {
                cell.outputs = r.outputs;
            }
            if (r.status === 'error') {
                const err = new Error(r.message || 'Test execution failed');
                err.cellIndex = cellIndex;
                throw err;
            }
            console.log('Test cell executed:', cellIndex, r.details);
            if (!running.value) return; // interrupted; see runOneCell
            // A test cell that raised: report it the way a code cell is
            // reported, with the error type the server sent rather than a
            // flattened message.
            if (r.details === 'CellExecutionError' || outputsHaveStoppingError(r.outputs)) {
                const info = getErrorInfo(r.outputs) || {};
                const err = new Error("Test failed: " + (info.ename || 'Error')
                    + (info.evalue ? ': ' + info.evalue : ''));
                err.cellIndex = cellIndex;
                throw err;
            }
        };

        const ui_runTestCell = async (cellIndex) => {
            flushActiveEdits();
            await waitForPendingSaves();
            await withRunning(() => runOneTest(cellIndex));
        };

        const ui_runAllTests = async () => {
            flushActiveEdits();
            await waitForPendingSaves();
            await withRunning(async () => {
                for (let i = 0; i < notebook.value.cells.length; i++) {
                    if (!running.value) break;
                    if (notebook.value.cells[i].cell_type === 'test') {
                        await runOneTest(i);
                    }
                }
            });
        };

        const ui_saveExplanationAndRunTest = async (content, cellIndex) => {
            const response = await sendExplanationToServer(content, cellIndex);
            if (response && response.cell_name
                    && notebook.value && notebook.value.cells[cellIndex]) {
                notebook.value.cells[cellIndex].metadata.name = response.cell_name;
            }
            const ran = await withRunning(async () => {
                await generateTestCodeOneCell(cellIndex);
                await runOneTest(cellIndex);
            });
            if (!ran) return;
            const total = notebook.value?.cells?.length ?? 0;
            const next = Math.min(cellIndex + 1, total - 1);
            if (next !== cellIndex) setActiveCell(next, true);
        };

        const ui_forceRegenerateTestCode = async (cellIndex) => {
            asRead.value = false;
            flushActiveEdits();
            await waitForPendingSaves();
            await withRunning(async () => {
                let validationFeedback = null;
                const cell = notebook.value.cells[cellIndex];
                const v = cell?.metadata?.validation;
                if (v && !v.is_hidden && !v.is_valid && v.message) {
                    validationFeedback = v.message;
                    dismissValidation(cellIndex);
                }
                await generateTestCodeOneCell(cellIndex, true, validationFeedback);
            });
        };

        // Unit test mode state and methods

        const unitTestTargetIndex = ref(null);
        const unitTestActiveSubcell = ref('setup');
        const unitTestActiveTestName = ref(null);
        const unitTestValidity = ref({});

        function newSubCell() {
            return {
                cell_type: "code",
                source: "",
                outputs: [],
                execution_count: null,
                id: crypto.randomUUID(),
                metadata: {
                    explanation: "",
                    explanation_timestamp: "",
                    code_timestamp: "",
                    name: "",
                    variables: {},
                    validation: null
                }
            };
        }

        const fetchUnitTestState = async (cellIndex) => {
            try {
                const r = await apiCall('/get_unit_test_state', 'POST', { cell_index: cellIndex });
                if (r.status === 'success' && r.unit_test_state
                    && r.unit_test_state.cell_index === cellIndex) {
                    unitTestValidity.value = r.unit_test_state.state;
                }
            } catch (err) {
                console.error('Failed to fetch unit test state:', err);
            }
        };

        const enterUnitTestMode = async (cellIndex) => {
            const cell = notebook.value.cells[cellIndex];
            if (!cell.metadata.unit_tests || Object.keys(cell.metadata.unit_tests).length === 0) {
                cell.metadata.unit_tests = {
                    "Test 1": { cells: { setup: newSubCell(), test: newSubCell() }, validity: { setup_code_valid: false, setup_output_valid: false, target_output_valid: false, test_code_valid: false, test_output_valid: false } }
                };
                saveUnitTests(cellIndex);
            }
            unitTestTargetIndex.value = cellIndex;
            await fetchUnitTestState(cellIndex);
        };

        const exitUnitTestMode = () => {
            unitTestTargetIndex.value = null;
            unitTestValidity.value = {};
        };

        const saveUnitTests = async (cellIndex) => {
            const cell = notebook.value.cells[cellIndex];
            try {
                await apiCall('/save_unit_tests', 'POST', {
                    cell_index: cellIndex,
                    unit_tests: cell.metadata.unit_tests
                });
                console.log('Unit tests saved:', cellIndex);
            } catch (err) {
                throw new Error('Failed to save unit tests', { cause: err });
            }
        };

        const addUnitTest = async (cellIndex) => {
            const cell = notebook.value.cells[cellIndex];
            if (!cell.metadata.unit_tests) cell.metadata.unit_tests = {};
            let testNum = Object.keys(cell.metadata.unit_tests).length + 1;
            while (`Test ${testNum}` in cell.metadata.unit_tests) testNum++;
            cell.metadata.unit_tests[`Test ${testNum}`] = {
                cells: { setup: newSubCell(), test: newSubCell() },
                validity: { setup_code_valid: false, setup_output_valid: false, target_output_valid: false, test_code_valid: false, test_output_valid: false }
            };
            await saveUnitTests(cellIndex);
        };

        const deleteUnitTest = async (cellIndex, testName) => {
            const cell = notebook.value.cells[cellIndex];
            if (!cell.metadata.unit_tests) return;
            delete cell.metadata.unit_tests[testName];
            await saveUnitTests(cellIndex);
        };

        const renameUnitTest = async (cellIndex, oldName, newName) => {
            const cell = notebook.value.cells[cellIndex];
            if (!cell.metadata.unit_tests || !(oldName in cell.metadata.unit_tests)) return;
            if (newName in cell.metadata.unit_tests) return;
            const newTests = {};
            for (const [key, value] of Object.entries(cell.metadata.unit_tests)) {
                newTests[key === oldName ? newName : key] = value;
            }
            cell.metadata.unit_tests = newTests;
            await saveUnitTests(cellIndex);
        };

        const saveUnitTestExplanation = (cellIndex, testName, role, content) => {
            // Update local data immediately so executeUnitTest sees current explanation
            const cell = notebook.value.cells[cellIndex];
            const test = cell.metadata.unit_tests[testName];
            test.cells[role].metadata.explanation = content;

            const savePromise = (async () => {
                try {
                    await apiCall('/save_unit_test_explanation', 'POST', {
                        cell_index: cellIndex,
                        test_name: testName,
                        role: role,
                        explanation: content
                    });
                } catch (err) {
                    throw new Error('Failed to save unit test explanation', { cause: err });
                }
            })();
            trackSave(savePromise);
            return savePromise;
        };

        const saveUnitTestCode = (cellIndex, testName, role, content) => {
            const savePromise = (async () => {
                try {
                    await apiCall('/save_unit_test_code', 'POST', {
                        cell_index: cellIndex,
                        test_name: testName,
                        role: role,
                        source: content
                    });
                    // Keep the sub-cell we hold in step with what was saved, for
                    // the same reason as sendCodeToServer above.
                    const subCell = notebook.value?.cells[cellIndex]
                        ?.metadata?.unit_tests?.[testName]?.cells?.[role];
                    if (subCell) subCell.source = content;
                } catch (err) {
                    throw new Error('Failed to save unit test code', { cause: err });
                }
            })();
            trackSave(savePromise);
            return savePromise;
        };

        const clearUnitTestCode = async (cellIndex, testName, role) => {
            try {
                await apiCall('/clear_unit_test_code', 'POST', {
                    cell_index: cellIndex,
                    test_name: testName,
                    role: role
                });
                // Update local state
                const cell = notebook.value.cells[cellIndex];
                const test = cell.metadata.unit_tests[testName];
                const subCell = test.cells[role];
                subCell.source = '';
                subCell.outputs = [];
            } catch (err) {
                throw new Error('Failed to clear unit test code', { cause: err });
            }
        };

        const clearUnitTestOutputs = async (cellIndex, testName) => {
            try {
                await apiCall('/clear_unit_test_outputs', 'POST', {
                    cell_index: cellIndex,
                    test_name: testName
                });
            } catch (err) {
                throw new Error('Failed to clear unit test outputs', { cause: err });
            }
        };

        const executeUnitTestCell = async (cellIndex, testName, role) => {
            runningActivity.value = { type: `unit-test-${role}`, cellIndex, testName };
            const r = await apiCall('/run_unit_test_cell', 'POST', {
                cell_index: cellIndex,
                test_name: testName,
                role: role
            });
            // Update local outputs
            const cell = notebook.value.cells[cellIndex];
            const test = cell.metadata.unit_tests[testName];
            if (role === 'setup') {
                test.cells.setup.outputs = r.outputs || [];
            } else if (role === 'target') {
                if (!test.cells.target) test.cells.target = {};
                test.cells.target.outputs = r.outputs || [];
            } else {
                test.cells.test.outputs = r.outputs || [];
            }
            if (r.details === 'CellExecutionError') {
                const err = new Error(`Unit test ${role} execution error`);
                err.cellIndex = cellIndex;
                throw err;
            }
            return r;
        };

        const generateUnitTestCodeInner = async (cellIndex, testName, role) => {
            runningActivity.value = { type: `unit-test-gen-${role}`, cellIndex, testName };
            const r = await apiCall('/generate_unit_test_cell_code', 'POST', {
                cell_index: cellIndex,
                test_name: testName,
                role: role
            });
            if (r.status === 'success' && r.code) {
                const cell = notebook.value.cells[cellIndex];
                const test = cell.metadata.unit_tests[testName];
                if (role === 'target') {
                    cell.source = r.code;
                } else {
                    test.cells[role].source = r.code;
                }
            } else if (r.status === 'error') {
                throw new Error(r.message || 'Failed to generate unit test code');
            }
            return r;
        };

        // Ensure prerequisites for any unit test sub-cell execution:
        // main notebook cells executed, target cell code generated.
        const ensureUnitTestPrereqs = async (cellIndex) => {
            if (cellIndex > 0 && last_executed_cell_index.value < cellIndex - 1) {
                await runCells(cellIndex - 1);
            }
            if (!running.value) return;
            if (last_valid_code_cell_index.value < cellIndex) {
                await generateCode(cellIndex);
            }
        };

        // Generate setup code if needed and execute setup.
        const runUnitTestSetup = async (cellIndex, testName) => {
            const cell = notebook.value.cells[cellIndex];
            const test = cell.metadata.unit_tests[testName];
            const validity = unitTestValidity.value?.[testName];
            const setupHasExplanation = (test.cells.setup.metadata?.explanation || '').trim();
            const setupCodeInvalid = !validity?.setup?.code_valid;
            if (setupHasExplanation && (!(test.cells.setup.source || '').trim() || setupCodeInvalid)) {
                await generateUnitTestCodeInner(cellIndex, testName, 'setup');
            }
            if (!running.value) return;
            await executeUnitTestCell(cellIndex, testName, 'setup');
        };

        // Run setup if needed, then execute target.
        const runUnitTestTarget = async (cellIndex, testName) => {
            const validity = unitTestValidity.value?.[testName];
            if (!validity?.setup?.output_valid) {
                await runUnitTestSetup(cellIndex, testName);
            }
            if (!running.value) return;
            await executeUnitTestCell(cellIndex, testName, 'target');
        };

        // Run setup + target if needed, then generate test code if needed and execute test.
        const runUnitTestTest = async (cellIndex, testName) => {
            const validity = unitTestValidity.value?.[testName];
            if (!validity?.target?.output_valid) {
                await runUnitTestTarget(cellIndex, testName);
            }
            if (!running.value) return;
            const cell = notebook.value.cells[cellIndex];
            const test = cell.metadata.unit_tests[testName];
            const testHasExplanation = (test.cells.test.metadata?.explanation || '').trim();
            const testCodeInvalid = !validity?.test?.code_valid;
            if (testHasExplanation && (!(test.cells.test.source || '').trim() || testCodeInvalid)) {
                await generateUnitTestCodeInner(cellIndex, testName, 'test');
            }
            if (!running.value) return;
            if ((test.cells.test.source || '').trim()) {
                await executeUnitTestCell(cellIndex, testName, 'test');
            }
        };

        const executeUnitTest = async (cellIndex, testName) => {
            // Full run: prerequisites, then setup, target, test.
            await ensureUnitTestPrereqs(cellIndex);
            if (!running.value) return;
            await runUnitTestSetup(cellIndex, testName);
            if (!running.value) return;
            await executeUnitTestCell(cellIndex, testName, 'target');
            if (!running.value) return;
            const cell = notebook.value.cells[cellIndex];
            const test = cell.metadata.unit_tests[testName];
            const validity = unitTestValidity.value?.[testName];
            const testHasExplanation = (test.cells.test.metadata?.explanation || '').trim();
            const testCodeInvalid = !validity?.test?.code_valid;
            if (testHasExplanation && (!(test.cells.test.source || '').trim() || testCodeInvalid)) {
                await generateUnitTestCodeInner(cellIndex, testName, 'test');
            }
            if (!running.value) return;
            if ((test.cells.test.source || '').trim()) {
                await executeUnitTestCell(cellIndex, testName, 'test');
            }
        };

        const ui_runUnitTest = async (cellIndex, testName) => {
            flushActiveEdits();
            await waitForPendingSaves();
            await withRunning(() => executeUnitTest(cellIndex, testName));
        };

        const ui_runUnitTestSubcell = async (cellIndex, testName, role) => {
            flushActiveEdits();
            await waitForPendingSaves();
            await withRunning(async () => {
                await ensureUnitTestPrereqs(cellIndex);
                if (!running.value) return;
                if (role === 'setup') {
                    await runUnitTestSetup(cellIndex, testName);
                } else if (role === 'target') {
                    await runUnitTestTarget(cellIndex, testName);
                } else if (role === 'test') {
                    await runUnitTestTest(cellIndex, testName);
                }
            });
        };

        const generateUnitTestCode = async (cellIndex, testName, role) => {
            await withRunning(() => generateUnitTestCodeInner(cellIndex, testName, role));
        };

        const handleKeydown = (e) => {
            const total = notebook.value?.cells?.length ?? 0;
            if (total === 0) return;

            if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
                if (isEditingField(e.target)) return;
                e.preventDefault();
                const delta = e.key === 'ArrowDown' ? 1 : -1;
                const current = activeIndex.value < 0 ? 0 : activeIndex.value;
                const next = Math.min(Math.max(current + delta, 0), total - 1);
                if (next !== activeIndex.value) setActiveCell(next, true);
                return;
            }

            if (e.key === 'Enter' && e.shiftKey) {
                if (isEditingField(e.target)) return;
                if (!notebook.value) return;
                if (unitTestTargetIndex.value !== null) {
                    // Unit test mode: run the active sub-cell and advance.
                    // Note: activeIndex is unrelated here — the open-unit-test
                    // button uses @click.stop, so entering unit-test mode does
                    // not necessarily set activeIndex. Drive off the unit-test
                    // state instead.
                    const testName = unitTestActiveTestName.value;
                    if (!testName) return;
                    e.preventDefault();
                    ui_runUnitTestSubcell(unitTestTargetIndex.value, testName, unitTestActiveSubcell.value)
                        .catch(reportError);
                    if (unitTestActiveSubcell.value === 'setup') unitTestActiveSubcell.value = 'target';
                    else if (unitTestActiveSubcell.value === 'target') unitTestActiveSubcell.value = 'test';
                } else {
                    if (activeIndex.value < 0) return;
                    e.preventDefault();
                    const cell = notebook.value.cells[activeIndex.value];
                    if (cell && (cell.cell_type === 'code' || cell.cell_type === 'test')) {
                        ui_runCell(activeIndex.value).catch(reportError);
                    }
                    const next = Math.min(activeIndex.value + 1, total - 1);
                    if (next !== activeIndex.value) setActiveCell(next);
                }
            }
        };

        const saveSettings = async (keys) => {
            // Save the API keys to the server
            try {
                const r = await apiCall('/set_key', 'POST', {
                    gemini_api_key: keys.gemini_api_key,
                    claude_api_key: keys.claude_api_key,
                    openai_api_key: keys.openai_api_key,
                });
                console.log('API keys saved successfully');
                if (r.active_ai_provider !== undefined) {
                    activeAiProvider.value = r.active_ai_provider;
                }
                // Update presence flags from server response
                if (r.has_gemini_key !== undefined) {
                    hasGeminiKey.value = r.has_gemini_key;
                }
                if (r.has_claude_key !== undefined) {
                    hasClaudeKey.value = r.has_claude_key;
                }
                if (r.has_openai_key !== undefined) {
                    hasOpenaiKey.value = r.has_openai_key;
                }
                if (r.claude_via_bedrock !== undefined) {
                    claudeViaBedrock.value = r.claude_via_bedrock;
                }
                // The server rebuilds the model list from the new keys.
                if (r.ai_providers !== undefined) {
                    aiProviderRegistry.value = r.ai_providers;
                }
            } catch (err) {
                throw new Error('Error saving API keys', { cause: err });
            }
            // Save the code-generation settings (independent of API keys).
            if (keys.ask_questions !== undefined) {
                try {
                    const r = await apiCall('/set_ask_questions', 'POST', { value: keys.ask_questions });
                    if (r.ask_questions !== undefined) askQuestions.value = r.ask_questions;
                } catch (err) {
                    throw new Error('Error saving code generation setting', { cause: err });
                }
            }
            if (keys.skip_regeneration !== undefined) {
                try {
                    const r = await apiCall('/set_skip_regeneration', 'POST', { value: keys.skip_regeneration });
                    if (r.skip_regeneration !== undefined) skipRegeneration.value = r.skip_regeneration;
                } catch (err) {
                    throw new Error('Error saving the regeneration setting', { cause: err });
                }
            }
            // Save the global "Explain code" options.
            if (keys.explanation_detail !== undefined) {
                try {
                    const r = await apiCall('/set_explain_options', 'POST', {
                        detail: keys.explanation_detail,
                        bullets: keys.explanation_bullets,
                        latex: keys.explanation_latex,
                    });
                    if (r.explanation_detail !== undefined) explanationDetail.value = r.explanation_detail;
                    if (r.explanation_bullets !== undefined) explanationBullets.value = r.explanation_bullets;
                    if (r.explanation_latex !== undefined) explanationLatex.value = r.explanation_latex;
                } catch (err) {
                    throw new Error('Error saving explanation options', { cause: err });
                }
            }
            // Save the "Fix errors also amends the description" setting.
            if (keys.fix_error_amends_description !== undefined) {
                try {
                    const r = await apiCall('/set_fix_error_amends_description', 'POST',
                        { value: keys.fix_error_amends_description });
                    if (r.fix_error_amends_description !== undefined) {
                        fixErrorAmendsDescription.value = r.fix_error_amends_description;
                    }
                } catch (err) {
                    throw new Error('Error saving the description-amendment setting', { cause: err });
                }
            }
        };

        const setActiveAiProvider = async (providerId) => {
            try {
                const r = await apiCall('/set_active_ai', 'POST', { provider: providerId });
                if (r.status === 'success') {
                    activeAiProvider.value = r.active_ai_provider;
                } else {
                    throw new Error(r.message || 'Failed to set AI provider');
                }
            } catch (err) {
                throw new Error('Error setting AI provider', { cause: err });
            }
        };

        const genError = () => {
            throw new Error('This is a generated error for testing purposes. This is a generated error for testing purposes. This is a generated error for testing purposes. This is a generated error for testing purposes. ');
        }

        const closeUiError = () => {
            uiError.value = null;
        };

        // Rename the notebook: the server saves a copy under the new name and
        // switches all future saves to it. On success the @stateful response
        // carries the new name, which updateState() applies to notebook_name.
        const renameNotebook = async (newName) => {
            if (!newName) return;
            try {
                const r = await apiCall('/rename_notebook', 'POST', { name: newName });
                if (r.status === 'error') {
                    uiError.value = r.message || 'Could not rename the notebook.';
                }
            } catch (err) {
                uiError.value = (err && err.message) || 'Could not rename the notebook.';
            }
        };

        // Open the plainbook dialog in the given mode, showing where the file
        // will land. The folder is only for the help line, so a failure to get
        // it does not stop the dialog.
        const openNotebookDialog = async (mode, defaultName) => {
            notebookModalMode.value = mode;
            notebookModalDefaultName.value = defaultName;
            newNotebookFolder.value = '';
            showNewNotebook.value = true;
            try {
                const r = await apiCall('/current_dir');
                newNotebookFolder.value = r.path || '';
            } catch (err) {
                console.warn('Could not determine the notebook folder:', err);
            }
        };

        const openNewNotebook = () => openNotebookDialog('new', '');

        // Opening picks a file rather than naming one, so there is no name to
        // suggest.
        const openExistingNotebook = () => openNotebookDialog('open', '');

        // Copying suggests <name>_copy; the dialog preselects it, so typing
        // replaces it.
        const openCopyNotebook = () =>
            openNotebookDialog('copy', (notebook_name.value || 'notebook') + '_copy');

        // Create a new plainbook, copy this one, or open an existing one. In
        // every case the server launches it as its own process, so it appears
        // in a new window with its own kernel; nothing changes here.
        //
        // `path` is set when the dialog knows it is dealing with a file that
        // already exists -- an explicit pick in open mode, or a name in new
        // mode that turned out to be taken -- and then the request is an open,
        // whichever button was pressed.
        const submitNotebookDialog = async ({ mode, name, folder, path }) => {
            const isCopy = mode === 'copy';
            const isOpen = mode === 'open' || !!path;
            const failure = isOpen ? 'Could not open the plainbook.'
                : isCopy ? 'Could not copy the plainbook.'
                    : 'Could not create the new plainbook.';
            if (isOpen ? !path : !name) return;
            showNewNotebook.value = false;
            const [route, body] = isOpen ? ['/open_notebook', { path }]
                : isCopy ? ['/copy_notebook', { name, folder }]
                    : ['/new_notebook', { name, folder }];
            try {
                const r = await apiCall(route, 'POST', body);
                if (r.status === 'error') {
                    uiError.value = r.message || failure;
                }
            } catch (err) {
                uiError.value = (err && err.message) || failure;
            }
        };

        const handleClickOutside = (event) => {
            if (event.target.closest('.modal')) return;
            const container = document.querySelector('.notebook-container');
            const navbar = document.querySelector('.app-toolbar');
            if (container && !container.contains(event.target) &&
                !(navbar && navbar.contains(event.target))) {
                activeIndex.value = -1;
            }
        };

        // Changing the input files (Files tab) can mark all cells stale on the
        // server; InputFile.js dispatches the fresh state so we can update.
        const onFilesChanged = (e) => {
            if (e.detail) updateState(e.detail);
        };

        // Not every caller awaits the promise it starts: a click handler may fire
        // a fetch and return, and Vue only routes errors from promises a handler
        // hands back. Such a rejection reaches neither app.config.errorHandler
        // nor any catch, so before this recovered the run state a stray could
        // leave `running` true and the navbar stuck on "Running cell N". Catch
        // the strays here instead of auditing every call site forever. The
        // background pollers (sendPing, ActionLogger) carry their own .catch, so
        // a dropped heartbeat still does not reach the error bar. Left
        // un-prevented so the rejection still reaches the console.
        const onUnhandledRejection = (e) => {
            const reason = e.reason;
            reportError(reason instanceof Error ? reason : new Error(String(reason)));
        };

        // ── Telling the server we are still here ──
        // Each Plainbook window owns a server and a kernel, so the server exits
        // when its window goes away. Two signals, because neither suffices:
        //   - pagehide + sendBeacon: the prompt one. sendBeacon is the only send
        //     that reliably survives page teardown (a fetch here is cancelled).
        //     The server only *schedules* the exit, because a reload fires
        //     pagehide too and the reloaded page's first request cancels it.
        //   - the ping below: the safety net, for a dropped beacon or a browser
        //     that was killed. The server's idle limit is minutes, not seconds,
        //     because browsers throttle timers in hidden tabs to about 1/minute.
        const PING_INTERVAL_MS = 30000;
        let pingTimer = null;
        const sendPing = () => {
            // Bypass apiCall: a failed heartbeat is not worth an error banner.
            serverFetch(`/ping?token=${authToken}`).catch(() => {});
        };
        const onPageHide = () => {
            navigator.sendBeacon(`/shutdown?token=${authToken}`);
        };

        onMounted(() => {
            fetchNotebook();
            window.addEventListener('keydown', handleKeydown);
            window.addEventListener('click', handleClickOutside);
            window.addEventListener('plainbook:files-changed', onFilesChanged);
            window.addEventListener('unhandledrejection', onUnhandledRejection);
            window.addEventListener('pagehide', onPageHide);
            pingTimer = setInterval(sendPing, PING_INTERVAL_MS);
        });

        onBeforeUnmount(() => {
            window.removeEventListener('keydown', handleKeydown);
            window.removeEventListener('click', handleClickOutside);
            window.removeEventListener('plainbook:files-changed', onFilesChanged);
            window.removeEventListener('unhandledrejection', onUnhandledRejection);
            window.removeEventListener('pagehide', onPageHide);
            if (pingTimer) clearInterval(pingTimer);
        });

        return { notebook, notebook_name, loading, error, isLocked, lockNotebook, shareOutputWithAi, skipRegeneration, explanationDetail, explanationBullets, explanationLatex, fixErrorAmendsDescription, aiTokens, verificationStatus, toggleShareOutput,
            askQuestions, clarifyState, dismissClarify, ui_submitClarification,
            sendExplanationToServer, authToken,
            sendCodeToServer, clearCellCode, ui_saveExplanationAndRun, ui_saveCodeAndRun,
            sendMarkdownToServer, generateCode, activeIndex, reloadNotebook, downloadIpynb,
            validateCode, ui_validateCode, explainCode, ui_explainCode, dismissValidation, ui_verifyNotebook, dismissVerification, ui_resetAndRunAllCells, ui_forceRegenerateCellCode,
            setActiveCell, ui_runCell, running, runningActivity, asRead,
            ui_interruptKernel, insertCell, markdownEditKey,
            foldState, ui_amendAndFold, ui_acceptAmend, ui_saveAmend, dismissFold, ui_unfold,
            moduleInstall, ui_installModule, dismissModuleInstall,
            last_executed_cell_index, last_valid_code_cell_index, last_valid_output_cell_index,
            last_valid_test_cell_index,
            saveSettings, showSettings, showInfo, showTestHelp,
            showNewNotebook, newNotebookFolder, notebookModalMode, notebookModalDefaultName,
            openNewNotebook, openCopyNotebook, openExistingNotebook, submitNotebookDialog,
            tocOpen,
            genError, uiError, closeUiError, renameNotebook, debug, sendDebugRequest, resetTokens,
            explanationEditKey, deleteCell, moveCell,
            clearOutputs, activeAiProvider, availableAiProviders, setActiveAiProvider, onProvidersChanged, isCodespace, hasGeminiKey, hasClaudeKey, hasOpenaiKey, claudeViaBedrock, logEnabled, logviewEnabled, printAllEnabled, chromeless, authToken,
            restarting, ui_restart,
            ui_runTestCell, ui_runAllTests, ui_saveExplanationAndRunTest, ui_saveCodeAndRunTest, ui_forceRegenerateTestCode,
            unitTestTargetIndex, unitTestActiveSubcell, unitTestActiveTestName, enterUnitTestMode, exitUnitTestMode,
            addUnitTest, deleteUnitTest, renameUnitTest,
            saveUnitTestExplanation, saveUnitTestCode, clearUnitTestCode, clearUnitTestOutputs,
            ui_runUnitTest, ui_runUnitTestSubcell, generateUnitTestCode, unitTestValidity,
            ui_validateUnitTestCode, dismissUnitTestValidation };
    },

template: `#app-template`,
});
app.directive('mathjax', mathjaxDirective);
app.mount('#app');
