// Shared wrapper around fetch() that gives a clear, uniform message when the
// Plainbook server isn't there at all (not started, stopped, or the page was
// restored from cache after the server exited).
//
// A dead server makes fetch() reject before any HTTP response exists, so the
// rejection itself is the signal — we never match on the message text, since
// browsers disagree on it ("Failed to fetch" / "NetworkError when attempting
// to fetch resource." / "Load failed").

// No "Error:" prefix here: UiError.js and index.html already render one.
export const SERVER_DOWN_MESSAGE = "Plainbook server is not responding.";

/**
 * fetch(), but a transport-level failure throws a tagged, human-readable error.
 * Only the fetch() call is wrapped: a later response.json() failure means the
 * server did answer, which is a different problem and keeps its own message.
 */
export const serverFetch = async (url, options) => {
    try {
        return await fetch(url, options);
    } catch (err) {
        throw Object.assign(new Error(SERVER_DOWN_MESSAGE), {
            isServerDown: true,
            cause: err,
        });
    }
};

/**
 * True if err, or anything in its cause chain, is a server-down error. Callers
 * often re-wrap ("Failed to fetch files", "Error in loading notebook"), so the
 * flag has to be looked for down the chain, not just on the outermost error.
 */
export const isServerDown = (err) => {
    for (let e = err; e; e = e.cause) {
        if (e.isServerDown) return true;
    }
    return false;
};
