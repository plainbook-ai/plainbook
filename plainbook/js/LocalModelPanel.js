import { ref, computed, watch, onBeforeUnmount } from './vue.esm-browser.js';
import { serverFetch, isServerDown } from './serverFetch.js';

// The "Local model" section of the Settings modal.  Unlike the rest of the
// modal it talks to the server itself and acts immediately (no Save button):
// setting a model up is a download of minutes, run by the server in the
// background and shown here by polling /local_model/status.
const POLL_MS = 1000;

const gb = (bytes) => (bytes / 1e9).toFixed(1);

export default {
    props: ['authToken', 'isActive'],
    emits: ['providers-changed'],
    setup(props, { emit }) {
        const status = ref(null);       // last /local_model/status response
        const error = ref(null);        // last failed action, shown inline
        const busy = ref(false);        // an immediate action (select/remove) in flight
        let pollTimer = null;

        const job = computed(() => status.value && status.value.job);
        const jobRunning = computed(() => !!job.value && job.value.status === 'running');
        const models = computed(() => (status.value && status.value.models) || []);
        const runtime = computed(() => status.value && status.value.runtime);
        const memoryGb = computed(() => status.value && status.value.memory_gb);

        const runtimeText = computed(() => {
            if (!runtime.value) return '';
            if (!runtime.value.installed) {
                return 'The Ollama runtime is not installed; it will be downloaded during setup '
                    + '(about 160 MB on macOS, 1.4 GB on Linux and Windows).';
            }
            if (runtime.value.managed) {
                return `Ollama runtime ${runtime.value.version || ''} installed by Plainbook.`;
            }
            return `Using the Ollama runtime found at ${runtime.value.path}.`;
        });

        const lowMemory = (m) => memoryGb.value != null && memoryGb.value < m.min_memory_gb;

        const progressText = computed(() => {
            const j = job.value;
            if (!j) return '';
            let text = j.message || '';
            if (j.completed != null && j.total) {
                text += ` ${gb(j.completed)} / ${gb(j.total)} GB`;
            }
            return text;
        });

        const call = async (path, body) => {
            const options = body === undefined ? {} : {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            };
            const res = await serverFetch(`${path}?token=${props.authToken}`, options);
            if (!res.ok) throw new Error(`Server error: ${res.statusText}`);
            return res.json();
        };

        const applyStatus = (r) => {
            status.value = r;
            if (r.ai_providers) {
                emit('providers-changed', {
                    ai_providers: r.ai_providers,
                    active_ai_provider: r.active_ai_provider,
                });
            }
        };

        const refresh = async () => {
            try {
                applyStatus(await call('/local_model/status'));
            } catch (err) {
                if (isServerDown(err)) throw err;
                console.warn('Failed to load local model status:', err);
            }
            schedulePoll();
        };

        const schedulePoll = () => {
            clearTimeout(pollTimer);
            pollTimer = null;
            if (props.isActive && jobRunning.value) {
                pollTimer = setTimeout(refresh, POLL_MS);
            }
        };

        const action = async (path, body) => {
            error.value = null;
            busy.value = true;
            try {
                const r = await call(path, body);
                if (r.status === 'error') {
                    error.value = r.message;
                } else if (r.models) {
                    applyStatus(r);
                }
                await refresh();
            } catch (err) {
                if (isServerDown(err)) throw err;
                error.value = err.message;
            } finally {
                busy.value = false;
            }
        };

        const setup = (m, reinstall = false) => action('/local_model/setup', { model: m.id, reinstall });
        const select = (m) => action('/local_model/select', { model: m.id });
        const remove = (m) => {
            if (!confirm(`Remove ${m.label} from this computer? It can be downloaded again later.`)) return;
            return action('/local_model/remove', { model: m.id });
        };
        const cancel = () => action('/local_model/cancel', {});

        watch(() => props.isActive, (active) => {
            if (active) {
                error.value = null;
                refresh();
            } else {
                clearTimeout(pollTimer);
                pollTimer = null;
            }
        }, { immediate: true });

        onBeforeUnmount(() => clearTimeout(pollTimer));

        return { status, error, busy, job, jobRunning, models, runtimeText, memoryGb, lowMemory,
                 progressText, setup, select, remove, cancel };
    },
    template: /* html */ `
    <div class="field local-model-panel">
        <label class="label">Local model (no API key needed)</label>
        <p class="help mb-2">
            Run an open-weights model on this computer instead of a cloud AI. It needs a
            large one-time download and a computer with enough memory; it is slower and
            less capable than the cloud models, but free and private.
        </p>
        <template v-if="status">
            <div v-if="!status.platform_supported" class="notification is-warning is-light">
                Local models are not available on this kind of computer.
            </div>
            <template v-else>
                <p class="help mb-2">{{ runtimeText }}</p>
                <div v-for="m in models" :key="m.id" class="box local-model-row">
                    <div class="is-flex is-align-items-center is-justify-content-space-between">
                        <div>
                            <strong>{{ m.label }}</strong>
                            <span class="tag is-success is-light ml-2" v-if="m.selected">In use</span>
                            <span class="tag is-info is-light ml-2" v-else-if="m.installed">Installed</span>
                            <span class="tag is-light ml-2" v-else>Not installed</span>
                            <span class="tag is-light ml-1" v-if="m.loaded" title="Loaded in memory">Running</span>
                        </div>
                        <div class="buttons are-small mb-0" v-if="!jobRunning">
                            <button class="button is-primary" v-if="!m.installed"
                                    :class="{'is-loading': busy}" @click="setup(m)">
                                Download &amp; set up
                            </button>
                            <button class="button is-link" v-if="m.installed && !m.selected"
                                    :class="{'is-loading': busy}" @click="select(m)">Use</button>
                            <button class="button" v-if="m.installed"
                                    :class="{'is-loading': busy}" @click="setup(m, true)">Reinstall</button>
                            <button class="button is-danger is-outlined" v-if="m.installed"
                                    :class="{'is-loading': busy}" @click="remove(m)">Remove</button>
                        </div>
                    </div>
                    <p class="help">{{ m.description }}</p>
                    <p class="help">
                        About {{ m.download_gb }} GB to download; needs {{ m.min_memory_gb }} GB of memory.
                        <span v-if="lowMemory(m)" class="has-text-danger">
                            This computer has {{ Math.round(memoryGb) }} GB, which may not be enough.
                        </span>
                    </p>
                </div>
                <div v-if="jobRunning" class="local-model-progress">
                    <p class="help">{{ progressText }}</p>
                    <div class="is-flex is-align-items-center">
                        <progress class="progress is-info is-small mb-0"
                                  :value="job.total ? job.completed : undefined"
                                  :max="job.total || 1"></progress>
                        <button class="button is-small ml-2" @click="cancel">Cancel</button>
                    </div>
                </div>
                <p v-else-if="job && job.status === 'done'" class="help has-text-success">{{ job.message }}</p>
                <p v-else-if="job && job.status === 'cancelled'" class="help">{{ job.message }}</p>
                <p v-else-if="job && job.status === 'error'" class="help has-text-danger">{{ job.error }}</p>
            </template>
        </template>
        <p v-if="error" class="help has-text-danger">{{ error }}</p>
    </div>`
};
