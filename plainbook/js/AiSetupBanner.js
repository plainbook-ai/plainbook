// AiSetupBanner.js
// Shown at the top of the notebook when no AI provider is configured: no API
// key, and no local model. Plainbook cannot generate or validate anything in
// that state, and until this existed it said so only when the user attempted an
// AI action, so a first-time user met a blank notebook with no hint of what was
// missing.
// Deliberately has no dismiss button: it clears itself as soon as a key or a
// local model is configured (`activeAiProvider` in nb.js turns non-null and the
// v-if in index.html stops rendering it), and closing it before then would only
// hide the reason nothing works.

export default {
    emits: ['open-settings'],
    template: /* html */ `
        <article class="message is-warning ai-setup-banner mb-4">
            <div class="message-header py-1">
                <p>
                    <span class="icon"><i class="bx bx-error"></i></span>
                    <span>No AI model is set up yet</span>
                </p>
            </div>
            <div class="message-body py-2">
                <p class="mb-2">
                    Plainbook uses AI models to generate and validate code.
                    Please open the settings and select a local
                    model or add an API key.
                </p>
                <div class="buttons are-small mb-0">
                    <button class="button is-small is-primary"
                            @click.stop="$emit('open-settings')">
                        <span class="icon"><i class="bx bx-cog"></i></span>
                        <span>Open Settings</span>
                    </button>
                </div>
            </div>
        </article>
    `
};
