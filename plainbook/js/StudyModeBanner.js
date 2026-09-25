// StudyModeBanner.js
// Shown at the top of the notebook when the server runs with --unit-tests-only.
// Without it a participant meets a notebook whose controls have quietly gone,
// with nothing to say why; the mode is a deliberate restriction, so it should
// announce itself.
// Not dismissible: it describes how the whole session works, not a transient
// condition, and it is the only place the rule is written down.

export default {
    template: /* html */ `
        <article class="message is-info study-mode-banner mb-4">
            <div class="message-header py-1">
                <p>
                    <span class="icon"><i class="bx bx-medical-flask"></i></span>
                    <span>Unit-test mode</span>
                </p>
            </div>
            <div class="message-body py-2">
                <p>
                    This notebook is fixed: its cells cannot be edited, added,
                    removed or reordered, and its code is not regenerated.
                    You can add and run unit tests on any cell with the
                    <strong>Test</strong> button, and you can run the notebook to
                    see what it does.
                </p>
            </div>
        </article>
    `
};
