import { ref, reactive, watch } from './vue.esm-browser.js';
import LocalModelPanel from './LocalModelPanel.js';

// The providers whose API keys are managed here.  `id` is the prefix of the
// `<id>_api_key` setting and of the `has<Id>Key` prop.
const KEY_PROVIDERS = [
    { id: 'claude', label: 'Claude', url: 'https://console.anthropic.com/settings/keys' },
    { id: 'gemini', label: 'Gemini', url: 'https://aistudio.google.com/app/apikey' },
    { id: 'openai', label: 'OpenAI', url: 'https://platform.openai.com/api-keys' },
];

export default {
    components: { LocalModelPanel },
    props: ['isActive', 'isCodespace', 'hasGeminiKey', 'hasClaudeKey', 'hasOpenaiKey', 'claudeViaBedrock',
            'askQuestions', 'explanationDetail', 'explanationBullets', 'explanationLatex',
            'fixErrorAmendsDescription', 'skipRegeneration', 'authToken'],
    // providers-changed: the local model panel changed the available AI
    // providers (payload {ai_providers, active_ai_provider}); it acts at once,
    // independently of Save.
    emits: ['close', 'save', 'providers-changed'],
    setup(props, { emit }) {
        // Per-provider key state, keyed by provider id.
        const localKeys = reactive({});   // text typed into the key input
        const editing = reactive({});     // the user clicked the masked key to replace it
        const removed = reactive({});     // the user asked to remove the key
        const localAskQuestions = ref(false);
        const localSkipRegeneration = ref(true);
        const localExplanationDetail = ref(1);
        const localExplanationBullets = ref(false);
        const localExplanationLatex = ref(false);
        const localFixErrorAmendsDescription = ref(true);

        // Whether the server has a key for the provider (props hasClaudeKey, ...).
        const hasKey = (id) => !!props['has' + id.charAt(0).toUpperCase() + id.slice(1) + 'Key'];

        const resetKeyState = () => {
            for (const p of KEY_PROVIDERS) {
                localKeys[p.id] = '';
                editing[p.id] = false;
                removed[p.id] = false;
            }
        };
        resetKeyState();

        // Reset inputs whenever the modal is opened
        watch(() => props.isActive, (active) => {
            if (active) {
                resetKeyState();
                localAskQuestions.value = !!props.askQuestions;
                // Default to on when the setting is not yet defined.
                localSkipRegeneration.value = props.skipRegeneration !== false;
                localExplanationDetail.value = props.explanationDetail || 1;
                localExplanationBullets.value = !!props.explanationBullets;
                localExplanationLatex.value = !!props.explanationLatex;
                // Default to on when the setting is not yet defined.
                localFixErrorAmendsDescription.value = props.fixErrorAmendsDescription !== false;
            }
        });

        const startEditing = (id) => { editing[id] = true; };
        const removeKey = (id) => { removed[id] = true; };

        const handleSave = () => {
            const payload = {
                ask_questions: localAskQuestions.value,
                skip_regeneration: localSkipRegeneration.value,
                fix_error_amends_description: localFixErrorAmendsDescription.value,
                explanation_detail: localExplanationDetail.value,
                explanation_bullets: localExplanationBullets.value,
                explanation_latex: localExplanationLatex.value,
            };
            // Per key: null = remove, '' = keep the current one, text = new key.
            for (const p of KEY_PROVIDERS) {
                payload[p.id + '_api_key'] = removed[p.id] ? null
                    : ((editing[p.id] || !hasKey(p.id)) ? (localKeys[p.id] || '') : '');
            }
            emit('save', payload);
        };

        return { keyProviders: KEY_PROVIDERS, localKeys, editing, removed, hasKey,
            localAskQuestions, localExplanationDetail, localExplanationBullets, localExplanationLatex,
            localFixErrorAmendsDescription, localSkipRegeneration, startEditing, removeKey, handleSave };
    },
    template: /* html */ `
    <div class="modal" :class="{'is-active': isActive}">
        <div class="modal-background" @click="$emit('close')"></div>
        <div class="modal-card">
            <header class="modal-card-head">
                <p class="modal-card-title">Settings</p>
                <button class="delete" aria-label="close" @click="$emit('close')"></button>
            </header>
            <section class="modal-card-body">
                <div class="field" v-for="p in keyProviders" :key="p.id">
                    <label class="label">{{ p.label }} API Key</label>
                    <div class="control" v-if="p.id === 'claude' && claudeViaBedrock">
                        <div class="input settings-bedrock-status">
                            Claude is available via AWS Bedrock
                        </div>
                    </div>
                    <div class="control" v-else-if="removed[p.id]">
                        <div class="input settings-key-status">
                            Key will be removed on save
                        </div>
                    </div>
                    <div class="control" v-else-if="hasKey(p.id) && !editing[p.id]">
                        <div style="display: flex; align-items: center; gap: 0.5rem;">
                            <div class="input settings-key-masked"
                                 @click="startEditing(p.id)">
                                ●●●●●●●●●●●●
                            </div>
                            <button class="button is-small is-danger is-outlined" @click="removeKey(p.id)"><i class="bx bx-trash"></i></button>
                        </div>
                    </div>
                    <div class="control" v-else>
                        <input class="input" type="text"
                               v-model="localKeys[p.id]"
                               :placeholder="hasKey(p.id) ? 'Enter new key (leave blank to keep current)' : 'Enter your ' + p.label + ' API key (optional)'">
                    </div>
                    <p class="help" v-if="!(p.id === 'claude' && claudeViaBedrock)">
                        <a :href="p.url" target="_blank" class="button is-small is-link is-light" style="margin-top: 0.5rem;">
                            {{ hasKey(p.id) ? 'Manage ' + p.label + ' API Key' : 'Get ' + p.label + ' API Key' }}
                        </a>
                    </p>
                </div>
                <hr>
                <local-model-panel :auth-token="authToken" :is-active="isActive"
                                   @providers-changed="$emit('providers-changed', $event)">
                </local-model-panel>
                <hr>
                <div class="field">
                    <label class="label">Code generation</label>
                    <label class="checkbox">
                        <input type="checkbox" v-model="localAskQuestions">
                        Enable asking questions
                    </label>
                    <p class="help">
                        When on, the AI may reply to an action cell with a few questions instead
                        of code, whenever the description leaves it in doubt about what the cell
                        should do. It is the AI that decides: when the description is clear, it
                        simply writes the code.
                    </p>
                    <label class="checkbox mt-3">
                        <input type="checkbox" v-model="localSkipRegeneration">
                        Skip regeneration when data is unchanged
                    </label>
                    <p class="help">
                        When on (default), a cell whose description and inputs have not changed is
                        left as it is instead of being sent to the AI again. Turn this off to always
                        regenerate a cell when the code before it changes.
                    </p>
                    <label class="checkbox mt-3">
                        <input type="checkbox" v-model="localFixErrorAmendsDescription">
                        Fix errors also amends the description
                    </label>
                    <p class="help">
                        When on (default), the "Fix Code" button asks the AI for a revised
                        description as well, so that regenerating from scratch would avoid the
                        error just fixed. Turn this off to have fixing an error change only the
                        code, leaving the description you wrote untouched.
                    </p>
                </div>
                <hr>
                <div class="field">
                    <label class="label">Code explanations</label>
                    <div class="field">
                        <label class="label is-small">Level of detail</label>
                        <div class="control">
                            <div class="select is-small">
                                <select v-model.number="localExplanationDetail">
                                    <option :value="1">Brief</option>
                                    <option :value="2">Normal</option>
                                    <option :value="3">Detailed</option>
                                    <option :value="4">Expert</option>
                                </select>
                            </div>
                        </div>
                    </div>
                    <label class="checkbox">
                        <input type="checkbox" v-model="localExplanationBullets">
                        Use bullet points
                    </label>
                    <br>
                    <label class="checkbox">
                        <input type="checkbox" v-model="localExplanationLatex">
                        Use LaTeX for equations
                    </label>
                    <p class="help">
                        Controls how the "Explain code" button writes the explanation.
                    </p>
                </div>
            </section>
            <footer class="modal-card-foot" style="justify-content: flex-end;">
                <button class="button is-primary" @click="handleSave">Save</button>
            </footer>
        </div>
    </div>`
};
