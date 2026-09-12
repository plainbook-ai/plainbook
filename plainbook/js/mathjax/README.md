# Vendored MathJax

`tex-svg-full.js` is MathJax **3.2.2**, file `es5/tex-svg-full.js` from the npm package
(https://registry.npmjs.org/mathjax/-/mathjax-3.2.2.tgz), licensed under Apache-2.0 (see `LICENSE`).

Plainbook must work with no internet access, so MathJax is served from here rather than from a CDN.
This particular build was chosen because it is a single self-contained file: TeX input, SVG output,
every TeX extension, and the fonts (as SVG paths) are all embedded, so MathJax never fetches anything
at runtime. (MathJax 4 splits the fonts into a separate package that is loaded dynamically, which is
why it was not used.) The context menu is disabled in the page configuration, since its accessibility
explorer would try to load the speech-rule-engine from a CDN.

The TeX `$...$` / `$$...$$` delimiters are recognised by `js/markdown.js`, which lifts the math out of
the Markdown before markdown-it can alter it and hands it to MathJax as `\(...\)` / `\[...\]`.

## Updating

    cd /tmp && npm pack mathjax@<version> && tar xzf mathjax-<version>.tgz
    cp package/es5/tex-svg-full.js package/LICENSE <plainbook>/plainbook/js/mathjax/

Then update the version above.
