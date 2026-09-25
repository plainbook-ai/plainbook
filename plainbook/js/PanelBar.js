import { ref } from './vue.esm-browser.js';
import InputFile from './InputFile.js';
import InstructionsPanel from './InstructionsPanel.js';
import VerificationBar from './VerificationBar.js';

export default {
    props: ['authToken', 'verification', 'unitTestsOnly'],
    emits: ['dismiss-verification'],
    components: { InputFile, InstructionsPanel, VerificationBar },
    setup() {
        const activeTab = ref(null);
        const selectedCount = ref(0);
        const missingCount = ref(0);

        const toggleTab = (name) => {
            activeTab.value = activeTab.value === name ? null : name;
        };

        const onFileCounts = ({ selected, missing }) => {
            selectedCount.value = selected;
            missingCount.value = missing;
        };

        return { activeTab, toggleTab, selectedCount, missingCount, onFileCounts };
    },
    template: /* html */ `
        <div class="panel-container">
            <div style="display: flex; align-items: stretch; background: transparent; padding: 0;">
                <button class="button is-ghost panel-tab"
                    @click="toggleTab('files')"
                    :class="{ 'is-active': activeTab === 'files' }"
                >
                    <span class="icon is-small"><i class="bx bx-folder"></i></span>
                    <span>Files</span>
                    <span class="panel-badge">
                        {{ selectedCount }}
                    </span>
                    <span v-if="missingCount > 0" class="panel-badge has-background-danger">
                        {{ missingCount }}
                    </span>
                </button>
                <div v-if="!unitTestsOnly" class="panel-divider"></div>
                <button v-if="!unitTestsOnly" class="button is-ghost panel-tab"
                    @click="toggleTab('instructions')"
                    :class="{ 'is-active': activeTab === 'instructions' }"
                >
                    <span class="icon is-small"><i class="bx bx-book"></i></span>
                    <span>Instructions</span>
                </button>
            </div>
            <verification-bar
                v-if="verification && !verification.is_hidden"
                :verification="verification"
                @dismiss="$emit('dismiss-verification')" />
            <div v-show="activeTab === 'files'" class="panel-section">
                <input-file :auth-token="authToken" @file-counts="onFileCounts" />
            </div>
            <div v-if="activeTab === 'instructions'" class="panel-section">
                <instructions-panel :auth-token="authToken" />
            </div>
        </div>
    `
};
