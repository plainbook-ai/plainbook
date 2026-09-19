// errorUtils.js
// Shared helpers so every part of the UI agrees on what counts as "an error"
// in a cell's outputs. Besides formal `output_type === 'error'` outputs, we
// also treat error-like stderr streams (e.g. an uncaught traceback or a pandas
// warning printed to stderr) as an error state.

// A stderr stream is considered error-like when its text mentions a class name
// ending in Error/Warning/Exception, or a Python traceback header.
const ERROR_LIKE_RE = /\b\w*(?:Error|Warning|Exception)\b|Traceback \(most recent call last\)/;
// The subset of the above that means something actually went wrong. A stream
// that matches ERROR_LIKE_RE but not this one is only a warning (a pandas
// DtypeWarning, say): advisory, so it must not stop a run or raise the
// app-level error bar, even though it still offers "Fix Code" on the cell.
const HARD_ERROR_RE = /\b\w*(?:Error|Exception)\b|Traceback \(most recent call last\)/;
// Extracts "SomeError: message" from stderr / traceback text.
const ERROR_TYPE_RE = /(\w*(?:Error|Warning|Exception))\s*:\s*([\s\S]*)/;

function joinText(t) {
    return Array.isArray(t) ? t.join('') : (t || '');
}

// True when `out` is a stderr stream whose text looks like an error/warning.
export function isErrorLikeStderr(out) {
    return !!out
        && out.output_type === 'stream'
        && out.name === 'stderr'
        && ERROR_LIKE_RE.test(joinText(out.text));
}

// True when any output is a formal error or an error-like stderr stream.
export function outputsHaveError(outputs) {
    if (!outputs) return false;
    return outputs.some(o => o.output_type === 'error' || isErrorLikeStderr(o));
}

// True when `out` is a stderr stream reporting a real failure, not just a warning.
export function isHardErrorStderr(out) {
    return isErrorLikeStderr(out) && HARD_ERROR_RE.test(joinText(out.text));
}

// True when `out` is a stderr stream carrying a warning and nothing worse.
// Advisory: it neither stops a run nor renders in the full error colours.
export function isWarningOnlyStderr(out) {
    return isErrorLikeStderr(out) && !isHardErrorStderr(out);
}

// True when any output should stop a run: a formal error output, or stderr that
// is more than a warning. Deliberately narrower than outputsHaveError(): a cell
// that only warned still ran, so the run carries on and no error bar appears,
// while the cell keeps offering "Fix Code" for the warning.
export function outputsHaveStoppingError(outputs) {
    if (!outputs) return false;
    return outputs.some(o => o.output_type === 'error' || isHardErrorStderr(o));
}

// Returns { ename, evalue } for the first error in `outputs`, or null.
// Prefers a formal error output; otherwise parses the first error-like stderr.
export function getErrorInfo(outputs) {
    if (!outputs) return null;
    const err = outputs.find(o => o.output_type === 'error');
    if (err) {
        return { ename: err.ename || 'Error', evalue: err.evalue || '' };
    }
    const se = outputs.find(isErrorLikeStderr);
    if (se) {
        const text = joinText(se.text).trim();
        const m = text.match(ERROR_TYPE_RE);
        if (m) return { ename: m[1], evalue: m[2].trim() };
        return { ename: 'Error', evalue: text };
    }
    return null;
}
