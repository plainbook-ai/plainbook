import { ref, computed, onMounted } from './vue.esm-browser.js';
import { serverFetch, isServerDown } from './serverFetch.js';

export default {
    props: ['authToken'],
    setup(props) {
        const localInstructions = ref('');
        const savedInstructions = ref('');
        const isLoading = ref(false);
        const isSaving = ref(false);
        const isDirty = computed(() => localInstructions.value !== savedInstructions.value);

        const loadInstructions = async () => {
            isLoading.value = true;
            try {
                const res = await serverFetch(`/get_ai_instructions?token=${props.authToken}`);
                if (!res.ok) return;
                const data = await res.json();
                savedInstructions.value = data.ai_instructions || '';
                localInstructions.value = savedInstructions.value;
            } catch (err) {
                if (isServerDown(err)) throw err;
                console.warn('Failed to load AI instructions:', err);
            } finally {
                isLoading.value = false;
            }
        };

        const save = async () => {
            isSaving.value = true;
            try {
                await serverFetch(`/set_ai_instructions?token=${props.authToken}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ai_instructions: localInstructions.value })
                });
                savedInstructions.value = localInstructions.value;
            } catch (err) {
                if (isServerDown(err)) throw err;
                console.warn('Failed to save AI instructions:', err);
            } finally {
                isSaving.value = false;
            }
        };

        const cancel = () => {
            localInstructions.value = savedInstructions.value;
        };

        onMounted(loadInstructions);

        return { localInstructions, isLoading, isSaving, isDirty, save, cancel };
    },
    template: /* html */ `
        <div style="display: flex; flex-direction: column; height: 400px; padding: 1rem;" class="instructions-container">
            <div style="margin-bottom: 0.5rem;">
                <p class="instructions-help" style="margin-top: 0rem;">
                    These instructions are included in every AI prompt for this notebook (code generation, test generation, and validation).
                </p>
            </div>
            <div v-if="isLoading" class="text-muted" style="flex: 1; display: flex; align-items: center; justify-content: center;">
                Loading...
            </div>
            <textarea v-else
                v-model="localInstructions"
                placeholder="e.g., Use pandas for data manipulation, use these specific libraries for data access, etc."
                class="instructions-textarea is-family-monospace"
                style="flex: 1; resize: none; padding: 0.5rem;"
            ></textarea>
            <div style="display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 0.5rem;">
                <button class="button is-light" :disabled="!isDirty" @click="cancel">Cancel</button>
                <button class="button is-link" :disabled="isSaving" :class="{ 'is-loading': isSaving }" @click="save">Save</button>
            </div>
        </div>
    `
};
