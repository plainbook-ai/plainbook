import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from './vue.esm-browser.js';

export default {
    props: ['source', 'executionCount', 'isActive', 'isLocked',
            'codeValid', 'outputValid', 'executed', 'hasError', 'asRead', 'externalCollapse'],
    emits: ['save', 'saveandrun', 'update:source', 'activate'],
    setup(props, { emit }) {
        const isCollapsed = ref(true);
        // When a parent supplies `externalCollapse`, the fold is driven from
        // outside (the code/explanation tab bar in NotebookCell) and the internal
        // "Show code" toggle is hidden. Otherwise CodeCell keeps its own fold, as
        // used by standalone test cells and the unit-test views.
        const controlled = computed(() => props.externalCollapse !== undefined && props.externalCollapse !== null);
        const collapsed = computed(() => controlled.value ? props.externalCollapse : isCollapsed.value);
        const isEditing = ref(false);
        const localSource = ref((Array.isArray(props.source) ? props.source.join('') : props.source) || '');
        const originalSource = ref(localSource.value);
        const textareaEl = ref(null);
        const localIsLocked = ref(props.isLocked);

        watch(() => props.isActive, (newVal) => {
            if (!newVal && isEditing.value) {
                saveCode();
            }
        });

        watch(() => props.source, (val) => {
            localSource.value = (Array.isArray(val) ? val.join('') : val) || '';
            nextTick(autoResize);
        });

        watch(() => props.isLocked, (newVal) => {
            console.log("Lock status changed:", newVal);
            localIsLocked.value = newVal;
            if (newVal) {
                cancelEdit();
            }
        });
        
        const autoResize = () => {
            const el = textareaEl.value;
            if (!el) return;
            el.style.boxSizing = 'border-box';
            el.style.overflow = 'hidden';
            el.style.resize = 'none';
            el.style.height = 'auto';
            el.style.height = `${el.scrollHeight}px`;
        };
       
        const highlightedCode = computed(() => {
            const code = localSource.value || '';
            if (!window.Prism || !window.Prism.languages || !window.Prism.languages.python) {
                // HTML escape if Prism not available
                return code.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            }
            try {
                const highlighted = window.Prism.highlight(
                    code, 
                    window.Prism.languages.python, 
                    'python'
                );
                return highlighted;
            } catch (e) {
                console.error('Prism highlighting error:', e);
                // HTML escape on error
                return code.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            }
        });

        const handleTabKey = (e) => {
            if (e.key === 'Tab') {
                e.preventDefault();
                const textarea = textareaEl.value;
                if (!textarea) return;
                
                const start = textarea.selectionStart;
                const end = textarea.selectionEnd;
                const text = localSource.value;
                const spaces = '    '; // 4 spaces
                
                if (start === end) {
                    // No selection - just insert 4 spaces
                    localSource.value = text.substring(0, start) + spaces + text.substring(end);
                    nextTick(() => {
                        textarea.selectionStart = textarea.selectionEnd = start + spaces.length;
                        autoResize();
                    });
                } else {
                    // Selection - indent all selected lines
                    const lines = text.split('\n');
                    const startLine = text.substring(0, start).split('\n').length - 1;
                    const endLine = text.substring(0, end).split('\n').length - 1;
                    
                    for (let i = startLine; i <= endLine; i++) {
                        if (lines[i] !== undefined) {
                            lines[i] = spaces + lines[i];
                        }
                    }
                    
                    const newText = lines.join('\n');
                    localSource.value = newText;
                    
                    nextTick(() => {
                        const newStart = start + spaces.length;
                        const newEnd = end + (endLine - startLine + 1) * spaces.length;
                        textarea.selectionStart = newStart;
                        textarea.selectionEnd = newEnd;
                        autoResize();
                    });
                }
            }
        };

        const enterEditMode = () => {
            if (localIsLocked.value) return;
            isEditing.value = true;
            nextTick(() => {
                if (textareaEl.value) textareaEl.value.focus();
            });
        };

        const enterEditModeAtPoint = (e) => {
            if (localIsLocked.value || isEditing.value) return;
            // Find the character offset at the click point
            let cursorOffset = 0;
            const pre = e.currentTarget.querySelector('pre');
            if (pre) {
                let container, offset;
                if (document.caretRangeFromPoint) {
                    const range = document.caretRangeFromPoint(e.clientX, e.clientY);
                    if (range) { container = range.startContainer; offset = range.startOffset; }
                } else if (document.caretPositionFromPoint) {
                    const pos = document.caretPositionFromPoint(e.clientX, e.clientY);
                    if (pos) { container = pos.offsetNode; offset = pos.offset; }
                }
                if (container) {
                    const walker = document.createTreeWalker(pre, NodeFilter.SHOW_TEXT);
                    let node;
                    while ((node = walker.nextNode())) {
                        if (node === container) { cursorOffset += offset; break; }
                        cursorOffset += node.textContent.length;
                    }
                }
            }
            isEditing.value = true;
            nextTick(() => {
                if (textareaEl.value) {
                    textareaEl.value.focus();
                    textareaEl.value.selectionStart = cursorOffset;
                    textareaEl.value.selectionEnd = cursorOffset;
                }
            });
        };

        const saveCode = () => {
            if (!isEditing.value) return;
            isEditing.value = false;
            emit('save', localSource.value);
        };

        const saveAndRunCode = () => {
            if (!isEditing.value) return;
            isEditing.value = false;
            emit('saveandrun', localSource.value);
        };

        const handleFlushEdits = () => {
            if (isEditing.value) {
                saveCode();
            }
        };

        const onBlur = () => {
            window.dispatchEvent(new Event('plainbook:flush-edits'));
        };

        onMounted(() => {
            window.addEventListener('plainbook:flush-edits', handleFlushEdits);
        });
        onBeforeUnmount(() => {
            window.removeEventListener('plainbook:flush-edits', handleFlushEdits);
        });

        const cancelEdit = () => {
            localSource.value = originalSource.value;
            isEditing.value = false;
        };

        const toggleCollapse = () => {
            isCollapsed.value = !isCollapsed.value;
            if (!isCollapsed.value && isEditing.value) nextTick(autoResize);
        };

        return { isCollapsed, toggleCollapse, controlled, collapsed, isEditing, cancelEdit, localSource,
            localIsLocked, highlightedCode, enterEditMode, enterEditModeAtPoint,
            saveCode, saveAndRunCode, textareaEl, autoResize, handleTabKey, onBlur };
    },
    template: /* html */ `
        <div class="code-cell-wrapper">
            <div v-if="!controlled || !collapsed" class="code-cell-toolbar" style="display: flex; gap: 0.25rem; align-items: center;">
                <button v-if="!controlled" class="button is-small is-ghost px-2 mt-1" style="text-decoration: none;"
                        @click="toggleCollapse">
                    {{ collapsed ? '▶ &nbsp;Show code' : '▼ &nbsp;Hide code' }}
                </button>
                <button v-if="!controlled && !isActive && collapsed" class="button is-small"
                    style="opacity: 0.6; padding: 0.1rem 0.5rem;"
                    @click.stop="$emit('activate')">
                    <span>Output:&nbsp;</span>
                    <span v-if="!codeValid">Stale</span>
                    <span v-else-if="!outputValid">Stale</span>
                    <span v-else-if="asRead">Unmodified</span>
                    <span v-else>Up to date</span>
                </button>
                <span style="flex: 1;"></span>
                <button v-if="isActive && !collapsed && !isEditing && !localIsLocked"
                    class="button is-small is-info mt-1 mr-3"
                    @click="enterEditMode">
                    <span class="icon"><i class="bx bx-pencil"></i></span>
                    <span>Edit Code</span>
                </button>
            </div>
            <div v-show="!collapsed" class="code-content" style="padding-left: 2.25rem;">
                <div class="code-editor-container p-2 is-size-7"
                     @dblclick="enterEditModeAtPoint($event)">
                    <pre class="language-python"><code class="language-python" v-html="highlightedCode + '\\n'"></code></pre>
                    <textarea v-if="isEditing"
                        ref="textareaEl"
                        v-model="localSource"
                        spellcheck="false"
                        @keydown.tab.prevent="handleTabKey"
                        @blur="onBlur"
                        @keydown.enter.shift.prevent="saveAndRunCode">
                    </textarea>
                </div>
                <div v-if="isEditing" style="display: flex; justify-content: flex-end; gap: 0.5rem; padding: 0 0.5rem 0.5rem;">
                    <button class="button is-small" @mousedown.prevent @click.stop="cancelEdit">
                        Cancel
                    </button>
                    <button class="button is-small is-primary" :disabled="localIsLocked" @mousedown.prevent @click.stop="saveCode">
                        Save
                    </button>
                </div>
            </div>
        </div>
    `
};
