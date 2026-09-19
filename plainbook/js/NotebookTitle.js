import { ref, watch, nextTick } from './vue.esm-browser.js';

// NotebookTitle.js
// Shows the notebook name at the top of the screen. Discoverable rename:
//   hover -> an outline appears, hinting the title is interactive
//   click -> the name becomes an editable field
// Committing a changed name emits 'rename', which saves the notebook as a
// copy under the new name (see renameNotebook in nb.js).
export default {
    props: ['name', 'isLocked'],
    emits: ['rename'],
    setup(props, { emit }) {
        const isEditing = ref(false);
        const localName = ref(props.name || '');
        const inputEl = ref(null);

        // Keep the local copy in sync when the server confirms a new name.
        watch(() => props.name, (val) => {
            if (!isEditing.value) localName.value = val || '';
        });

        const startEdit = () => {
            if (props.isLocked) return;
            localName.value = props.name || '';
            isEditing.value = true;
            nextTick(() => {
                if (inputEl.value) {
                    inputEl.value.focus();
                    inputEl.value.select();
                }
            });
        };

        const commit = () => {
            if (!isEditing.value) return;
            isEditing.value = false;
            const trimmed = localName.value.trim();
            if (trimmed && trimmed !== (props.name || '')) {
                emit('rename', trimmed);
            } else {
                localName.value = props.name || '';
            }
        };

        const cancel = () => {
            isEditing.value = false;
            localName.value = props.name || '';
        };

        return { isEditing, localName, inputEl, startEdit, commit, cancel };
    },
    template: /* html */ `
        <h1 class="title notebook-title" style="margin-bottom: 1.5rem;">
            <input v-if="isEditing"
                   ref="inputEl"
                   class="input notebook-title-input"
                   v-model="localName"
                   @keydown.enter.prevent="commit"
                   @keydown.esc.prevent="cancel"
                   @blur="commit" />
            <span v-else
                  class="notebook-title-text"
                  :title="isLocked ? name : 'Click to rename (saves a copy under the new name)'"
                  @click.stop="startEdit">{{ name }}</span>
        </h1>
    `
};
