import { ref, watch, computed } from './vue.esm-browser.js';
import { createMarkdown } from './markdown.js';

export default {
    props: ['verification'],
    emits: ['dismiss'],

    setup(props, { emit }) {
        const md = createMarkdown();
        const message = ref(props.verification?.message || '');
        const is_valid = ref(props.verification?.is_valid || false);

        watch(() => props.verification, (val) => {
            message.value = val?.message || '';
            is_valid.value = val?.is_valid || false;
        });

        const renderedMarkdown = computed(() => {
            if (!message.value) {
                return is_valid.value
                    ? '<p>Notebook verified: no issues found.</p>'
                    : '';
            }
            return md.render(message.value);
        });

        const dismiss = () => emit('dismiss');

        return { dismiss, renderedMarkdown, is_valid };
    },

    template: /* html */ `
    <div class="verification-bar"
        :class="is_valid ? 'has-background-success-light' : 'has-background-danger-light'"
        style="position: relative; min-height: 1.75rem; border-top: 1px solid rgba(0,0,0,0.05);"
    >
        <div class="p-2 pr-6 my-0 content is-small" v-html="renderedMarkdown" v-mathjax></div>
        <button @click="dismiss" class="delete"
              style="cursor: pointer; position: absolute; top: 6px; right: 6px;">
        </button>
    </div>
    `
};
