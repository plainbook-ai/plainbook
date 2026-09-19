import { ref, computed, watch } from './vue.esm-browser.js';
import { serverFetch, isServerDown } from './serverFetch.js';

// FilePicker.js
// A folder browser for choosing where a plainbook should live, or which one to
// open. It only browses and reports: the folder it is showing, and the file the
// user clicked. Nothing is written to the server, so the same component serves
// the new, copy and open dialogs.
//
// The browser's own file dialog cannot be used for this: it hands the page a
// File object with a bare name, never a path, and the path is exactly what the
// server needs in order to open and save the notebook.
export default {
    props: {
        authToken: String,
        // Folder to open on; changing it re-navigates.
        startPath: String,
        // 'file' lets a file be selected (and highlighted); 'none' means only
        // the folder matters, and clicking a file merely reports it.
        selectable: { type: String, default: 'none' },
        // Files with this extension are the point of the dialog; the rest are
        // shown greyed, but remain clickable.
        highlightExtension: { type: String, default: '.plnb' },
    },
    emits: ['folder-change', 'entries', 'pick', 'confirm'],
    setup(props, { emit }) {
        const currentPath = ref('');
        const parentPath = ref('');
        const entries = ref([]);
        const isLoading = ref(false);
        const filterQuery = ref('');
        const selectedPath = ref('');
        const error = ref('');

        const filteredEntries = computed(() => {
            const q = filterQuery.value.toLowerCase();
            return entries.value.filter(e => e.name.toLowerCase().includes(q));
        });

        const atRoot = computed(() =>
            !parentPath.value || parentPath.value === currentPath.value);

        const isNotebook = (entry) =>
            entry.type === 'file' &&
            entry.name.toLowerCase().endsWith(props.highlightExtension);

        const fetchFiles = async (path) => {
            isLoading.value = true;
            error.value = '';
            try {
                const res = await serverFetch(`/file_list?token=${props.authToken}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path }),
                });
                // Unlike InputFile.js, do not parse a failed response: an
                // unreadable folder must say so, not look empty.
                if (!res.ok) {
                    error.value = res.status === 403
                        ? 'You do not have permission to read that folder.'
                        : 'That folder could not be read.';
                    return;
                }
                const data = await res.json();
                entries.value = data.files || [];
                // The server tells us where we are and what is above us, so
                // navigation needs no platform-specific path surgery here.
                currentPath.value = data.path || path;
                parentPath.value = data.parent || '';
                filterQuery.value = '';
                selectedPath.value = '';
                emit('folder-change', currentPath.value);
                emit('entries', entries.value);
            } catch (err) {
                if (isServerDown(err)) throw err;
                error.value = 'That folder could not be read.';
            } finally {
                isLoading.value = false;
            }
        };

        const goUp = () => fetchFiles(parentPath.value);
        const openFolder = (entry) => fetchFiles(entry.path);

        const goTo = async (route) => {
            try {
                const res = await serverFetch(`${route}?token=${props.authToken}`);
                const data = await res.json();
                await fetchFiles(data.path);
            } catch (err) {
                if (isServerDown(err)) throw err;
                console.warn(`Could not navigate to ${route}:`, err);
            }
        };
        const goHome = () => goTo('/home_dir');
        const goCurrent = () => goTo('/current_dir');

        const pickFile = (entry) => {
            if (props.selectable === 'file') selectedPath.value = entry.path;
            emit('pick', entry);
        };

        // Navigate whenever the parent points us somewhere, including on open.
        // With nowhere to go, place ourselves at the notebook's own folder.
        watch(() => props.startPath, (path) => {
            if (path) fetchFiles(path);
            else if (!currentPath.value) goCurrent();
        }, { immediate: true });

        return {
            currentPath, entries, filteredEntries, filterQuery, isLoading, error,
            selectedPath, atRoot, isNotebook,
            goUp, goHome, goCurrent, openFolder, pickFile,
        };
    },
    template: /* html */ `
    <div class="file-browser" style="border: 1px solid var(--bulma-border); border-radius: 4px;">
        <div class="file-browser-filter">
            <input class="input is-small" type="text" v-model="filterQuery"
                   placeholder="Filter by name">
        </div>
        <div class="file-browser-nav">
            <button class="button is-small is-light" @click="goUp"
                    :disabled="atRoot" title="Up one folder">
                <span class="icon is-small"><i class="bx bx-arrow-big-up"></i></span>
            </button>
            <button class="button is-small is-light" @click="goHome" title="Home folder">
                <span class="icon is-small"><i class="bx bx-home"></i></span>
            </button>
            <button class="button is-small is-light" @click="goCurrent"
                    title="Folder of this plainbook">
                <span class="icon is-small"><i class="bx bx-target"></i></span>
            </button>
            <code class="is-size-7" style="overflow: hidden; text-overflow: ellipsis;
                  white-space: nowrap;">{{ currentPath }}</code>
        </div>
        <div style="height: 240px; overflow-y: auto;">
            <p v-if="error" class="has-text-danger is-size-7 p-2">{{ error }}</p>
            <p v-else-if="isLoading" class="is-size-7 has-text-grey p-2">Loading...</p>
            <p v-else-if="!filteredEntries.length" class="is-size-7 has-text-grey p-2">
                Nothing here.
            </p>
            <ul v-else style="list-style: none; margin: 0; padding: 0;">
                <li v-for="item in filteredEntries" :key="item.path"
                    class="file-item"
                    :class="{ 'is-selected': item.path === selectedPath }">
                    <span class="icon is-small" :class="item.type === 'directory' ? 'dir-icon' : ''">
                        <i :class="item.type === 'directory' ? 'bx bx-folder' : 'bx bx-file'"></i>
                    </span>
                    <span v-if="item.type === 'directory'" class="file-name-link is-size-7"
                          @click="openFolder(item)">{{ item.name }}/</span>
                    <span v-else class="is-size-7 file-name-link"
                          :class="{ 'has-text-grey': !isNotebook(item) }"
                          @click="pickFile(item)"
                          @dblclick="$emit('confirm')">{{ item.name }}</span>
                </li>
            </ul>
        </div>
    </div>`
};
