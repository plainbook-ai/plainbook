// MissingModuleBar.js
// Bar shown at the top of a cell's output when execution failed with a
// ModuleNotFoundError. Offers to install the missing package (via pip in
// the kernel), to rewrite the code without it, or to do nothing.
// `install` is the installation state owned by nb.js:
//   null/undefined                                -> show the question
//   { status: 'installing' }                      -> show progress
//   { status: 'done', success, output }           -> show pip's report

export default {
    props: ['moduleName', 'install', 'running', 'isLocked'],
    emits: ['install', 'rewrite', 'dismiss'],
    template: /* html */ `
        <article class="message is-warning missing-module-bar mb-3">
            <div class="message-header py-1">
                <p>
                    <span class="icon"><i class="bx bx-error"></i></span>
                    <span>Python module missing: install?</span>
                </p>
            </div>
            <div class="message-body py-2">
                <template v-if="!install">
                    <p class="mb-2">
                        The code generated tries to use the module
                        <code>{{ moduleName }}</code>, which is not currently
                        installed. Would you like to install it?
                    </p>
                    <div class="buttons are-small mb-0">
                        <button class="button is-small is-primary"
                                :disabled="running || isLocked"
                                @click.stop="$emit('install')">
                            <span class="icon"><i class="bx bx-arrow-down-square"></i></span>
                            <span>Yes, install it</span>
                        </button>
                        <button class="button is-small is-info"
                                :disabled="running || isLocked"
                                @click.stop="$emit('rewrite')">
                            <span class="icon"><i class="bx bx-cognition"></i></span>
                            <span>No, try to rewrite the code without using the package</span>
                        </button>
                        <button class="button is-small"
                                @click.stop="$emit('dismiss')">
                            <span class="icon"><i class="bx bx-x"></i></span>    
                            <span>Do nothing (I will install it)</span>
                        </button>
                    </div>
                </template>
                <template v-else-if="install.status === 'installing'">
                    <p>
                        <span class="icon"><i class="bx bx-loader-alt bx-spin"></i></span>
                        <span>Installing <code>{{ moduleName }}</code>&hellip;</span>
                    </p>
                </template>
                <template v-else>
                    <p class="mb-2 has-text-weight-bold"
                       :class="install.success ? 'has-text-success' : 'has-text-danger'">
                        <span v-if="install.success">Installation succeeded. Run the cell again to continue.</span>
                        <span v-else>Installation failed.</span>
                    </p>
                    <pre class="is-family-monospace is-size-7 p-2"
                         style="max-height: 14rem; overflow: auto; white-space: pre-wrap; word-break: break-word;">{{ install.output }}</pre>
                    <div class="buttons are-small mb-0 mt-2">
                        <button class="button is-small" @click.stop="$emit('dismiss')">
                            <span>Close</span>
                        </button>
                    </div>
                </template>
            </div>
        </article>
    `
};
