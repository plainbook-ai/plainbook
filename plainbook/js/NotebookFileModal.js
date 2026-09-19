import { ref, computed, watch, nextTick } from './vue.esm-browser.js';
import FilePicker from './FilePicker.js';

// NotebookFileModal.js
// The one dialog for naming and locating a plainbook, in three modes:
//
//   new   an empty plainbook, created where the picker is pointing -- unless a
//         file of that name is already there, in which case it is opened, since
//         a name and a folder together name a file;
//   copy  a duplicate of the current plainbook, in the chosen folder; a name
//         already in use gets _2, _3, ... appended, because a copy must never
//         open the file it would have copied onto;
//   open  an existing notebook, chosen in the picker.
//
// Whichever mode, the result opens in its own window with its own kernel --
// exactly as if `plainbook <path>` had been run from the command line. The
// parent picks the mode and calls the matching endpoint; this dialog collects
// the name, the folder and the file.
export default {
    components: { FilePicker },
    props: ['isActive', 'mode', 'defaultName', 'startFolder', 'authToken'],
    emits: ['close', 'submit'],
    setup(props, { emit }) {
        const localName = ref('');
        const inputEl = ref(null);
        const folder = ref('');
        const entries = ref([]);
        const pickedPath = ref('');
        const pickerPath = ref('');

        const isCopy = computed(() => props.mode === 'copy');
        const isOpen = computed(() => props.mode === 'open');
        const title = computed(() =>
            isOpen.value ? 'Open plainbook'
                : isCopy.value ? 'Copy plainbook' : 'New plainbook');

        // In new mode the typed name may already exist in this folder, in which
        // case the dialog opens it instead of creating. The picker's listing is
        // right here, so the button can say which of the two will happen. The
        // server checks again -- that check is the one that counts.
        const existing = computed(() => {
            if (isOpen.value || isCopy.value) return null;
            const typed = localName.value.trim().toLowerCase();
            if (!typed) return null;
            const wanted = [typed, typed + '.plnb'];
            return entries.value.find(
                e => e.type === 'file' && wanted.includes(e.name.toLowerCase())) || null;
        });

        const actionLabel = computed(() =>
            isOpen.value ? 'Open' : isCopy.value ? 'Copy' : (existing.value ? 'Open' : 'Create'));

        const canSubmit = computed(() =>
            isOpen.value ? !!pickedPath.value : !!localName.value.trim());

        // Start from the suggested name every time it opens, with the field
        // focused and the suggestion selected so typing simply replaces it.
        watch(() => props.isActive, (active) => {
            if (!active) return;
            localName.value = props.defaultName || '';
            pickedPath.value = '';
            pickerPath.value = props.startFolder || '';
            nextTick(() => {
                if (!inputEl.value) return;
                inputEl.value.focus();
                inputEl.value.select();
            });
        });

        // The parent looks the folder up asynchronously, so it may arrive after
        // the dialog is already open.
        watch(() => props.startFolder, (path) => {
            if (props.isActive && path && !folder.value) pickerPath.value = path;
        });

        const onFolderChange = (path) => {
            folder.value = path;
            pickedPath.value = '';
        };

        const onPick = (entry) => {
            pickedPath.value = entry.path;
            // Clicking a file in a naming mode fills the field, so clicking and
            // typing lead to exactly the same place.
            if (!isOpen.value) localName.value = entry.name.replace(/\.plnb$/i, '');
        };

        const submit = () => {
            if (!canSubmit.value) return;
            emit('submit', {
                mode: props.mode,
                name: localName.value.trim(),
                folder: folder.value,
                // In new mode, an existing file turns this into an open.
                path: isOpen.value ? pickedPath.value
                    : (existing.value ? existing.value.path : ''),
            });
        };

        return {
            localName, inputEl, folder, pickedPath, pickerPath,
            isCopy, isOpen, title, actionLabel, existing, canSubmit,
            onFolderChange, onPick, submit,
            onEntries: (list) => { entries.value = list; },
        };
    },
    template: /* html */ `
    <div class="modal" :class="{'is-active': isActive}">
        <div class="modal-background" @click="$emit('close')"></div>
        <div class="modal-card" style="width: 90%; max-width: 620px;">
            <header class="modal-card-head">
                <p class="modal-card-title">{{ title }}</p>
                <button class="delete" aria-label="close" @click="$emit('close')"></button>
            </header>
            <section class="modal-card-body">
                <div class="field">
                    <label class="label is-size-7">Folder</label>
                    <file-picker
                        :auth-token="authToken"
                        :start-path="pickerPath"
                        :selectable="isOpen ? 'file' : 'none'"
                        @folder-change="onFolderChange"
                        @entries="onEntries"
                        @pick="onPick"
                        @confirm="submit" />
                </div>

                <div v-if="!isOpen" class="field">
                    <label class="label is-size-7">Name</label>
                    <div class="field has-addons mb-1">
                        <div class="control is-expanded">
                            <input class="input" type="text" ref="inputEl"
                                   v-model="localName"
                                   placeholder="my-analysis"
                                   @keyup.enter="submit">
                        </div>
                        <div class="control">
                            <span class="button is-static">.plnb</span>
                        </div>
                    </div>
                    <p class="help">
                        <span v-if="existing">
                            <strong>{{ existing.name }}</strong> already exists here, so it will be
                            opened rather than created.
                        </span>
                        <span v-else-if="isCopy">
                            A copy of this plainbook is created in
                            <code>{{ folder }}</code> and opened in a new window, with its own
                            kernel; you keep working here on the original. If the name is taken,
                            <code>_2</code>, <code>_3</code>, ... is appended.
                        </span>
                        <span v-else>
                            Created in <code>{{ folder }}</code> and opened in a new window,
                            with its own kernel.
                        </span>
                    </p>
                </div>

                <p v-else class="help">
                    <span v-if="pickedPath">
                        Opens <code>{{ pickedPath }}</code> in a new window, with its own kernel;
                        this plainbook keeps running.
                    </span>
                    <span v-else>Choose a notebook to open. Plainbooks are shown in black.</span>
                </p>
            </section>
            <footer class="modal-card-foot" style="justify-content: flex-end;">
                <button class="button" @click="$emit('close')">Cancel</button>
                <button class="button is-primary" :disabled="!canSubmit"
                        @click="submit">{{ actionLabel }}</button>
            </footer>
        </div>
    </div>`
};
