import { ref, watch, nextTick } from './vue.esm-browser.js';
import { createMarkdown } from './markdown.js';

const MarkdownCell = {
    props: ['source', 'startEditKey', 'isActive', 'isLocked'],
    emits: ['save', 'delete', 'moveUp', 'moveDown'],
    setup(props, { emit }) {
        const md = createMarkdown({ html: true });
        const localSource = ref(Array.isArray(props.source) ? props.source.join('') : props.source || '');
        const originalSource = ref(localSource.value);
        const textareaEl = ref(null);
        const localIsLocked = ref(props.isLocked);

        // Create a local editing state instead of using props.isEditing
        const isEditing = ref(false);

        const renderContent = () => md.render(localSource.value);
        const rendered = ref(renderContent());

        const refresh = () => {
            rendered.value = renderContent();
        };
        
        watch(() => props.source, (val) => {
            localSource.value = Array.isArray(val) ? val.join('') : val || '';
            refresh();
        });

        // Watch for the "bump" signal from the parent
        watch(() => props.startEditKey, () => {
            isEditing.value = true; // Use local ref
            nextTick(() => { 
                autoResize();
                if (textareaEl.value) textareaEl.value.focus(); 
            });    
        });    

        watch(() => props.isActive, (newVal) => {
            // If the cell is no longer active and it was being edited, save it.
            if (!newVal && isEditing.value) {
                save();
            }
        });

        watch(() => props.isLocked, (newVal) => {
            localIsLocked.value = newVal;
            if (newVal) {
                // Leave edit mode, so a cell locked mid-edit does not keep an
                // editable textarea whose Save would be refused. Deliberately
                // not cancelEdit(): that deletes the cell when the original was
                // empty, and locking must never delete anything -- which is
                // presumably why the call here was commented out before.
                localSource.value = originalSource.value;
                isEditing.value = false;
            }
        });

        const autoResize = () => {
            const el = textareaEl.value;
            if (!el) return;
            el.style.boxSizing = 'border-box';
            el.style.overflow = 'hidden';
            el.style.resize = 'none';
            el.style.height = 'auto';
            const minHeight = 24; // approximately one line in pixels
            el.style.height = `${Math.max(el.scrollHeight, minHeight)}px`;
        };

        const enterEditMode = () => {
            if (localIsLocked.value) return;
            originalSource.value = localSource.value;
            isEditing.value = true;
            nextTick(() => {
                autoResize();
                if (textareaEl.value) {
                    textareaEl.value.focus();
                    textareaEl.value.scrollTop = 0;
                }   
            });
        };

        const cancelEdit = () => {
            const originalIsEmpty = !originalSource.value || originalSource.value.trim().length === 0;
            if (originalIsEmpty) {
                isEditing.value = false;
                emit('delete');
                return;
            }
            localSource.value = originalSource.value;
            isEditing.value = false;
        };

        const save = () => {
            if (localIsLocked.value) return;
            const trimmed = (localSource.value || '').trim();
            isEditing.value = false;
            if (trimmed.length === 0) {
                emit('delete');
                return;
            }
            emit('save', localSource.value);
            refresh();
        };

        return { localSource, rendered, textareaEl, enterEditMode, cancelEdit, save, autoResize, 
            localIsLocked, isEditing: isEditing };
    },

    template: /* html */ `
        <div class="markdown-body content" style="position: relative; min-height: 2.5rem;">
            <div class="p-2 block mb-0" v-if="!isEditing" @dblclick="enterEditMode" 
                style="min-height: 1.6em" v-html="rendered" v-mathjax></div>

            <!-- bottom toolbar -->
            <div v-if="!isEditing && isActive && !localIsLocked"
                 class="explanation-toolbar pl-3 pr-3"
                 style="display: flex; align-items: center; justify-content: flex-end; gap: 0.5rem;">
                <div class="toolbar-right" style="display: flex; gap: 0.25rem;">
                    <button class="button is-small is-info" title="Edit markdown" :disabled="localIsLocked" @click.stop="enterEditMode">Edit</button>
                    <button class="button is-small is-info py-1 " title="Move up" aria-label="Move Up" @click.stop="$emit('moveUp')"><span class="icon"><i class="bx bx-arrow-up"></i></span></button>
                    <button class="button is-small is-info py-1 " title="Move down" aria-label="Move Down" @click.stop="$emit('moveDown')"><span class="icon"><i class="bx bx-arrow-down"></i></span></button>
                    <button class="button is-small is-danger py-1 " title="Delete" aria-label="Delete" @click.stop="$emit('delete')"><span class="icon"><i class="bx bx-trash"></i></span></button>
                </div>
            </div>

            <div v-if="isEditing" class="p-2">
                <textarea
                    ref="textareaEl"
                    v-model="localSource"
                    placeholder="Write a comment or explanation. You can use markdown."
                    class="textarea is-family-monospace p-2"
                    rows="1"
                    style="overflow: hidden; resize: none; height: 0;"
                    @input="autoResize"
                    @keydown.enter.shift.prevent="save">
                ></textarea>
                <div class="mt-2" style="display: flex; justify-content: flex-end; gap: 0.5rem;">
                    <button class="button is-small" @click="cancelEdit">Cancel</button>
                    <button class="button is-small is-primary" :disabled="localIsLocked" @click="save">Save</button>
                </div>
            </div>
        </div>`
};

export default MarkdownCell;
