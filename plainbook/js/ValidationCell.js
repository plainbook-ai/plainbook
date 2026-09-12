import {ref, watch, nextTick, computed} from './vue.esm-browser.js';
import { createMarkdown } from './markdown.js';

export default {
    props: ['validation'],
    emits: ['dismiss_validation'],
    
    setup(props, { emit }) {
        const md = createMarkdown();
        const message = ref(props.validation.message || '');
        const is_valid = ref(props.validation.is_valid || false);
        const is_hidden = ref(props.validation.is_hidden || false);

        watch(() => props.validation, (val) => {
            console.log("Validation updated:", val);
            message.value = val.message || '';
            is_valid.value = val.is_valid || false;
            is_hidden.value = val.is_hidden || false;
        });

        const renderedMarkdown = computed(() => {
            return message.value ? md.render(message.value) : '';
        });

        const dismiss = () => {
            if (is_hidden.value) {
                is_hidden.value = true;
            }
            emit('dismiss_validation');
        };
        return { dismiss, renderedMarkdown, message, is_valid, is_hidden };
    },

    template: /* html */ `
    <div v-if="message && !is_hidden"
        class="validation-cell" 
        :class="is_valid ? 'has-background-success-light' : 'has-background-danger-light'"
        style="position: relative; min-height: 1.75rem;"
    >
        <div class="validation-content p-2 pr-6 my-0 content is-small" v-html="renderedMarkdown" v-mathjax></div>
        <button @click="dismiss" class="delete"
              style="cursor: pointer; position: absolute; top: 6px; right: 6px;">
        </button>
    </div>
    `
};