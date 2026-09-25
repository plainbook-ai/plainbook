// Display names of the provider majors used as group headers in the model menu.
const MAJOR_LABELS = { claude: 'Claude', gemini: 'Gemini', openai: 'OpenAI' };
// Majors with a single entry that is its own label: no group header for them.
const UNGROUPED_MAJORS = new Set(['local']);

export default {
    props: ['isLocked', 'running', 'restarting', 'submitting', 'lastSubmittedAtLabel', 'isUserStudy', 'runningActivity', 'hasNotebook', 'upToDate', 'cellCount', 'testCellCount', 'hasApiKey', 'debug',
            'activeAiProvider', 'availableAiProviders', 'shareOutputWithAi', 'aiTokens', 'verification', 'verificationStatus', 'logEnabled', 'logviewEnabled', 'unitTestsOnly', 'chromeless', 'authToken'],
    emits: [
        'lock', 'refresh', 'interrupt', 'regenerate-all', 'new-notebook', 'copy-notebook',
        'open-notebook',
        'restart', 'reset-run-all', 'run-all', 'run-all-tests', 'verify-notebook', 'clear-outputs', 'open-info', 'open-settings', 'debug-request',
        'set-ai-provider', 'toggle-share-output', 'reset-tokens', 'download-ipynb', 'submit-study'
        ],
    data() {
        return { aiDropdownOpen: false };
    },
    computed: {
        totalTokens() {
            if (!this.aiTokens) return 0;
            return this.aiTokens.input || 0;
        },
        formattedTokens() {
            const t = this.totalTokens;
            if (t >= 1_000_000) return (t / 1_000_000).toFixed(1) + 'M';
            if (t >= 1_000) return (t / 1_000).toFixed(1) + 'k';
            return String(t);
        },
        activeProviderName() {
            if (!this.availableAiProviders || this.availableAiProviders.length === 0) return 'No AI Keys';
            const active = this.availableAiProviders.find(p => p.id === this.activeAiProvider);
            return active ? active.name : 'No AI';
        },
        canSwitchProvider() {
            return this.availableAiProviders && this.availableAiProviders.length >= 2;
        },
        verifyButtonClass() {
            return this.verificationStatus === 'ok' ? 'is-success' : 'is-danger';
        },
        verifyButtonTitle() {
            const ts = this.verification?.timestamp;
            let when = '';
            if (ts) {
                const d = new Date(ts);
                if (!isNaN(d.getTime())) {
                    when = ' on ' + d.toLocaleString(undefined, {
                        year: 'numeric', month: 'short', day: 'numeric',
                        hour: '2-digit', minute: '2-digit',
                    });
                }
            }
            if (this.verificationStatus === 'ok') {
                return 'Notebook last verified OK on this machine and path' + when;
            }
            if (this.verificationStatus === 'mismatch') {
                return 'Stored verification was made on a different machine or path' + when + ' -- re-verify';
            }
            return 'Notebook not verified -- click to run + AI audit for correctness and dangerous operations';
        },
        groupedProviders() {
            if (!this.availableAiProviders) return [];
            const groups = [];
            let lastMajor = null;
            for (const p of this.availableAiProviders) {
                const major = p.major || p.id;
                if (major !== lastMajor) {
                    if (UNGROUPED_MAJORS.has(major)) {
                        if (groups.length) groups.push({ type: 'divider' });
                    } else {
                        groups.push({ type: 'header', label: MAJOR_LABELS[major] || major.charAt(0).toUpperCase() + major.slice(1) });
                    }
                    lastMajor = major;
                }
                groups.push({ type: 'item', provider: p });
            }
            return groups;
        },
    },
    methods: {
        toggleDropdown() {
            if (!this.canSwitchProvider) return;
            this.aiDropdownOpen = !this.aiDropdownOpen;
        },
        selectProvider(id) {
            this.$emit('set-ai-provider', id);
            this.aiDropdownOpen = false;
        },
    },
    mounted() {
        this._onDocClick = (e) => {
            if (this.$refs.aiDropdown && !this.$refs.aiDropdown.contains(e.target)) {
                this.aiDropdownOpen = false;
            }
        };
        document.addEventListener('click', this._onDocClick);
    },
    beforeUnmount() {
        document.removeEventListener('click', this._onDocClick);
    },
    template: /* html */ `
    <div class="app-toolbar has-background-dark"
         style="display: flex; flex-wrap: wrap; align-items: center;
                padding: 0.4rem 0.4rem; gap: 0.2rem;"
         role="navigation" aria-label="main navigation">
        <div class="buttons mb-0">

                        <button class="button is-light" @click="$emit('open-info')" title="About Plainbook">
                            <img src="/images/Plainbook_logo.png" alt="About Plainbook"
                                 style="height: 1.5em;">
                        </button>

                        <div v-if="!isUserStudy && !unitTestsOnly" class="buttons has-addons mb-0" style="display: inline-flex;">
                            <button class="button is-light" title="Open an existing plainbook (in its own window)"
                                    @click="$emit('open-notebook')">
                                <span class="icon"><i class="bx bx-square"></i></span>
                            </button>
                            <button class="button is-light" title="Copy this plainbook under a new name (opens in its own window)"
                                    @click="$emit('copy-notebook')">
                                <span class="icon"><i class="bx bx-copy"></i></span>
                            </button>
                            <button class="button is-light" title="New plainbook (opens in its own window)"
                                    @click="$emit('new-notebook')">
                                <span class="icon"><i class="bx bx-plus"></i></span>
                            </button>
                        </div>

                        <button v-if="isLocked && !unitTestsOnly" class="button is-warning" title="Unlock Notebook" @click="$emit('lock', false)">
                        <span class="icon"><i class="bx bx-lock"></i></span>
                        </button>
                        <button v-else-if="!unitTestsOnly" class="button is-light" title="Lock Notebook" @click="$emit('lock', true)">
                        <span class="icon"><i class="bx bx-lock-open"></i></span>
                        </button>

                        <!-- <button v-if="!running && hasNotebook"
                            :disabled="cellCount === 0"
                            @click="$emit('clear-outputs')"
                            title="Clear all outputs"
                            class="button is-light">
                            <span class="icon"><i class="bx bx-broom"></i></span>
                            <span>Clear outputs</span>
                        </button> -->

                        <a v-if="logviewEnabled"
                           :href="'/log_view?token=' + authToken"
                           title="Open session log viewer"
                           class="button is-info is-light">
                            <span class="icon"><i class="bx bx-history"></i></span>
                            <span>Log viewer</span>
                        </a>

                        <button v-if="hasNotebook"
                                :disabled="running"
                                @click="$emit('download-ipynb')"
                                title="Download as Jupyter notebook (.ipynb)"
                                class="button is-light">
                            <span class="icon"><i class="bx bx-arrow-to-bottom"></i></span>
                            <span>.ipynb</span>
                        </button>

                        <!-- Only in a chromeless window, which has no browser toolbar
                             and so no reload button of its own. -->
                        <button v-if="chromeless && !running && hasNotebook"
                            @click="$emit('refresh')"
                            class="button is-light" title="Reload Notebook">
                            <span class="icon"><i class="bx bx-refresh-cw"></i></span>
                            <span>Refresh</span>
                        </button>

                        <button v-if="running && hasNotebook"
                                @click="$emit('interrupt')"
                                class="button is-danger" title="Interrupt Execution">
                            <span class="icon">
                                <i class="bx bx-stop-circle"></i>
                            </span>
                            <span v-if="runningActivity && runningActivity.type === 'generating'">
                                Generating cell {{ runningActivity.cellIndex + 1 }}<template v-if="runningActivity.cellName">: {{ runningActivity.cellName }}</template>
                            </span>
                            <span v-else-if="runningActivity && runningActivity.type === 'validating'">
                                Validating cell {{ runningActivity.cellIndex + 1 }}<template v-if="runningActivity.cellName">: {{ runningActivity.cellName }}</template>
                            </span>
                            <span v-else-if="runningActivity && runningActivity.type === 'explaining'">
                                Explaining code in cell {{ runningActivity.cellName || (runningActivity.cellIndex + 1) }}
                            </span>
                            <span v-else-if="runningActivity && runningActivity.type === 'verifying'">
                                Verifying notebook&hellip;
                            </span>
                            <span v-else-if="runningActivity && runningActivity.type === 'running'">
                                Running cell {{ runningActivity.cellIndex + 1 }}<template v-if="runningActivity.cellName">: {{ runningActivity.cellName }}</template>
                            </span>
                            <span v-else-if="runningActivity && runningActivity.type === 'installing'">
                                Installing module<template v-if="runningActivity.moduleName"> {{ runningActivity.moduleName }}</template>&hellip;
                            </span>
                            <span v-else-if="runningActivity && runningActivity.type === 'unit-test-gen-setup'">
                                Generating setup code<template v-if="runningActivity.testName"> ({{ runningActivity.testName }})</template>
                            </span>
                            <span v-else-if="runningActivity && runningActivity.type === 'unit-test-gen-test'">
                                Generating test code<template v-if="runningActivity.testName"> ({{ runningActivity.testName }})</template>
                            </span>
                            <span v-else-if="runningActivity && runningActivity.type === 'unit-test-setup'">
                                Running setup cell<template v-if="runningActivity.testName"> ({{ runningActivity.testName }})</template>
                            </span>
                            <span v-else-if="runningActivity && runningActivity.type === 'unit-test-target'">
                                Running target cell<template v-if="runningActivity.testName"> ({{ runningActivity.testName }})</template>
                            </span>
                            <span v-else-if="runningActivity && runningActivity.type === 'unit-test-test'">
                                Running test cell<template v-if="runningActivity.testName"> ({{ runningActivity.testName }})</template>
                            </span>
                            <span v-else>Running...</span>
                        </button>

                        <button v-if="!running && hasNotebook"
                            :disabled="cellCount === 0 || restarting"
                            :class="['button', 'is-primary']"
                            @mousedown.prevent
                            @click="$emit('restart')"
                            title="Restart (clears execution state)">
                            <span class="icon"><i class="bx bx-rewind"></i></span>
                            <span>Restart</span>
                        </button>

                        <!--
                        <button v-if="!running && hasNotebook"
                            :disabled="cellCount === 0"
                            @mousedown.prevent
                            @click="$emit('reset-run-all')"
                            title="Reset and run all cells"
                            class="button is-primary">
                            <span class="icon">
                                <i class="bx bx-keyframe-ease-in"></i>
                            </span>
                            <span>Re-run</span>
                        </button>
                        -->

                        <button v-if="!running && hasNotebook"
                            :disabled="cellCount === 0"
                            @mousedown.prevent
                            @click="$emit('run-all')"
                            title="Run all"
                            class="button is-primary">
                            <span class="icon"><i class="bx bx-play"></i></span>
                            <span>Run</span>
                        </button>

                        <button v-if="!running && hasNotebook"
                            :disabled="!testCellCount"
                            @mousedown.prevent
                            @click="$emit('run-all-tests')"
                            :title="testCellCount ? 'Run all tests' : 'This notebook has no global tests'"
                            class="button is-warning">
                            <span class="icon"><i class="bx bx-seal-check"></i></span>
                            <span>Run tests</span>
                        </button>

                        <button v-if="!running && hasNotebook && !unitTestsOnly"
                            :disabled="cellCount === 0"
                            @mousedown.prevent
                            @click="$emit('verify-notebook')"
                            :title="verifyButtonTitle"
                            :class="['button', verifyButtonClass]">
                            <span class="icon"><i class="bx bx-shield-quarter"></i></span>
                            <span>Verify</span>
                        </button>

                        <button v-if="hasNotebook && isUserStudy"
                            :disabled="cellCount === 0 || running || submitting"
                            @mousedown.prevent
                            @click="$emit('submit-study')"
                            title="Submit the notebook for analysis"
                            class="button is-success">
                            <span class="icon"><i class="bx bx-arrow-from-bottom-stroke"></i></span>
                            <span>{{ submitting ? 'Submitting...' : 'Submit' }}</span>
                        </button>
                        <span v-if="hasNotebook && isUserStudy && lastSubmittedAtLabel"
                              class="tag is-info is-light"
                              :title="'Latest submit time'">
                            Last submit: {{ lastSubmittedAtLabel }}
                        </span>

        </div>
        <span style="flex: 1;"></span>
        <div class="buttons mb-0">
                        <button v-if="debug" class="button is-warning" title="Send debug request" @click="$emit('debug-request')">
                            <span class="icon"><i class="bx bx-bug"></i></span>
                            <span>Debug</span>
                        </button>
                        <!-- Orange while outputs go to the AI, green once they do
                             not: the colour tracks how exposed the data is, so
                             green agrees with the check on the shield rather than
                             signalling "this feature is on". -->
                        <button class="button" :class="shareOutputWithAi ? 'is-warning' : 'is-success'"
                                @click="$emit('toggle-share-output')"
                                :title="shareOutputWithAi ? 'Cell outputs are shared with AI (click to disable)' : 'Cell outputs are NOT shared with AI (click to enable)'">
                            <span class="icon">
                                <i :class="shareOutputWithAi ? 'bx bx-shield' : 'bx bx-check-shield'"></i>
                            </span>
                        </button>
                        <span v-if="debug" class="tag is-dark" :title="'AI tokens: ' + (aiTokens.input || 0) + ' input, ' + (aiTokens.output || 0) + ' output. Click to reset.'" style="cursor: pointer; margin-right: 0.25rem;" @click="$emit('reset-tokens')">
                            <span class="icon is-small" style="margin-right: 0.25rem;"><i class="bx bx-chip"></i></span>
                            {{ formattedTokens }}
                        </span>
                        <div ref="aiDropdown">
                            <div class="dropdown" :class="{'is-active': aiDropdownOpen}">
                                <div class="dropdown-trigger">
                                    <button class="button is-light"
                                            :disabled="!availableAiProviders || availableAiProviders.length === 0"
                                            @click.stop="toggleDropdown"
                                            :title="canSwitchProvider ? 'Select AI Provider' : activeProviderName">
                                        <span class="icon is-small"><i class="bx bx-light-bulb"></i></span>
                                        <span>{{ activeProviderName }}</span>
                                        <span v-if="canSwitchProvider" class="icon is-small">
                                            <i class="bx bx-chevron-down"></i>
                                        </span>
                                    </button>
                                </div>
                                <div class="dropdown-menu ai-provider-menu" role="menu" v-if="canSwitchProvider">
                                    <div class="dropdown-content">
                                        <template v-for="(entry, idx) in groupedProviders" :key="idx">
                                            <hr v-if="entry.type === 'divider' || (entry.type === 'header' && idx > 0)" class="dropdown-divider">
                                            <p v-if="entry.type === 'header'" class="dropdown-item has-text-weight-bold ai-provider-header">
                                                {{ entry.label }}
                                            </p>
                                            <a v-if="entry.type === 'item'"
                                                class="dropdown-item" :class="{'is-active': entry.provider.id === activeAiProvider}"
                                                @click.prevent="selectProvider(entry.provider.id)">
                                                {{ entry.provider.name }}
                                            </a>
                                        </template>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <button v-if="!unitTestsOnly" class="button" :class="hasApiKey ? 'is-light' : 'is-warning'"
                                @click="$emit('open-settings')" title="Settings">
                            <span class="icon"><i :class="hasApiKey ? 'bx bx-cog' : 'bx bx-alert-triangle'"></i></span>
                            <span>Settings</span>
                        </button>
        </div>
    </div>`
};
