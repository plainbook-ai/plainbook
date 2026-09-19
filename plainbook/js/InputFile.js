import { ref, reactive, onMounted, computed, watch } from './vue.esm-browser.js';
import { serverFetch, isServerDown } from './serverFetch.js';

export default {
    props: ['authToken'],
    emits: ['file-counts'],
    setup(props, { emit }) {
        const currentPath = ref('/'); // Root path
        const fileList = ref([]);     // Files in the current directory
        const selectedFiles = reactive(new Map()); // Path -> File object mapping
        const missingFiles = reactive(new Map()); // Path -> File object mapping for missing files
        const isLoading = ref(false);
        const filterQuery = ref(''); // Search state
        // When set, the browser is in "replace mode" for a specific file:
        // { kind: 'selected' | 'missing', path, name }. Null = normal add mode.
        const replaceTarget = ref(null);

        const filteredFiles = computed(() => {
            const query = filterQuery.value.toLowerCase();
            return fileList.value.filter(f => f.name.toLowerCase().includes(query));
        });

        const fetchFiles = async (path) => {
            isLoading.value = true;
            filterQuery.value = ''; // Reset search when changing folders
            try {
                const response = await serverFetch(`/file_list?token=${props.authToken}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path: path })
                });
                const data = await response.json();
                fileList.value = data.files || []; 
                currentPath.value = path;
            } catch (err) {
                throw new Error("Failed to fetch files", { cause: err });
            } finally {
                isLoading.value = false;
            }
        };

        // Navigation actions. These return the promise rather than dropping it:
        // Vue only routes a handler's error to the global handler if the handler
        // hands the promise back.
        const openFolder = (folder) => {
            return fetchFiles(folder.path);
        };

        const goUp = () => {
            const parts = currentPath.value.split('/').filter(Boolean);
            parts.pop();
            const parentPath = '/' + parts.join('/');
            return fetchFiles(parentPath);
        };

        const goHome = async () => {
            try {
                const res = await serverFetch(`/home_dir?token=${props.authToken}`);
                const data = await res.json();
                await fetchFiles(data.path);
            } catch (err) {
                if (isServerDown(err)) throw err;
                console.warn('Failed to navigate to home directory:', err);
            }
        };

        const goCurrent = async () => {
            try {
                const res = await serverFetch(`/current_dir?token=${props.authToken}`);
                const data = await res.json();
                await fetchFiles(data.path);
            } catch (err) {
                if (isServerDown(err)) throw err;
                console.warn('Failed to navigate to current directory:', err);
            }
        };

        // Selection actions
        const toggleSelection = (file) => {
            if (selectedFiles.has(file.path)) {
                selectedFiles.delete(file.path);
            } else {
                selectedFiles.set(file.path, file);
            }
        };

        const removeSelected = (path) => {
            selectedFiles.delete(path);
        };

        const removeMissing = (path) => {
            missingFiles.delete(path);
        }

        // Replace / Find flow -------------------------------------------------
        const startReplaceSelected = (path, file) => {
            replaceTarget.value = { kind: 'selected', path, name: file.name };
        };
        const startReplaceMissing = (path, file) => {
            replaceTarget.value = { kind: 'missing', path, name: file.name };
        };
        const cancelReplace = () => { replaceTarget.value = null; };

        // Mode-dependent description line shown under the title.
        const browserHeader = computed(() => {
            const t = replaceTarget.value;
            if (!t) return 'Select files for notebook access, so AI knows where to find them.';
            if (t.kind === 'missing') return `Let AI know where it can find file ${t.name}`;
            return `Replace ${t.name} with another file for AI to use`;
        });

        // Pick `newFile` (from the left browser) as the replacement.
        const pickReplacement = (newFile) => {
            const t = replaceTarget.value;
            if (!t) return;
            selectedFiles.set(newFile.path, newFile);      // add the new file
            if (t.kind === 'missing') {
                missingFiles.delete(t.path);               // clear the missing entry
            } else if (t.path !== newFile.path) {
                selectedFiles.delete(t.path);              // drop the replaced file
            }
            replaceTarget.value = null;                    // back to "Add files"
        };

        const syncSelectedFiles = async () => {
            // Convert Map values to a plain array of file objects
            try {
                const res = await serverFetch(`/set_files?token=${props.authToken}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        files: Array.from(selectedFiles.values()),
                        missing_files: Array.from(missingFiles.values())
                    })
                });
                // Changing the file set can mark all cells stale server-side.
                // Propagate the fresh state so the notebook view updates.
                const data = await res.json().catch(() => null);
                if (data && data.state) {
                    window.dispatchEvent(new CustomEvent(
                        'plainbook:files-changed', { detail: data.state }));
                }
            } catch (err) {
                throw new Error("Failed to sync files with notebook", { cause: err });
            }
        };

        const emitCounts = () => {
            emit('file-counts', { selected: selectedFiles.size, missing: missingFiles.size });
        };

        // emitCounts() first so the sync promise can be returned: Vue wraps watcher
        // callbacks the same way it wraps event handlers, and only handles the
        // error if the callback returns the promise.
        watch(selectedFiles, () => { emitCounts(); return syncSelectedFiles(); }, { deep: true });
        watch(missingFiles,  () => { emitCounts(); return syncSelectedFiles(); }, { deep: true });

        // Load selected files mapping from server and populate `selectedFiles`
        const loadSelectedFiles = async () => {
            try {
                const res = await serverFetch(`/get_files?token=${props.authToken}`);
                if (!res.ok) return;
                const data = await res.json();
                // Clear existing selection and repopulate
                selectedFiles.clear();
                data.files.forEach(f => {
                    selectedFiles.set(f.path, f);
                });
                missingFiles.clear();
                data.missing_files.forEach(f => {
                    missingFiles.set(f.path, f);
                });
                emitCounts();
            } catch (err) {
                if (isServerDown(err)) throw err;
                console.warn('Failed to load selected input files:', err);
            }
        };

        // Get home dir on load
        const initialize = async () => {
            try {
                const res = await serverFetch(`/current_dir?token=${props.authToken}`);
                const data = await res.json();
                await fetchFiles(data.path);
                await loadSelectedFiles();
            } catch (err) {
                // Falling back to the root only makes sense if the server is
                // alive and merely rejected the path; if it isn't answering,
                // retrying just fails a second time.
                if (isServerDown(err)) throw err;
                await fetchFiles('/');
                await loadSelectedFiles();
            }
        };

        // Initial load
        onMounted(initialize);

        return {
            currentPath, fileList, isLoading,
            selectedFiles, missingFiles, filterQuery, filteredFiles,
            openFolder, goUp, goHome, goCurrent, toggleSelection, removeSelected, removeMissing,
            replaceTarget, browserHeader, startReplaceSelected, startReplaceMissing,
            cancelReplace, pickReplacement
        };
    },
    template: /* html */ `
            <div style="display: flex; height: 400px;" class="file-browser">
                <div style="flex: 1; border-right: 1px solid var(--bulma-border); display: flex; flex-direction: column;">
                    <div class="file-browser-title">
                        <span v-if="replaceTarget">Replace file <strong>{{ replaceTarget.name }}</strong></span>
                        <span v-else>Add files</span>
                        <button v-if="replaceTarget" @click="cancelReplace" class="button is-small is-light" title="Cancel">
                            <span class="icon is-small"><i class="bx bx-x"></i></span><span>Cancel</span>
                        </button>
                    </div>
                    <div class="file-browser-header">{{ browserHeader }}</div>
                    <div class="file-browser-filter">
                        <input type="text" v-model="filterQuery" placeholder="Filter files..."
                            style="flex: 1; padding: 4px;">
                    </div>
                    <div class="file-browser-nav">
                        <button @click="goUp" :disabled="currentPath === '/'" class="button is-small is-light">
                            <span class="icon is-small"><i class="bx bx-arrow-big-up"></i></span>
                            <span>Up</span>
                        </button>
                        <button @click="goHome" class="button is-small is-light">
                            <span class="icon is-small"><i class="bx bx-home"></i></span>
                            <span>Home</span>
                        </button>
                        <button @click="goCurrent" class="button is-small is-light">
                            <span class="icon is-small"><i class="bx bx-target"></i></span>
                            <span>Current</span>
                        </button>
                        <code style="font-size: 0.8rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{{ currentPath }}</code>
                    </div>
                    <div style="overflow-y: auto; flex: 1;">
                        <div v-if="isLoading" class="text-muted" style="padding: 1rem;">Loading...</div>
                        <ul v-else style="list-style: none; margin: 0; padding: 0;">
                            <li v-for="item in filteredFiles" :key="item.path" class="file-item">

                                <span style="width: 1rem; min-width: 1rem; display: flex; justify-content: center; align-items: center; flex-shrink: 0;">
                                    <input type="checkbox" v-if="item.type === 'file' && !replaceTarget"
                                           :checked="selectedFiles.has(item.path)"
                                           @change="toggleSelection(item)"
                                           style="width: 0.8rem; height: 0.8rem; margin: 0; cursor: pointer;">
                                </span>

                                <span class="icon is-small" :class="item.type === 'directory' ? 'dir-icon' : ''">
                                    <i :class="item.type === 'directory' ? 'bx bx-folder' : 'bx bx-file'"></i>
                                </span>

                                <span v-if="item.type === 'directory'"
                                      @click="openFolder(item)"
                                      class="file-name-link is-size-7">
                                    {{ item.name }}/
                                </span>
                                <span v-else-if="replaceTarget"
                                      @click="pickReplacement(item)"
                                      class="file-name-link is-size-7"
                                      title="Use this file as the replacement">
                                    {{ item.name }}
                                </span>
                                <span v-else class="is-size-7">{{ item.name }}</span>
                            </li>
                        </ul>
                    </div>
                </div>

                <div class="selected-files-panel">
                    <div class="selected-files-header">Selected Files ({{ selectedFiles.size }})</div>
                    <div style="overflow-y: auto; flex: 1; padding: 0.5rem;">
                        <div v-if="selectedFiles.size === 0" class="text-subtle" style="font-style: italic;">No files selected</div>
                        <ul style="list-style: none; margin: 0; padding: 0;">
                            <li v-for="[path, file] in selectedFiles" :key="path" class="selected-file-card">
                                <button @click="removeSelected(path)" class="delete has-background-danger is-small" style="margin-top: 4px;">
                                </button>
                                <div style="display: flex; flex-direction: column; min-width: 0; flex: 1;">
                                    <div class="selected-file-name" :title="path">
                                        {{ file.name }}
                                    </div>
                                    <div class="selected-file-path">
                                        {{ path }}
                                    </div>
                                </div>
                                <button @click="startReplaceSelected(path, file)" class="button is-small is-light" title="Replace this file">
                                    <span class="icon is-small"><i class="bx bx-search"></i></span><span>Replace</span>
                                </button>
                            </li>
                        </ul>
                    </div>
                    <div v-if="missingFiles.size > 0" class="selected-files-header has-text-danger">Missing Files ({{ missingFiles.size }})</div>
                    <div v-if="missingFiles.size > 0" style="overflow-y: auto; flex: 1; padding: 0.5rem;">
                        <ul style="list-style: none; margin: 0; padding: 0;">
                            <li v-for="[path, file] in missingFiles" :key="path" class="selected-file-card" style="padding: 4px; border-radius: 3px; margin-bottom: 4px; font-size: 0.85rem;">
                                <button @click="removeMissing(path)" class="delete has-background-danger is-small mr-2">
                                </button>
                                <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1;" :title="path">
                                    {{ file.name }}
                                </span>
                                <button @click="startReplaceMissing(path, file)" class="button is-small is-light" title="Find this file">
                                    <span class="icon is-small"><i class="bx bx-search"></i></span><span>Find</span>
                                </button>
                            </li>
                        </ul>
                    </div>

                </div>

            </div>
    `
};
