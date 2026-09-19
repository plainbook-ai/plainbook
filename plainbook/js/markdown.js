// Markdown rendering shared by every component that shows Markdown, with
// TeX math support.
//
// markdown-it rewrites characters that are common inside formulas (`*` becomes
// emphasis, `\\` and `\{` lose their backslash, `<` can start a tag), so math
// has to be lifted out before inline parsing.  The `math` rule below does that
// for `$...$`, `$$...$$`, `\(...\)` and `\[...\]` and emits the formula,
// HTML-escaped, in the `\(...\)` / `\[...\]` delimiters MathJax looks for (see
// the MathJax config in views/index.html).  MathJax itself is loaded locally
// from js/mathjax/ and typesets each rendered element through the `v-mathjax`
// directive.

// Delimiters, in the order they are tried (`$$` before `$` so they pair up).
const DELIMITERS = [
    { open: '$$', close: '$$', display: true },
    { open: '\\[', close: '\\]', display: true },
    { open: '\\(', close: '\\)', display: false },
    { open: '$', close: '$', display: false },
];

function isSpace(code) {
    return code === 0x20 || code === 0x09 || code === 0x0A || code === 0x0D;
}

function isDigit(code) {
    return code >= 0x30 && code <= 0x39;
}

// Finds the closing delimiter for math whose content starts at `start` and
// returns its position, or -1.  For single `$`, Pandoc's rule tells `$x$`
// apart from prices such as "$5 and $10": the closing `$` must not be preceded
// by whitespace nor followed by a digit.
function findClosing(src, start, max, delim) {
    const strict = delim.close === '$';
    let pos = start;
    while (pos < max) {
        pos = src.indexOf(delim.close, pos);
        if (pos < 0 || pos + delim.close.length > max) return -1;
        const prev = src.charCodeAt(pos - 1);
        const next = src.charCodeAt(pos + delim.close.length);
        const closes = pos > start && (!strict ||
            (!isSpace(prev) && !(pos + delim.close.length < max && isDigit(next))));
        if (closes) return pos;
        pos += delim.close.length;
    }
    return -1;
}

function mathRule(state, silent) {
    const src = state.src;
    const start = state.pos;
    const max = state.posMax;
    const first = src.charCodeAt(start);
    if (first !== 0x24 /* $ */ && first !== 0x5C /* \ */) return false;

    const delim = DELIMITERS.find(d => src.startsWith(d.open, start));
    if (!delim) return false;
    const contentStart = start + delim.open.length;
    if (contentStart >= max) return false;
    if (delim.open === '$') {
        // Pandoc: the opening `$` must not be followed by whitespace, and a `$`
        // right after a digit (as in "1$") is part of a number.
        if (isSpace(src.charCodeAt(contentStart))) return false;
        if (start > 0 && isDigit(src.charCodeAt(start - 1))) return false;
    }

    const end = findClosing(src, contentStart, max, delim);
    if (end < 0) return false;

    if (!silent) {
        const token = state.push('math', '', 0);
        token.content = src.slice(contentStart, end);
        token.display = delim.display;
    }
    state.pos = end + delim.close.length;
    return true;
}

function mathPlugin(md) {
    // Before `escape`, which would otherwise turn `\(` into `(`.  Code spans
    // are unaffected: `backticks` consumes them whole, so a `$x$` inside one
    // is never seen by this rule.
    md.inline.ruler.before('escape', 'math', mathRule);
    md.renderer.rules.math = (tokens, idx) => {
        const token = tokens[idx];
        const tex = md.utils.escapeHtml(token.content);
        return token.display
            ? `<span class="math">\\[${tex}\\]</span>`
            : `<span class="math">\\(${tex}\\)</span>`;
    };
}

// Returns a markdown-it instance (with the given markdown-it options) that
// understands TeX math.
export function createMarkdown(options) {
    return window.markdownit(options).use(mathPlugin);
}

// Typesets the math inside `el` with MathJax, once MathJax has loaded.  A page
// without MathJax simply shows the `\(...\)` delimiters as text.
async function typeset(el) {
    const mj = window.MathJax;
    if (!mj || !mj.startup) return;
    try {
        await mj.startup.promise;
        mj.typesetClear([el]);
        await mj.typesetPromise([el]);
    } catch (e) {
        console.warn('MathJax typesetting failed:', e);
    }
}

// `v-mathjax`: use next to `v-html` on any element that shows rendered
// Markdown.  Registered with `app.directive('mathjax', mathjaxDirective)`.
export const mathjaxDirective = {
    mounted: typeset,
    updated: typeset,
};
