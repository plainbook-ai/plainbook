# Development tools

**For testing and development purposes only.** Nothing in this folder is part
of the Plainbook package: it is not imported by the server or the client, and
it is excluded from the built distribution (`pyproject.toml` packages only
`plainbook*`). It is safe to ignore this folder entirely unless you are working
on the client code.

To install, do:

	npm install

## check-templates.mjs

Compile-checks the Vue templates embedded in the components in `plainbook/js/`.

Each component keeps its markup in a `template:` tagged template string. To
JavaScript that is just a string, so `node --check` — and any ordinary linter —
will happily accept a template with an unbalanced tag or a malformed directive.
This tool feeds each template to the same Vue compiler the browser uses at
runtime, so those problems surface before they reach the page.

To run, do:

	npm run check

It prints one line per component and exits non-zero if any template fails, so
it can be wired into a pre-commit hook or CI. To check a different directory:

	node check-templates.mjs ../some/other/dir

Note that these are compile-time checks on the markup only. They say nothing
about whether the bindings a template refers to actually exist in the
component's `setup()`, and they do not run the application.
