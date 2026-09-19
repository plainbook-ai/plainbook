// Compile-check the Vue templates embedded in the client components.
//
// Each component in plainbook/js/ carries its markup in a `template:` tagged
// template string. Node's own parser only sees a string literal, so an
// unbalanced tag or a malformed directive is valid JavaScript and slips
// through. This runs each template through the real Vue template compiler,
// which is what the browser does at runtime, and reports what it complains
// about with file line numbers.
//
// Usage:  npm run check          (from dev-tools/)
//         node check-templates.mjs [dir]
//
// Exits non-zero if any template fails to compile.

import { compile } from '@vue/compiler-dom';
import { readFileSync, readdirSync } from 'node:fs';
import { join, dirname, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const dir = resolve(process.argv[2] || join(here, '..', 'plainbook', 'js'));

// Matches `template: /* html */ \`` (the comment is optional).
const TEMPLATE_RE = /template:\s*(?:\/\*\s*html\s*\*\/\s*)?`/;

// Returns { text, offset } for the component's template literal, where offset
// is the number of source lines before it, or null if the file has no template.
function extractTemplate(src) {
    const m = TEMPLATE_RE.exec(src);
    if (!m) return null;
    const start = m.index + m[0].length;
    let end = start;
    // Scan to the closing backtick, skipping escaped ones.
    while (end < src.length && !(src[end] === '`' && src[end - 1] !== '\\')) end++;
    return { text: src.slice(start, end), offset: src.slice(0, start).split('\n').length - 1 };
}

let checked = 0;
const failures = [];

for (const name of readdirSync(dir).filter(f => f.endsWith('.js')).sort()) {
    const path = join(dir, name);
    const found = extractTemplate(readFileSync(path, 'utf8'));
    if (!found) continue;   // plain module, no component template
    checked++;

    // Collect every error rather than throwing on the first, so one bad file
    // reports all of its problems in a single run.
    const errors = [];
    compile(found.text, { onError: e => errors.push(e) });

    if (errors.length === 0) {
        console.log(`  ok    ${name}`);
    } else {
        for (const e of errors) {
            const line = e.loc ? found.offset + e.loc.start.line : '?';
            const col = e.loc ? e.loc.start.column : '?';
            failures.push(`${relative(process.cwd(), path)}:${line}:${col}  ${e.message}`);
        }
        console.log(`  FAIL  ${name}  (${errors.length} error${errors.length > 1 ? 's' : ''})`);
    }
}

console.log(`\n${checked} template${checked === 1 ? '' : 's'} checked, ${failures.length} error${failures.length === 1 ? '' : 's'}`);
if (failures.length) {
    console.log('');
    for (const f of failures) console.log(f);
    process.exit(1);
}
