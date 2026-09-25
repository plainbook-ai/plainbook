import atexit
import copy
import datetime
import hashlib
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import uuid

import machineid
import nbformat
import requests

from .ai_common import (get_session_tokens, DEFAULT_EXPLANATION_DETAIL_LEVEL,
                        DEFAULT_EXPLANATION_USE_BULLETS, DEFAULT_EXPLANATION_USE_LATEX)
from .utilities import PIP_INSTALL_CODE, parse_pip_install_result, resolve_package_name
from .gemini import gemini_generate_code, gemini_validate_code, gemini_explain_code, gemini_generate_cell_name, gemini_generate_test_code, gemini_generate_unit_test_code, gemini_verify_notebook, gemini_verify_tests, gemini_fold_additions, gemini_amend_explanation
from .claude import claude_generate_code, claude_validate_code, claude_explain_code, claude_generate_cell_name, claude_generate_test_code, claude_generate_unit_test_code, claude_verify_notebook, claude_verify_tests, claude_fold_additions, claude_amend_explanation
from .openai import openai_generate_code, openai_validate_code, openai_explain_code, openai_generate_cell_name, openai_generate_test_code, openai_generate_unit_test_code, openai_verify_notebook, openai_verify_tests, openai_fold_additions, openai_amend_explanation
from .local_gpt_oss import local_generate_code, local_validate_code, local_explain_code, local_generate_cell_name, local_generate_test_code, local_generate_unit_test_code, local_verify_notebook, local_verify_tests, local_fold_additions, local_amend_explanation

AI_PROVIDERS = {
    "gemini": {"generate": gemini_generate_code, "validate": gemini_validate_code, "explain": gemini_explain_code, "name": gemini_generate_cell_name, "generate_test": gemini_generate_test_code, "generate_unit_test": gemini_generate_unit_test_code, "verify_notebook": gemini_verify_notebook, "verify_tests": gemini_verify_tests, "fold": gemini_fold_additions, "amend_explanation": gemini_amend_explanation},
    "claude": {"generate": claude_generate_code, "validate": claude_validate_code, "explain": claude_explain_code, "name": claude_generate_cell_name, "generate_test": claude_generate_test_code, "generate_unit_test": claude_generate_unit_test_code, "verify_notebook": claude_verify_notebook, "verify_tests": claude_verify_tests, "fold": claude_fold_additions, "amend_explanation": claude_amend_explanation},
    "openai": {"generate": openai_generate_code, "validate": openai_validate_code, "explain": openai_explain_code, "name": openai_generate_cell_name, "generate_test": openai_generate_test_code, "generate_unit_test": openai_generate_unit_test_code, "verify_notebook": openai_verify_notebook, "verify_tests": openai_verify_tests, "fold": openai_fold_additions, "amend_explanation": openai_amend_explanation},
    # A model running on this machine (see local_models.py); no API key.
    "local": {"generate": local_generate_code, "validate": local_validate_code, "explain": local_explain_code, "name": local_generate_cell_name, "generate_test": local_generate_test_code, "generate_unit_test": local_generate_unit_test_code, "verify_notebook": local_verify_notebook, "verify_tests": local_verify_tests, "fold": local_fold_additions, "amend_explanation": local_amend_explanation},
}

MAX_OUTPUT_CHARS_FOR_AI = 2000


def normalize_notebook_name(new_name):
    """The bare notebook name from user input.

    Takes the basename (a typed path is not a way to write elsewhere) and drops a
    trailing .plnb/.ipynb if the user typed one, so the caller can append the
    canonical extension itself. Raises ValueError when nothing is left. Shared by
    rename() and by the new-notebook route, so both validate identically."""
    name = os.path.basename((new_name or '').strip())
    for ext in ('.plnb', '.ipynb'):
        if name.lower().endswith(ext):
            name = name[:-len(ext)]
            break
    name = name.strip()
    if not name:
        raise ValueError("Please provide a name for the notebook.")
    return name


def unique_notebook_path(folder, name):
    """The (name, path) to use for a new .plnb in `folder`, avoiding collisions.

    If `name`.plnb is taken, tries name_2, name_3, ... Returns the name actually
    chosen together with its full path, so callers can report the real name back
    to the user. Shared by rename(), save_copy() and the new-notebook route, so
    that naming a notebook never fails just because the name is in use."""
    candidate = name
    n = 1
    while os.path.exists(os.path.join(folder, candidate + ".plnb")):
        n += 1
        candidate = f"{name}_{n}"
    return candidate, os.path.join(folder, candidate + ".plnb")


def check_notebook_file(path):
    """Raise ValueError unless `path` is a file we can open as a notebook.

    Called before opening a notebook the user picked, from the process that can
    still tell them what went wrong: a file that cannot be loaded must be
    reported here, not discovered by a child process that dies silently. The
    messages are user-facing.

    The question asked is only "can nbformat load it?", which is exactly what
    the Plainbook constructor will ask. It is deliberately not a strict
    validation: nbformat logs schema violations rather than raising, which is
    what lets our own 'test' cell type round-trip."""
    if not os.path.exists(path):
        raise ValueError(f"There is no file at {path}.")
    if os.path.isdir(path):
        raise ValueError(f"{os.path.basename(path)} is a folder, not a notebook.")
    try:
        nbformat.read(path, as_version=4)
    except Exception as e:
        # Deliberately broad: a file can fail to be a notebook in many ways
        # (bad JSON, no 'cells', a top-level array, an unreadable encoding),
        # and each nbformat version raises its own assortment of types.
        raise ValueError(
            f"{os.path.basename(path)} is not a notebook file.") from e


class ExecutionError(Exception):
    """Custom exception for execution errors in Plainbook."""
    pass

class CellExecutionError(Exception):
    """Raised when a cell execution produces a runtime error."""
    def __init__(self, traceback="", ename="", evalue=""):
        self.traceback = traceback
        self.ename = ename
        self.evalue = evalue
        super().__init__(f"{ename}: {evalue}")

class ClarificationNeeded(Exception):
    """Raised when the AI asks questions instead of generating code. The cell is
    left unchanged."""
    def __init__(self, questions):
        self.questions = questions
        super().__init__("The AI needs clarification before generating code.")

def getlist(value):
    """Utility to ensure a value is a list."""
    if isinstance(value, list):
        return value
    else:
        return [value]

def tostring(value):
    """Utility to ensure a value is a string."""
    if isinstance(value, str):
        return value
    elif isinstance(value, list):
        return "".join(value)
    else:
        return str(value)

# What counts as "this cell is in error". Besides a formal error output, an
# error-like stderr stream counts too: an uncaught traceback or a warning that
# the code printed to stderr rather than raised. Kept deliberately in step with
# outputsHaveError() in js/errorUtils.js — the client uses that to decide
# whether to offer the "Fix Code" button, and the server uses this to decide
# whether there is an error to fix. If the two disagree, the button appears for
# an error the server does not see, and the fix silently does nothing.
ERROR_LIKE_RE = re.compile(
    r"\b\w*(?:Error|Warning|Exception)\b|Traceback \(most recent call last\)")


def is_error_like_stderr(output):
    """True when `output` is a stderr stream whose text looks like an error."""
    return (output.get('output_type') == 'stream'
            and output.get('name') == 'stderr'
            and bool(ERROR_LIKE_RE.search(tostring(output.get('text', '')))))


def outputs_have_error(outputs):
    """True when any output is a formal error or an error-like stderr stream."""
    return any(o.get('output_type') == 'error' or is_error_like_stderr(o)
               for o in getlist(outputs or []))


VARIABLE_INSPECTION_CODE = """
import json
import types

def _get_var_info():
    pd = None
    try: import pandas as pd
    except: pass
    np = None
    try: import numpy as np
    except: pass

    var_info = {}
    for name, obj in list(globals().items()):
        if name.startswith('_') or isinstance(obj, types.ModuleType) or \
           isinstance(obj, types.FunctionType) or name == 'VARIABLE_INSPECTION_CODE':
            continue
        try:
            info = {"type": type(obj).__name__}
            if pd and isinstance(obj, pd.DataFrame):
                info["columns"] = [{"name": str(c), "dtype": str(d)} for c, d in obj.dtypes.items()]
                info["shape"] = obj.shape
            elif pd and isinstance(obj, pd.Series):
                info["dtype"] = str(obj.dtype)
                info["len"] = len(obj)
            elif np and isinstance(obj, np.ndarray):
                info["shape"] = obj.shape
                info["dtype"] = str(obj.dtype)
            elif hasattr(obj, '__len__') and not isinstance(obj, (str, bytes)):
                info["len"] = len(obj)
            var_info[name] = info
        except:
            continue
    return var_info

print(json.dumps(_get_var_info()))
"""

PREVIOUS_CODE_EXPLANATION_CHANGED = """
PREVIOUS CODE CELL:
This is the previous code for the cell.
The explanation of what needs generating has changed, so the code needs to be revised.

{code_string}
"""

PREVIOUS_CODE_NEEDS_REVISION = """
PREVIOUS CELL CODE:
This is the previous code for the cell; it might need revision as some of the previous code may have changed.

{code_string}
"""


def _generate_random_name():
    """Generates a random pronounceable name like 'bakace_runabi'."""
    import random
    vowels = 'aeiou'
    consonants = 'bcdfghjklmnpqrstvwxyz'
    def _random_word():
        return ''.join(random.choice(consonants) + random.choice(vowels) for _ in range(3))
    return _random_word() + '_' + _random_word()


class _LiveCellMeta:
    """Per-cell, session-only skip metadata that is NOT serialized to the .plnb.

    Same category as Plainbook._cell_states: it is relative to the live kernel
    and is rebuilt each session, so it is kept off cell.metadata (which nbformat
    writes to disk) and stored on the Plainbook, keyed by cell.id. __slots__ is
    the single source of truth for the set of ephemeral keys.

    output_hash is the hash of the source that produced the cell's currently
    stored output — whatever that output is, including an error and including
    nothing — or None when no stored output belongs to the current source. The
    execution-skip runs the cell for real as soon as it stops matching the
    cell's current source."""
    __slots__ = ('output_hash', 'input_group_fingerprints', 'accessed_symbols',
                 'accessed_symbol_hashes', 'modified_symbols', 'deleted_symbols')

    def __init__(self):
        for k in self.__slots__:
            setattr(self, k, None)


class Plainbook:
    """Plainbook implementation backed by the snapshot kernel."""

    def __init__(self, notebook_path, debug=False, dump_ai_requests=False,
                 unit_tests_only=False):
        print(f"Starting Plainbook for {notebook_path}...")
        self.path = notebook_path
        self.debug = debug
        self.dump_ai_requests = dump_ai_requests
        # User-study mode (--unit-tests-only): the stored code of the notebook is
        # the artefact under test and must never be regenerated. See
        # _pin_code_validity for why pinning, rather than merely refusing
        # generation, is what makes that work.
        self.unit_tests_only = unit_tests_only
        self.name = os.path.splitext(os.path.basename(notebook_path))[0]
        self.nb = None
        self._lock = threading.Lock()
        # Status variables.
        self.last_executed_cell = -1
        self.last_valid_code_cell = -1
        self.last_valid_output_cell = -1
        self.last_valid_test_cell = -1
        # Loads the notebook from disk.
        self._load_notebook()
        if unit_tests_only:
            # _filter_input_files is skipped deliberately: it invalidates every
            # cell citing a file that is missing on THIS machine, which on a
            # study notebook opened on a participant's laptop would mark the
            # cells stale and have the first run regenerate them.
            self._pin_code_validity()
        else:
            self._filter_input_files()
        # AI request tracker, so we can interrupt if needed.
        self.ai_request_pending = False
        # Start the snapshot kernel.
        self._sk_token = secrets.token_hex(16)
        self._sk_port = self._find_free_port(start=9100)
        self._sk_base_url = f"http://127.0.0.1:{self._sk_port}"
        self._current_exec_id = None
        self._cell_states = {}
        self._live_states = set()        # kernel state names created this session (for execution-skip)
        self._live_cell_meta = {}        # cell.id -> _LiveCellMeta (session-only skip metadata, not serialized)
        self._unit_test_states = {}     # "{cell_id}:{test_name}:{role}" -> kernel state name
        # Keep generation and execution counters. 
        self._requested_generations = 0
        self._performed_generations = 0
        self._requested_executions = 0
        self._performed_executions = 0
        # Unit test validity is stored inline in cell.metadata.unit_tests[name]['validity']
        self._sk_process = subprocess.Popen(
            [sys.executable, "-m", "snapshot_kernel.main",
             "--bind", f"127.0.0.1:{self._sk_port}",
             "--token", self._sk_token],
            stdout=None if debug else subprocess.PIPE,
            stderr=None if debug else subprocess.PIPE,
        )
        self._wait_for_server()
        self.default_variables = self._get_variables()
        atexit.register(self._shutdown)

    # Compatibility properties for main.py assertions

    @property
    def kc(self):
        return self

    @property
    def km(self):
        return self

    def is_alive(self):
        return self._sk_process is not None and self._sk_process.poll() is None

    # Snapshot kernel HTTP helpers

    def _sk_request(self, method, path, json_body=None):
        """Send a request to the snapshot kernel server."""
        url = f"{self._sk_base_url}{path}"
        params = {"token": self._sk_token}
        resp = requests.request(method, url, params=params, json=json_body, timeout=300)
        resp.raise_for_status()
        return resp.json()

    def _find_free_port(self, start=9100):
        """Scan for a free port starting from start."""
        port = start
        while True:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(('127.0.0.1', port))
                    return port
                except OSError:
                    port += 1

    def _wait_for_server(self, timeout=10):
        """Poll GET /states until the snapshot kernel server is ready."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                self._sk_request("GET", "/states")
                if self.debug:
                    print(f"Snapshot kernel server ready on port {self._sk_port}")
                return
            except Exception:
                time.sleep(0.2)
        raise RuntimeError(
            f"Snapshot kernel server failed to start within {timeout}s on port {self._sk_port}"
        )

    def _find_input_state(self, index):
        """Walk backwards to find the snapshot state name to execute cell `index` against.
        Returns 'initial' if no previous code cell has been executed."""
        for i in range(index - 1, -1, -1):
            cell = self.nb.cells[i]
            if cell.cell_type == 'code' and i <= self.last_executed_cell:
                state = self._cell_states.get(cell.id)
                if state:
                    return state
        return "initial"

    @staticmethod
    def _hash_text(text):
        """SHA-256 hex digest of a text field (treats None as empty)."""
        return hashlib.sha256((text or "").encode("utf-8")).hexdigest()

    def _live(self, cell):
        """Return the cell's session-only skip metadata (a _LiveCellMeta),
        creating it on first access. Not serialized (kept off cell.metadata)."""
        lm = self._live_cell_meta.get(cell.id)
        if lm is None:
            lm = self._live_cell_meta[cell.id] = _LiveCellMeta()
        return lm

    def _code_matches_description(self, cell):
        """True if the cell's code was generated from its current description
        (the stored code_description_hash equals the current description_hash)."""
        dh = cell.metadata.get('description_hash')
        ch = cell.metadata.get('code_description_hash')
        return bool(dh) and dh == ch

    def _refresh_code_hash(self, cell):
        """Store the hash of the cell's current source code, and drop the AI code
        explanation if the code it was written for has changed. Called wherever
        new source is produced (AI generation, manual edit, clear). Returns True
        iff an explanation was cleared."""
        cell.metadata['code_hash'] = self._hash_text(cell.source)
        if cell.metadata.get('ai_code_explanation') is None:
            return False
        if cell.metadata.get('code_hash_for_code_explanation') == cell.metadata['code_hash']:
            return False              # explanation still describes the current code
        for k in ('ai_code_explanation', 'ai_code_explanation_timestamp',
                  'code_hash_for_code_explanation'):
            cell.metadata.pop(k, None)
        return True

    def _drop_outputs(self, cell):
        """Discard a cell's stored output and the execution-skip's claim on it.

        output_hash names the source that produced the stored output. Discarding
        the output leaves nothing for a skip to reuse, and an empty output list
        is a legal result in its own right (a cell like `v = 1` produces none),
        so the hash cannot encode the difference: it has to be cleared
        explicitly. Otherwise _try_skip_execution "succeeds" by handing back the
        empty output and marking the cell executed and up to date."""
        cell.outputs = []
        self._live(cell).output_hash = None

    def _accessed_vars_unchanged(self, cell, index):
        """True iff every symbol the cell read still hashes to the stored value in
        the cell's current input state. Conservative: returns False if the cell
        was never successfully executed or the hashes can't be obtained."""
        accessed = self._live(cell).accessed_symbols
        if accessed is None:
            return False              # never executed -> no baseline
        if not accessed:
            return True               # reads nothing pre-existing
        stored = self._live(cell).accessed_symbol_hashes or {}
        input_state = self._find_input_state(index)
        try:
            resp = self._sk_request("POST", "/symbol_hashes", {
                "state_name": input_state, "symbols": accessed, "hash_algo": "full",
            })
        except Exception:
            return False              # state evicted / kernel issue -> regenerate
        current = resp.get("hashes", {})
        return all(stored.get(s) == current.get(s) for s in accessed)

    def _skip_code_generation(self, cell, index):
        """Mark the code valid without calling AI, when it is byte-identical to
        what a regeneration would produce (description unchanged and accessed
        variables unchanged). Because nothing about the cell changed, this is a
        true no-op for the cell's output and execution state: the existing
        output stays valid (so the execution-skip can preserve it) and
        last_valid_output_cell / last_executed_cell are left untouched. Only the
        code-valid watermark advances. cell.source is left unchanged, which is
        also what keeps the execution-skip eligible: its key is the hash of the
        source, so leaving the source alone leaves the stored output valid."""
        cell.metadata['code_description_hash'] = cell.metadata.get('description_hash')
        cell.metadata['code_timestamp'] = datetime.datetime.now().isoformat()
        self.last_valid_code_cell = index
        self._write()
        return cell.source, True, None   # (code, success, amended) — same shape as real path

    # Unit test validity tracking

    _UT_CASCADE = ['setup_code', 'setup_output', 'target_output', 'test_code', 'test_output']
    _UT_STATE_ROLES = {'setup_output': 'setup', 'target_output': 'target', 'test_output': 'test'}

    def _ut_state_key(self, cell_index, test_name, role):
        return f"{self.nb.cells[cell_index].id}:{test_name}:{role}"

    def _get_ut_validity(self, cell_index, test_name):
        """Get or create validity dict for a unit test."""
        tests = self.nb.cells[cell_index].metadata.get('unit_tests', {})
        ut = tests[test_name]
        if 'validity' not in ut:
            ut['validity'] = {
                'setup_code_valid': False,
                'setup_output_valid': False,
                'target_output_valid': False,
                'test_code_valid': False,
                'test_output_valid': False,
            }
        return ut['validity']

    def _invalidate_unit_test(self, cell_index, test_name, from_point):
        """Cascade invalidation from from_point onward for a unit test."""
        v = self._get_ut_validity(cell_index, test_name)
        start = self._UT_CASCADE.index(from_point)
        for point in self._UT_CASCADE[start:]:
            v[point + '_valid'] = False
            if point in self._UT_STATE_ROLES:
                sk = self._ut_state_key(cell_index, test_name, self._UT_STATE_ROLES[point])
                if sk in self._unit_test_states:
                    try:
                        self._sk_request("DELETE", f"/states/{self._unit_test_states[sk]}")
                    except Exception:
                        pass
                    del self._unit_test_states[sk]

    def _invalidate_all_unit_tests(self, cell_index, from_point):
        """Invalidate all unit tests for a cell from from_point onward."""
        cell = self.nb.cells[cell_index]
        tests = cell.metadata.get('unit_tests', {})
        for test_name in tests:
            self._invalidate_unit_test(cell_index, test_name, from_point)

    def get_unit_test_state(self, cell_index):
        """Returns validity flags for all unit tests of a specific target cell."""
        cell = self.nb.cells[cell_index]
        tests = cell.metadata.get('unit_tests', {})
        result = {}
        for test_name in tests:
            v = self._get_ut_validity(cell_index, test_name)
            result[test_name] = {
                'setup': {'code_valid': v['setup_code_valid'], 'output_valid': v['setup_output_valid']},
                'target': {'output_valid': v['target_output_valid']},
                'test': {'code_valid': v['test_code_valid'], 'output_valid': v['test_output_valid']},
            }
        return result

    # Kernel methods

    def execute_cell(self, index, force=False):
        """Executes a code cell by index against the appropriate snapshot.

        ``force`` skips the execution fast path, so the cell really runs even
        when its code and inputs are unchanged. Set it for cells with inputs the
        skip cannot track (the current time, random numbers, external files)."""
        with self._lock:
            if index < 0 or index >= len(self.nb.cells):
                raise ExecutionError("Cell index out of range")
            if index > self.last_valid_code_cell:
                raise ExecutionError("Executed a cell that is not valid")
            cell = self.nb.cells[index]
            if cell.cell_type != 'code':
                return None, "Not a code cell"
            # Already executed with a still-valid output: hand it straight back.
            # A forced run is precisely the request to ignore this.
            if not force and index <= min(self.last_executed_cell, self.last_valid_output_cell):
                return cell.outputs, "Cached"
            # Checks that all intervening cells between last_executed_cell and index are non-code.
            for i in range(self.last_executed_cell + 1, index):
                if self.nb.cells[i].cell_type == 'code':
                    raise ExecutionError("Cannot execute cell out of order")

            self._requested_executions += 1
            input_state = self._find_input_state(index)
            cell_id = cell.id
            if cell_id in self._cell_states:
                new_state_name = self._cell_states[cell_id]
            else:
                new_state_name = uuid.uuid4().hex
                existing_names = set(self._cell_states.values())
                while new_state_name in existing_names:
                    new_state_name = uuid.uuid4().hex
                self._cell_states[cell_id] = new_state_name

            # Whether this cell has already run in this kernel. If it has, a real
            # re-execution invalidates everything after it (see the success path
            # below). A successful skip does not: it reproduces the same result,
            # so the states that followed remain correct.
            was_reexecution = index <= self.last_executed_cell

            # Fast path unless the caller forces a real run: if this cell's code
            # is unchanged and nothing it reads has changed, reconstruct its
            # successor state without re-executing.
            if not force:
                skipped = self._try_skip_execution(cell, index, input_state, new_state_name)
                if skipped is not None:
                    return skipped

            self._performed_executions += 1
            exec_id = uuid.uuid4().hex
            self._current_exec_id = exec_id
            try:
                result = self._sk_request("POST", "/execute", {
                    "code": cell.source,
                    "exec_id": exec_id,
                    "state_name": input_state,
                    "new_state_name": new_state_name,
                })
            finally:
                self._current_exec_id = None

            # Convert outputs to nbformat objects
            outputs = []
            for out in result.get("output", []):
                outputs.append(nbformat.from_dict(out))
            cell.outputs = outputs
            # The code that produced the output now stored. Recorded here rather
            # than in the success path below so that it covers failed runs too:
            # an error output came from this source just as much as a good one
            # did, and leaving the hash pointing at the last *successful* source
            # is what let the execution-skip reuse a result the current code no
            # longer matches. Recorded after the kernel call returns, not before
            # it is sent: if _sk_request raises, cell.outputs is untouched too,
            # so the pair stays consistent.
            self._live(cell).output_hash = self._hash_text(cell.source)

            if result.get("error"):
                err = result["error"]
                # Build an error output matching Jupyter format
                error_output = nbformat.from_dict({
                    "output_type": "error",
                    "ename": err.get("ename", "Error"),
                    "evalue": err.get("evalue", ""),
                    "traceback": err.get("traceback", []),
                })
                # Only append if not already in outputs
                if not any(o.get("output_type") == "error" for o in cell.outputs):
                    cell.outputs.append(error_output)
                self._write()
                raise CellExecutionError(
                    traceback="\n".join(err.get("traceback", [])),
                    ename=err.get("ename", "Error"),
                    evalue=err.get("evalue", ""),
                )

            # Success: update execution pointer.
            if was_reexecution:
                # This cell ran again (a Force Run, typically), so every state
                # after it was computed from its previous value and is stale.
                # The snapshots themselves are kept, as _invalidate_from
                # documents: they are rebuild sources for the execution-skip,
                # which re-checks its input fingerprints against the current
                # state and declines when they no longer match.
                self._invalidate_from(index + 1)
                self.last_valid_output_cell = min(self.last_valid_output_cell, index)
                self.last_valid_test_cell = min(self.last_valid_test_cell, index)
            self.last_executed_cell = index
            self.last_valid_output_cell = max(index, self.last_valid_output_cell)
            self._live_states.add(new_state_name)
            # Get variables for AI context
            cell.metadata['variables'] = self._get_variables()
            # Record when this cell was last successfully executed.
            cell.metadata['execution_timestamp'] = datetime.datetime.now().isoformat()
            # Record the reads/writes and the change-detection baselines used by
            # the generation-skip (per-variable read hashes) and the
            # execution-skip (input-state alias-group fingerprints).
            accessed = result.get("accessed_symbols") or []
            lm = self._live(cell)
            lm.accessed_symbols = accessed
            lm.modified_symbols = result.get("modified_symbols") or []
            lm.deleted_symbols = result.get("deleted_symbols") or []
            # output_hash is set above, for failed runs as well as this one.
            lm.accessed_symbol_hashes = self._read_hashes(input_state, accessed)
            lm.input_group_fingerprints = self._input_fingerprints(input_state)
            self._write()
            return cell.outputs, 'ok'

    def _read_hashes(self, state_name, symbols):
        """Per-variable content hashes of `symbols` in a state (for generation-skip)."""
        if not symbols:
            return {}
        try:
            resp = self._sk_request("POST", "/symbol_hashes", {
                "state_name": state_name, "symbols": symbols, "hash_algo": "full",
            })
            return resp.get("hashes", {})
        except Exception:
            return {}

    def _input_fingerprints(self, state_name):
        """Alias-group fingerprints of a state's variables (for execution-skip)."""
        try:
            resp = self._sk_request("POST", "/alias_groups", {"state_name": state_name})
            return resp.get("fingerprints", [])
        except Exception:
            return []

    def _try_skip_execution(self, cell, index, input_state, source_state):
        """Reconstruct a code cell's successor state without re-executing it, when
        that is provably equivalent to a real run. Returns (outputs, 'ok') on a
        successful skip, or None to fall through to a normal execution.

        Safe iff the code that produced the stored output is unchanged and every
        alias group the cell reads is unchanged (group fingerprints capture
        cross-variable sharing). The successor is rebuilt group-by-group: the
        cell's output region from the source state, the pass-through from the
        current input state (alias groups are disjoint, so this preserves all
        aliasing). See Plans/execution-skip-via-alias-groups.md.
        """
        lm = self._live(cell)
        # The stored output must have been produced by the code now in the cell.
        # Any change to the source — AI regeneration, a manual edit, an unfold —
        # breaks this and forces a real execution.
        if not lm.output_hash or lm.output_hash != self._hash_text(cell.source):
            return None
        # The cell must have run successfully before (baseline present) and its
        # previous successor state must still be live in the kernel.
        if lm.modified_symbols is None:
            return None
        if source_state not in self._live_states:
            return None
        # Never skip a cell that is currently in error. Two reasons, both needed:
        #  1. An error is not a reusable result. A cell that failed must re-run
        #     even when nothing about it changed, because what fixed it may be
        #     outside the notebook: a pip install (see install_package below,
        #     where the user re-runs the *unmodified* cell), a repaired input
        #     file, a network resource that came back.
        #  2. A failed run leaves stale baselines. output_hash correctly names
        #     the code that produced the error, so re-running unchanged code
        #     satisfies the check above, while modified_symbols and source_state
        #     are still those of the last *successful* run. Rebuilding the
        #     successor state from those would be wrong.
        if any(getattr(o, 'output_type', None) == 'error' for o in cell.outputs):
            return None

        accessed = lm.accessed_symbols or []
        baseline = set(lm.input_group_fingerprints or [])

        # Current input alias groups + fingerprints.
        try:
            cur = self._sk_request("POST", "/alias_groups", {"state_name": input_state})
        except Exception:
            return None
        cur_var_group = {}
        for group, fp in zip(cur.get("groups", []), cur.get("fingerprints", [])):
            for name in group:
                cur_var_group[name] = fp
        # Every alias group containing a read variable must be unchanged.
        for name in accessed:
            if name not in cur_var_group or cur_var_group[name] not in baseline:
                return None

        # --- Provably safe to skip: rebuild the successor state. ---
        touched = (set(accessed)
                   | set(lm.modified_symbols or [])
                   | set(lm.deleted_symbols or []))
        deleted = set(lm.deleted_symbols or [])
        # Output region: source variables whose source-group holds a touched var.
        try:
            src = self._sk_request("POST", "/alias_groups", {"state_name": source_state})
        except Exception:
            return None
        source_vars = set()
        for group in src.get("groups", []):
            if any(n in touched for n in group):
                source_vars.update(group)
        # Pass-through: current-input variables not taken from source, not deleted.
        input_vars = [n for n in cur_var_group
                      if n not in source_vars and n not in deleted]

        try:
            self._sk_request("POST", "/rebuild_state", {
                "input_state": input_state,
                "source_state": source_state,
                "source_vars": sorted(source_vars),
                "input_vars": sorted(input_vars),
                "new_state_name": source_state,
            })
        except Exception:
            return None

        # Externally identical to a real execution, minus the computation.
        self._live_states.add(source_state)
        self.last_executed_cell = index
        self.last_valid_output_cell = max(index, self.last_valid_output_cell)
        cell.metadata['execution_timestamp'] = datetime.datetime.now().isoformat()
        cell.metadata['variables'] = self._get_variables()
        # Refresh the change-detection baselines for the next run.
        lm.input_group_fingerprints = cur.get("fingerprints", [])
        lm.accessed_symbol_hashes = self._read_hashes(input_state, accessed)
        self._write()
        return cell.outputs, 'ok'

    def _get_variables(self, state_name=None):
        """Execute the variable inspection code against a given or last executed state."""
        if state_name is None:
            # Find the most recent valid state
            for i in range(len(self.nb.cells) - 1, -1, -1):
                cell = self.nb.cells[i]
                if cell.cell_type == 'code' and i <= self.last_executed_cell:
                    state_name = self._cell_states.get(cell.id)
                    if state_name:
                        break
        if not state_name:
            return {}

        temp_state = uuid.uuid4().hex
        try:
            result = self._sk_request("POST", "/execute", {
                "code": VARIABLE_INSPECTION_CODE,
                "exec_id": uuid.uuid4().hex,
                "state_name": state_name,
                "new_state_name": temp_state,
            })
            # Parse stdout from the output
            result_json = ""
            for out in result.get("output", []):
                if out.get("output_type") == "stream" and out.get("name") == "stdout":
                    result_json += out.get("text", "")
            # Clean up temp state
            try:
                self._sk_request("DELETE", f"/states/{temp_state}")
            except Exception:
                pass
            return json.loads(result_json)
        except (json.JSONDecodeError, TypeError, Exception):
            # Clean up temp state on error
            try:
                self._sk_request("DELETE", f"/states/{temp_state}")
            except Exception:
                pass
            return {}

    def _reset_kernel(self):
        """Reset the snapshot kernel: clear ALL states and reset execution.

        Deletes every kernel snapshot (via /reset), forgets the state-name and
        live-state maps (including the per-cell execution-skip baselines), resets
        the execution pointers, and clears outputs, so that after a restart every
        cell is genuinely re-executed (nothing is reconstructed). Persisted code
        metadata (code_hash/code_description_hash/description_hash) is preserved."""
        self._sk_request("POST", "/reset")
        self.last_executed_cell = -1
        self.last_valid_output_cell = -1
        self.last_valid_test_cell = -1
        self._cell_states.clear()
        self._live_states.clear()
        self._live_cell_meta.clear()
        self._unit_test_states.clear()
        for cell in self.nb.cells:
            if cell.cell_type in ('code', 'test'):
                cell.outputs = []
        self._write()
        if self.debug:
            print("Snapshot kernel reset complete.")

    def _invalidate_execution(self, index):
        """Mark execution invalid from cell index onward. Preserves earlier snapshots."""
        self._invalidate_from(index)

    def _invalidate_from(self, index):
        """Mark execution invalid from cell index onward (lower last_executed_cell).

        Snapshot states from *index* onward are intentionally kept: they are
        stale as *inputs* (guarded by last_executed_cell) but serve as rebuild
        *sources* for the execution-skip, and are overwritten on re-execution.
        """
        for i in range(index, len(self.nb.cells)):
            cell = self.nb.cells[i]
            # Invalidate unit tests for cells at or after the invalidation point
            if cell.metadata.get('unit_tests'):
                self._invalidate_all_unit_tests(i, 'setup_code')
        self.last_executed_cell = min(self.last_executed_cell, index - 1)

    def install_package(self, module_name):
        """Installs the pip package providing `module_name` by executing pip
        in the kernel (against the initial state, via a throwaway snapshot:
        pip changes the environment on disk, not the in-memory state).
        Returns (success, output_text)."""
        package = resolve_package_name(module_name)
        with self._lock:
            temp_state = uuid.uuid4().hex
            try:
                result = self._sk_request("POST", "/execute", {
                    "code": PIP_INSTALL_CODE % json.dumps(package),
                    "exec_id": uuid.uuid4().hex,
                    "state_name": "initial",
                    "new_state_name": temp_state,
                })
            finally:
                try:
                    self._sk_request("DELETE", f"/states/{temp_state}")
                except Exception:
                    pass
        stdout_text = ""
        for out in result.get("output", []):
            if out.get("output_type") == "stream" and out.get("name") == "stdout":
                stdout_text += tostring(out.get("text", ""))
        return parse_pip_install_result(stdout_text)

    def interrupt_kernel(self):
        """Interrupt the currently running execution."""
        exec_id = self._current_exec_id
        if exec_id:
            if self.debug:
                print(f"Interrupting execution {exec_id}...")
            try:
                self._sk_request("POST", "/interrupt", {"exec_id": exec_id})
            except Exception as e:
                if self.debug:
                    print(f"Error interrupting: {e}")

    def _shutdown(self):
        """Terminate the snapshot kernel subprocess."""
        if self.debug:
            print(f"Shutting down snapshot kernel for {self.name}...")
        if hasattr(self, '_sk_process') and self._sk_process:
            try:
                self._sk_process.terminate()
                self._sk_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._sk_process.kill()
                self._sk_process.wait()
            except Exception as e:
                print(f"Error shutting down snapshot kernel: {e}")

    # Notebook I/O

    def _load_notebook(self):
        """Loads the notebook from the specified path. If the file is missing, create an empty notebook."""
        try:
            with open(self.path) as f:
                self.nb = nbformat.read(f, as_version=4)
                for cell in self.nb.cells:
                    cell.source = tostring(cell.source)
                    if cell.cell_type in ('code', 'test'):
                        if 'explanation' not in cell.metadata:
                            cell.metadata['explanation'] = cell.source
                            cell.metadata['explanation_timestamp'] = datetime.datetime.now().isoformat()
                        else:
                            cell.metadata['explanation'] = tostring(cell.metadata['explanation'])
                        if cell.metadata.get('code_timestamp') is None:
                            cell.metadata['code_timestamp'] = datetime.datetime.now().isoformat()
                        if cell.metadata.get('explanation_timestamp') is None:
                            cell.metadata['explanation_timestamp'] = datetime.datetime.now().isoformat()
                        # Backfill the description hash so unchanged explanations
                        # can be recognized. code_description_hash is intentionally
                        # NOT backfilled (we can't assume old code matches its
                        # description, so it should regenerate on demand).
                        cell.metadata.setdefault(
                            'description_hash', self._hash_text(cell.metadata.get('explanation')))
                        # code_hash tracks the actual source (overwrite any legacy
                        # value that used this key for the description hash). Treat
                        # an existing explanation as valid for the loaded code
                        # (explanation + code were saved together).
                        cell.metadata['code_hash'] = self._hash_text(cell.source)
                        if cell.metadata.get('ai_code_explanation') is not None:
                            cell.metadata.setdefault(
                                'code_hash_for_code_explanation', cell.metadata['code_hash'])
                        if cell.cell_type == 'code':
                            # Present as null until the cell is first executed.
                            cell.metadata.setdefault('execution_timestamp', None)
                            # Migration: earlier versions serialized these
                            # session-only skip baselines into the file. They now
                            # live in self._live_cell_meta, so drop any stale
                            # copies rather than let them linger / be rewritten.
                            for k in _LiveCellMeta.__slots__:
                                cell.metadata.pop(k, None)
        except (FileNotFoundError, OSError):
            # Ensure parent directory exists
            parent = os.path.dirname(self.path) or "."
            os.makedirs(parent, exist_ok=True)
            # Create an empty notebook and persist it
            self.nb = nbformat.v4.new_notebook()
            self.nb.cells = []
            self.nb.metadata = {}
            self.nb.metadata['input_files'] = []
            self.nb.metadata['is_locked'] = False
            self.nb.metadata['share_output_with_ai'] = True
            self.nb.metadata['ai_instructions'] = ''
            with open(self.path, "w") as f:
                nbformat.write(self.nb, f)
        self.last_executed_cell = -1 # When we load, we need to re-execute from the start.
        self.last_valid_code_cell = self.nb.metadata.get('last_valid_code_cell', -1)
        self.last_valid_output_cell = self.nb.metadata.get('last_valid_output', -1)
        self.last_valid_test_cell = self.nb.metadata.get('last_valid_test_cell', -1)

        # Migrate cells written before amend: keep their additions as guidance.
        for cell in self.nb.cells:
            additions = cell.metadata.pop('additions', None)
            if additions:
                base = self._normalize_explanation(cell.metadata.get('explanation'))
                guidance = "\n".join(f"- {a.get('text', '')}" for a in additions)
                cell.metadata['explanation'] = f"{base}\n\nAdditional guidance:\n{guidance}"

        # Migrate old unit test format (no 'cells' wrapper) to new format
        for cell in self.nb.cells:
            for test_name, ut in cell.metadata.get('unit_tests', {}).items():
                if 'cells' not in ut:
                    cells = {}
                    validity = ut.pop('validity', None)
                    for key in list(ut.keys()):
                        cells[key] = ut.pop(key)
                    ut['cells'] = cells
                    if validity is None:
                        ut['validity'] = {
                            'setup_code_valid': False,
                            'setup_output_valid': False,
                            'target_output_valid': False,
                            'test_code_valid': False,
                            'test_output_valid': False,
                        }
                    else:
                        ut['validity'] = validity

    def _cells_citing_paths(self, removed_paths):
        """Sorted indices of code cells whose generated source references any of
        the given file paths."""
        paths = [p for p in removed_paths if p]
        return [i for i, cell in enumerate(self.nb.cells)
                if cell.cell_type == 'code'
                and any(p in (cell.source or '') for p in paths)]

    def _invalidate_cells_for_removed_files(self, removed_paths):
        """Force-regenerate the code cells that cite any removed input-file path.

        For each citing cell, clears code_description_hash (so the generation-skip
        fast path cannot keep the now-stale code) and output_hash (an execution artifact),
        then lowers the code/output/test watermarks to just before the earliest
        citing cell. No-op if no cell cites a removed file (e.g. a pure file add,
        or a removed file that no cell references). Caller holds self._lock and
        persists via _write(); last_executed_cell (kernel snapshots) is left
        alone, matching the previous invalidation behaviour."""
        citing = self._cells_citing_paths(removed_paths)
        if not citing:
            return
        for i in citing:
            self.nb.cells[i].metadata.pop('code_description_hash', None)
            self._live(self.nb.cells[i]).output_hash = None
        boundary = min(citing) - 1
        self.last_valid_code_cell = min(self.last_valid_code_cell, boundary)
        self.last_valid_output_cell = min(self.last_valid_output_cell, boundary)
        self.last_valid_test_cell = min(self.last_valid_test_cell, boundary)

    def _filter_input_files(self):
        """Filters the input files from notebook metadata."""
        if 'input_files' in self.nb.metadata:
            input_files = self.nb.metadata['input_files']
            # Keeps only files whose path exists.
            present_input_files = []
            missing_input_files = []
            for f in input_files:
                if os.path.isfile(f.get('path', '')):
                    present_input_files.append(f)
                else:
                    missing_input_files.append(f)
            self.nb.metadata['input_files'] = present_input_files
            self.nb.metadata['missing_input_files'] = missing_input_files
            # Condition-1: files listed by the notebook are missing on disk, so
            # the code that refers to them must be regenerated -- invalidate only
            # the cells that actually cite a missing file.
            if missing_input_files:
                self._invalidate_cells_for_removed_files(
                    f.get('path') for f in missing_input_files)

    def _write(self, path=None):
        """Write the notebook to `path`, defaulting to its own path.

        The explicit path is for save_copy(), which writes the same content
        elsewhere without this notebook changing where it lives."""
        self.nb.metadata['last_valid_code_cell'] = self.last_valid_code_cell
        self.nb.metadata['last_valid_output'] = self.last_valid_output_cell
        self.nb.metadata['last_valid_test_cell'] = self.last_valid_test_cell
        with open(path or self.path, "w") as f:
            nbformat.write(self.nb, f)

    def rename(self, new_name):
        """Rename the notebook by saving a *copy* under a new name (with a
        .plnb extension) in the same directory, and switching all future saves
        to it. The original file is left untouched. Because the notebook is
        saved continuously, simply changing the name/path and writing once is
        enough for it to continue naturally under the new name.

        A name already in use is not an error: _2, _3, ... is appended, and the
        name the notebook actually took is reflected in self.name.

        Raises ValueError on an empty name.
        """
        with self._lock:
            name = normalize_notebook_name(new_name)
            if name == self.name:
                return
            parent = os.path.dirname(self.path) or "."
            self.name, self.path = unique_notebook_path(parent, name)
            self._write()

    def save_copy(self, new_name, folder=None):
        """Write a copy of this notebook under a new name, in `folder`.

        `folder` defaults to this notebook's own folder, and is expected to have
        been validated by the caller. This notebook's own name and path are
        untouched; the copy is just a file on disk, which the caller then opens
        as its own plainbook. Adds _2, _3, ... if the requested name is taken.
        Returns (name, path).

        Raises ValueError on an empty name.
        """
        with self._lock:
            name = normalize_notebook_name(new_name)
            parent = folder or os.path.dirname(self.path) or "."
            name, path = unique_notebook_path(parent, name)
            self._write(path)
            return name, path

    def append_log_entry(self, entry):
        """Append an action-log entry to nb.metadata['log'] and persist.
        Used by the --log user-study logging feature. See Log.md for schema."""
        with self._lock:
            self.nb.metadata.setdefault('log', []).append(entry)
            self._write()

    # State and JSON access

    def get_state(self):
        """Returns a dictionary representing the notebook state."""
        try:
            assert self.last_valid_code_cell >= self.last_valid_output_cell, (
                f"last_valid_code_cell {self.last_valid_code_cell}, "
                f"last_valid_output {self.last_valid_output_cell} ")
        except AssertionError as e:
            print(f"State violation: {e}")
            if not self.debug:
                raise e
        state = {
            'name': self.name,
            'path': self.path,
            'num_cells': len(self.nb.cells),
            'last_executed_cell': self.last_executed_cell,
            'last_valid_code_cell': self.last_valid_code_cell,
            'last_valid_output_cell': self.last_valid_output_cell,
            'last_valid_test_cell': self.last_valid_test_cell,
            'is_locked': self.nb.metadata.get('is_locked', False),
            'share_output_with_ai': self.nb.metadata.get('share_output_with_ai', True),
            'ai_tokens': get_session_tokens(),
            'verification_status': self.get_verification_status(),
        }
        if self.debug:
            print("State: ", json.dumps(state, indent=2))
        return state


    def get_cell_json(self, index):
        """Returns the JSON representation of a cell by index."""
        if index < 0 or index >= len(self.nb.cells):
            raise IndexError("Cell index out of range")
        return self.nb.cells[index]

    def get_json(self):
        """Returns the JSON representation of the entire notebook."""
        return self.nb

    # Public kernel reset wrapper

    def reset_kernel(self):
        """Resets the kernel."""
        if self.debug:
            print("Request to reset kernel received...")
        with self._lock:
            if self.debug:
                print("Resetting kernel...")
            self._reset_kernel()

    # Cell insertion, deletion, and movement methods

    def lock(self, is_locked):
        """Locks or unlocks the notebook."""
        with self._lock:
            self.nb.metadata['is_locked'] = is_locked
            self._write()

    def set_share_output_with_ai(self, share):
        """Sets whether cell outputs are shared with AI."""
        with self._lock:
            self.nb.metadata['share_output_with_ai'] = share
            self._write()

    def insert_cell(self, index, cell_type):
        """Insert a new cell at index with given type ('markdown', 'code', or 'test'). Returns the cell json."""
        with self._lock:
            assert cell_type in ('markdown', 'code', 'test')
            assert 0 <= index <= len(self.nb.cells)
            if cell_type == 'markdown':
                new_cell = nbformat.v4.new_markdown_cell(source="")
            elif cell_type == 'test':
                new_cell = nbformat.v4.new_code_cell(source="", execution_count=None, outputs=[])
                new_cell.cell_type = 'test'
                new_cell.metadata['explanation'] = []
                new_cell.metadata['explanation_timestamp'] = datetime.datetime.now().isoformat()
            else:
                new_cell = nbformat.v4.new_code_cell(source="", execution_count=None, outputs=[])
                new_cell.metadata['explanation'] = []
                new_cell.metadata['explanation_timestamp'] = datetime.datetime.now().isoformat()
            self.nb.cells.insert(index, new_cell)
            # Inserting code cells before the last executed cell requires invalidation.
            if cell_type == 'code':
                if index <= self.last_executed_cell:
                    self._invalidate_execution(index)
                self.last_valid_code_cell = min(self.last_valid_code_cell, index - 1)
                self.last_valid_output_cell = min(self.last_valid_output_cell, index - 1)
                self.last_valid_test_cell = min(self.last_valid_test_cell, index - 1)
            elif cell_type == 'test':
                self.last_valid_test_cell = min(self.last_valid_test_cell, index - 1)
            self._write()
            return new_cell, index


    def delete_cell(self, index):
        """Delete the cell at the given index."""
        with self._lock:
            if index < 0 or index >= len(self.nb.cells):
                raise IndexError("Cell index out of range")
            cell = self.nb.cells[index]
            # Update execution pointer: invalidate if code was executed, otherwise shift index
            if index <= self.last_executed_cell:
                if cell.cell_type == 'code':
                    self._invalidate_execution(index)
                else:
                    # Test and markdown cells are not in the main execution chain
                    self.last_executed_cell -= 1
            # Update validation pointers
            if cell.cell_type == 'code':
                self.last_valid_code_cell = min(self.last_valid_code_cell, index - 1)
                self.last_valid_output_cell = min(self.last_valid_output_cell, index - 1)
                self.last_valid_test_cell = min(self.last_valid_test_cell, index - 1)
            elif cell.cell_type == 'test':
                self.last_valid_test_cell = min(self.last_valid_test_cell, index - 1)
                # Shift code/output pointers since test cells are not in the main chain
                if index <= self.last_valid_code_cell:
                    self.last_valid_code_cell -= 1
                if index <= self.last_valid_output_cell:
                    self.last_valid_output_cell -= 1
            else:
                # Markdown cell: shift all pointers
                if index <= self.last_valid_code_cell:
                    self.last_valid_code_cell -= 1
                if index <= self.last_valid_output_cell:
                    self.last_valid_output_cell -= 1
                if index <= self.last_valid_test_cell:
                    self.last_valid_test_cell -= 1
            # Finally, delete the cell
            del self.nb.cells[index]
            self._write()


    def move_cell(self, index, new_index):
        """Move a cell from index to new_index."""
        with self._lock:
            n = len(self.nb.cells)
            assert 0 <= index < n, "Cell index out of range"
            assert 0 <= new_index <= n, "New index out of range"
            cell = self.nb.cells.pop(index)
            self.nb.cells.insert(new_index, cell)
            if cell.cell_type == 'code':
                affected_idx = min(index, new_index)
                if self.last_executed_cell >= affected_idx:
                    self._invalidate_execution(affected_idx)
                self.last_valid_code_cell = min(self.last_valid_code_cell, affected_idx - 1)
                self.last_valid_output_cell = min(self.last_valid_output_cell, affected_idx - 1)
                self.last_valid_test_cell = min(self.last_valid_test_cell, affected_idx - 1)
            elif cell.cell_type == 'test':
                # Test cells are not in the main execution chain; shift code/output/executed pointers
                if self.last_executed_cell >= index:
                    self.last_executed_cell -= 1
                if self.last_executed_cell >= new_index:
                    self.last_executed_cell += 1
                if self.last_valid_code_cell >= index:
                    self.last_valid_code_cell -= 1
                if self.last_valid_code_cell >= new_index:
                    self.last_valid_code_cell += 1
                if self.last_valid_output_cell >= index:
                    self.last_valid_output_cell -= 1
                if self.last_valid_output_cell >= new_index:
                    self.last_valid_output_cell += 1
                # Cap test validity at the affected range
                self.last_valid_test_cell = min(self.last_valid_test_cell, min(index, new_index) - 1)
            else:
                # Adjust pointers for markdown cell movement
                if self.last_executed_cell >= index:
                    self.last_executed_cell -= 1
                if self.last_executed_cell >= new_index:
                    self.last_executed_cell += 1
                # Adjust validation pointer
                if self.last_valid_code_cell >= index:
                    self.last_valid_code_cell -= 1
                if self.last_valid_code_cell >= new_index:
                    self.last_valid_code_cell += 1
                # Adjusts output pointer.
                if self.last_valid_output_cell >= index:
                    self.last_valid_output_cell -= 1
                if self.last_valid_output_cell >= new_index:
                    self.last_valid_output_cell += 1
                # Shift test pointer for markdown movement
                if self.last_valid_test_cell >= index:
                    self.last_valid_test_cell -= 1
                if self.last_valid_test_cell >= new_index:
                    self.last_valid_test_cell += 1
            self._write()

    # Cell editing methods

    def _clear_validation(self, cell):
        cell.metadata.pop('validation', None)  # Clear cached validation results
        cell.metadata.pop('validation_timestamp', None)
        
    def set_cell_source(self, index, source):
        """Sets the source code of a cell at the given index."""
        with self._lock:
            assert 0 <= index < len(self.nb.cells)
            cell = self.nb.cells[index]
            cell.source = source
            if cell.cell_type in ('code', 'test'):
                # New source: refresh the code hash and drop a now-stale explanation.
                self._refresh_code_hash(cell)
                # Hand-written code was not generated from the description, so
                # the generation-skip must not assume regenerating would produce
                # what is already here. Clearing the pin makes
                # _code_matches_description() false, so Generate really calls the
                # AI. Same idiom as _invalidate_cells_for_removed_files().
                cell.metadata.pop('code_description_hash', None)
            self._clear_validation(cell)  # Clear any cached validation results
            cell.metadata['code_timestamp'] = datetime.datetime.now().isoformat()
            if cell.cell_type == 'test':
                self._drop_outputs(cell)
                # The user has updated the test code; assume this cell valid, following invalid.
                self.last_valid_test_cell = min(self.last_valid_test_cell, index)
            elif cell.cell_type == 'code':
                # The output produced by the pre-edit code is kept, so the user
                # can still see what the cell last did. It is no longer current:
                # last_valid_output_cell below marks it stale (the UI labels it
                # so), and the execution-skip declines because the source it was
                # produced from no longer matches, so a re-run really re-runs.
                if index <= self.last_executed_cell:
                    self._invalidate_execution(index)
                # The user has updated the code.  We will assume this
                # cell to be valid, if it was before.
                # However, any following code cells are now invalid.
                self.last_valid_code_cell = min(self.last_valid_code_cell, index)
                # The output is now stale.
                self.last_valid_output_cell = min(self.last_valid_output_cell, index - 1)
                self.last_valid_test_cell = min(self.last_valid_test_cell, index - 1)
                # Invalidate unit tests: target code changed, setup may reference
                # variables that no longer exist
                if cell.metadata.get('unit_tests'):
                    self._invalidate_all_unit_tests(index, 'setup_code')
            self._write()


    def clear_cell_code(self, index):
        """Clears the source code of a code or test cell and marks its code as invalid."""
        with self._lock:
            assert 0 <= index < len(self.nb.cells)
            cell = self.nb.cells[index]
            assert cell.cell_type in ('code', 'test')
            cell.source = ''
            # Clearing the code invalidates any explanation of it.
            self._refresh_code_hash(cell)
            # Empty source was not generated from the description, so the
            # generation-skip must not assume regenerating would reproduce it.
            # Same idiom as set_cell_source().
            cell.metadata.pop('code_description_hash', None)
            self._clear_validation(cell)  # Clear any cached validation results
            self._drop_outputs(cell)
            if cell.cell_type == 'test':
                self.last_valid_test_cell = min(self.last_valid_test_cell, index - 1)
            else:
                if index <= self.last_executed_cell:
                    self._invalidate_execution(index)
                self.last_valid_code_cell = min(self.last_valid_code_cell, index - 1)
                self.last_valid_output_cell = min(self.last_valid_output_cell, index - 1)
                self.last_valid_test_cell = min(self.last_valid_test_cell, index - 1)
                # Invalidate unit tests: target code cleared, setup may reference
                # variables that no longer exist
                if cell.metadata.get('unit_tests'):
                    self._invalidate_all_unit_tests(index, 'setup_code')
            self._write()

    def set_cell_explanation(self, index, explanation):
        """Sets the explanation of a code or test cell at the given index."""
        with self._lock:
            assert 0 <= index < len(self.nb.cells)
            cell = self.nb.cells[index]
            assert cell.cell_type in ('code', 'test')
            cell.metadata['explanation'] = explanation
            cell.metadata['explanation_timestamp'] = datetime.datetime.now().isoformat()
            cell.metadata['description_hash'] = self._hash_text(explanation)
            if cell.cell_type == 'test':
                self.last_valid_test_cell = min(self.last_valid_test_cell, index - 1)
            else:
                # The cell code is now considered stale.
                self.last_valid_code_cell = min(self.last_valid_code_cell, index - 1)
                self.last_valid_output_cell = min(self.last_valid_output_cell, index - 1)
                self.last_valid_test_cell = min(self.last_valid_test_cell, index - 1)
                # Invalidate unit tests: target explanation changed, code will be
                # regenerated so setup and test cells are all stale
                if cell.metadata.get('unit_tests'):
                    self._invalidate_all_unit_tests(index, 'setup_code')
                # Invalidate unit tests on all downstream cells: they depend
                # on upstream state that is now stale
                for j in range(index + 1, len(self.nb.cells)):
                    if self.nb.cells[j].metadata.get('unit_tests'):
                        self._invalidate_all_unit_tests(j, 'setup_code')
            self._write()


    # Amend and fold

    @staticmethod
    def _normalize_explanation(explanation):
        """Coerces an explanation to a string (new cells store [] initially)."""
        if isinstance(explanation, list):
            return ''.join(explanation)
        return explanation or ''

    def _mark_code_stale(self, index):
        """Invalidates a cell and everything downstream, as an explanation edit does."""
        self.last_valid_code_cell = min(self.last_valid_code_cell, index - 1)
        self.last_valid_output_cell = min(self.last_valid_output_cell, index - 1)
        self.last_valid_test_cell = min(self.last_valid_test_cell, index - 1)
        if self.nb.cells[index].metadata.get('unit_tests'):
            self._invalidate_all_unit_tests(index, 'setup_code')
        for j in range(index + 1, len(self.nb.cells)):
            if self.nb.cells[j].metadata.get('unit_tests'):
                self._invalidate_all_unit_tests(j, 'setup_code')

    def _pin_code_validity(self):
        """Declares every cell's stored code valid, for --unit-tests-only mode.

        The client asks the server to generate a cell's code exactly when
        last_valid_code_cell has dropped below it, so pinning the watermark at
        the last cell is what guarantees the stored code is executed as it
        stands and never regenerated -- the property the whole study rests on.

        Refusing /generate_code on its own would not do: execute_cell raises for
        any cell past the watermark, and unit-test generation refuses unless the
        target's code is valid, so a dropped watermark would leave a participant
        unable to run or test anything, with no way to recover.

        The pinned value does reach the file, because _write stores the
        watermarks in the notebook's metadata and study mode writes on every
        run. That is harmless, and arguably right: it records that the stored
        code is the code, so reopening the notebook without the flag will not
        offer to regenerate it either.
        """
        last = len(self.nb.cells) - 1
        self.last_valid_code_cell = last
        self.last_valid_output_cell = min(self.last_valid_output_cell, last)
        self.last_valid_test_cell = min(self.last_valid_test_cell, last)

    def propose_amend(self, api_key, index, text, ai_provider="gemini", model=None):
        """Returns the explanation rewritten to incorporate `text`. Does not modify
        the cell; the caller reviews the result and calls commit_amend."""
        with self._lock:
            assert 0 <= index < len(self.nb.cells)
            cell = self.nb.cells[index]
            assert cell.cell_type in ('code', 'test')
            base = self._normalize_explanation(cell.metadata.get('explanation'))
            if not (text or '').strip():
                return base
            if self.ai_request_pending:
                raise RuntimeError("An AI request is already pending.")
            try:
                self.ai_request_pending = True
                fold_fn = AI_PROVIDERS[ai_provider]["fold"]
                return fold_fn(api_key, explanation=base, additions=[text], model=model,
                               debug=self.debug, dump_ai_requests=self.dump_ai_requests)
            finally:
                self.ai_request_pending = False

    def commit_amend(self, index, folded_explanation):
        """Installs a folded explanation, snapshotting the explanation and code it
        replaces so it can be undone. Marks the code stale: the folded text has not
        generated code yet, and the caller regenerates from it."""
        with self._lock:
            assert 0 <= index < len(self.nb.cells)
            cell = self.nb.cells[index]
            assert cell.cell_type in ('code', 'test')
            cell.metadata['explanation_prefold'] = {
                'explanation': self._normalize_explanation(cell.metadata.get('explanation')),
                'source': tostring(cell.source),
            }
            cell.metadata['explanation'] = folded_explanation
            cell.metadata['explanation_timestamp'] = datetime.datetime.now().isoformat()
            cell.metadata['description_hash'] = self._hash_text(folded_explanation)
            self._mark_code_stale(index)
            self._write()

    def unfold(self, index):
        """Restores the explanation and code saved by commit_amend, returning both,
        or None if there is no snapshot. A restored pair already ran together, so
        only the output is stale. Snapshots from before the amend redesign have no
        code to restore, and leave the code stale instead."""
        with self._lock:
            assert 0 <= index < len(self.nb.cells)
            cell = self.nb.cells[index]
            assert cell.cell_type in ('code', 'test')
            snapshot = cell.metadata.get('explanation_prefold')
            if not snapshot:
                return None
            source = snapshot.get('source')
            cell.metadata['explanation'] = snapshot.get('explanation', '')
            cell.metadata['explanation_timestamp'] = datetime.datetime.now().isoformat()
            restored_hash = self._hash_text(cell.metadata['explanation'])
            cell.metadata['description_hash'] = restored_hash
            del cell.metadata['explanation_prefold']
            if source is None:
                self._mark_code_stale(index)
            else:
                cell.source = source
                # The restored code was generated from the restored explanation, so
                # the pair matches and needs no regeneration. Replacing cell.source
                # also retires the stored output: it was produced by the pre-unfold
                # code, so the execution-skip declines and the restored code
                # actually runs.
                cell.metadata['code_description_hash'] = restored_hash
                self._refresh_code_hash(cell)
                self._invalidate_execution(index)
                self.last_valid_code_cell = min(self.last_valid_code_cell, index)
                self.last_valid_output_cell = min(self.last_valid_output_cell, index - 1)
                self.last_valid_test_cell = min(self.last_valid_test_cell, index - 1)
            self._write()
            return {'explanation': cell.metadata['explanation'], 'source': source}


    # Unit test metadata methods (stubs for Phase 1)

    def save_unit_tests(self, cell_index, unit_tests):
        """Save the full unit_tests dict to cell metadata."""
        with self._lock:
            assert 0 <= cell_index < len(self.nb.cells)
            cell = self.nb.cells[cell_index]
            cell_id = cell.id
            # Clear and delete kernel state entries for this cell
            for sk in [sk for sk in self._unit_test_states if sk.startswith(f"{cell_id}:")]:
                try:
                    self._sk_request("DELETE", f"/states/{self._unit_test_states[sk]}")
                except Exception:
                    pass
                del self._unit_test_states[sk]
            cell.metadata['unit_tests'] = unit_tests
            self._write()

    def save_unit_test_explanation(self, cell_index, test_name, role, explanation):
        """Update the explanation of a unit test sub-cell."""
        with self._lock:
            assert 0 <= cell_index < len(self.nb.cells)
            cell = self.nb.cells[cell_index]
            tests = cell.metadata.get('unit_tests', {})
            assert test_name in tests
            assert role in ('setup', 'test')
            tests[test_name]['cells'][role]['metadata']['explanation'] = explanation
            tests[test_name]['cells'][role]['metadata']['explanation_timestamp'] = datetime.datetime.now().isoformat()
            # Invalidate from the appropriate point
            if role == 'setup':
                self._invalidate_unit_test(cell_index, test_name, 'setup_code')
            else:
                self._invalidate_unit_test(cell_index, test_name, 'test_code')
            self._write()

    def save_unit_test_code(self, cell_index, test_name, role, source):
        """Update the source code of a unit test sub-cell."""
        with self._lock:
            assert 0 <= cell_index < len(self.nb.cells)
            cell = self.nb.cells[cell_index]
            tests = cell.metadata.get('unit_tests', {})
            assert test_name in tests
            assert role in ('setup', 'test')
            tests[test_name]['cells'][role]['source'] = source
            tests[test_name]['cells'][role]['metadata']['code_timestamp'] = datetime.datetime.now().isoformat()
            # Invalidate from the appropriate point
            if role == 'setup':
                self._invalidate_unit_test(cell_index, test_name, 'setup_output')
            else:
                self._invalidate_unit_test(cell_index, test_name, 'test_output')
            self._write()

    def clear_unit_test_code(self, cell_index, test_name, role):
        """Clear the source code and outputs of a unit test sub-cell."""
        with self._lock:
            assert 0 <= cell_index < len(self.nb.cells)
            cell = self.nb.cells[cell_index]
            tests = cell.metadata.get('unit_tests', {})
            assert test_name in tests
            assert role in ('setup', 'test')
            tests[test_name]['cells'][role]['source'] = ''
            tests[test_name]['cells'][role]['outputs'] = []
            # Invalidate from the appropriate point
            if role == 'setup':
                self._invalidate_unit_test(cell_index, test_name, 'setup_code')
            else:
                self._invalidate_unit_test(cell_index, test_name, 'test_code')
            self._write()

    # Unit test execution and generation

    def clear_unit_test_outputs(self, cell_index, test_name):
        """Clear outputs for all sub-cells of a unit test."""
        with self._lock:
            assert 0 <= cell_index < len(self.nb.cells)
            cell = self.nb.cells[cell_index]
            tests = cell.metadata.get('unit_tests', {})
            assert test_name in tests
            unit_test = tests[test_name]
            unit_test['cells']['setup']['outputs'] = []
            if 'target' in unit_test['cells']:
                unit_test['cells']['target']['outputs'] = []
            unit_test['cells']['test']['outputs'] = []
            self._write()

    def execute_unit_test_cell(self, cell_index, test_name, role):
        """Execute a unit test sub-cell (setup, target, or test)."""
        with self._lock:
            assert 0 <= cell_index < len(self.nb.cells)
            cell = self.nb.cells[cell_index]
            tests = cell.metadata.get('unit_tests', {})
            assert test_name in tests
            assert role in ('setup', 'target', 'test')
            unit_test = tests[test_name]

            # Determine input state
            if role == 'setup':
                input_state = self._find_input_state(cell_index)
            elif role == 'target':
                setup_key = self._ut_state_key(cell_index, test_name, 'setup')
                if setup_key not in self._unit_test_states:
                    raise ExecutionError("Setup must be executed before target")
                input_state = self._unit_test_states[setup_key]
            else:  # test
                target_key = self._ut_state_key(cell_index, test_name, 'target')
                if target_key not in self._unit_test_states:
                    raise ExecutionError("Target must be executed before test")
                input_state = self._unit_test_states[target_key]

            # Determine source code
            if role == 'setup':
                source = unit_test['cells']['setup'].get('source', '')
                # Empty setup code is fine — the kernel will execute a no-op
                # and create a distinct new state (fork of the input state).
            elif role == 'target':
                source = cell.source
            else:
                source = unit_test['cells']['test'].get('source', '')

            # Allocate/reuse state name guaranteeing uniqueness across all unit test sub-cells and main cells.
            state_key = self._ut_state_key(cell_index, test_name, role)
            if state_key in self._unit_test_states:
                new_state_name = self._unit_test_states[state_key]
            else:
                existing_names = set(self._cell_states.values()) | set(self._unit_test_states.values())
                new_state_name = uuid.uuid4().hex
                while new_state_name in existing_names:
                    new_state_name = uuid.uuid4().hex
                self._unit_test_states[state_key] = new_state_name

            exec_id = uuid.uuid4().hex
            self._current_exec_id = exec_id
            try:
                result = self._sk_request("POST", "/execute", {
                    "code": source,
                    "exec_id": exec_id,
                    "state_name": input_state,
                    "new_state_name": new_state_name,
                })
            finally:
                self._current_exec_id = None

            # Convert outputs
            outputs = []
            for out in result.get("output", []):
                outputs.append(nbformat.from_dict(out))

            # Store outputs in appropriate location
            if role == 'setup':
                unit_test['cells']['setup']['outputs'] = outputs
            elif role == 'target':
                if 'target' not in unit_test['cells']:
                    unit_test['cells']['target'] = {}
                unit_test['cells']['target']['outputs'] = outputs
            else:
                unit_test['cells']['test']['outputs'] = outputs

            if result.get("error"):
                err = result["error"]
                error_output = nbformat.from_dict({
                    "output_type": "error",
                    "ename": err.get("ename", "Error"),
                    "evalue": err.get("evalue", ""),
                    "traceback": err.get("traceback", []),
                })
                if role == 'setup':
                    if not any(o.get("output_type") == "error" for o in unit_test['cells']['setup']['outputs']):
                        unit_test['cells']['setup']['outputs'].append(error_output)
                elif role == 'target':
                    if not any(o.get("output_type") == "error" for o in unit_test['cells']['target']['outputs']):
                        unit_test['cells']['target']['outputs'].append(error_output)
                else:
                    if not any(o.get("output_type") == "error" for o in unit_test['cells']['test']['outputs']):
                        unit_test['cells']['test']['outputs'].append(error_output)
                self._write()
                raise CellExecutionError(
                    traceback="\n".join(err.get("traceback", [])),
                    ename=err.get("ename", "Error"),
                    evalue=err.get("evalue", ""),
                )

            # Get variables and store them
            variables = self._get_variables(state_name=new_state_name)
            if role == 'target':
                unit_test['cells']['target']['variables'] = variables
            elif role == 'setup':
                unit_test['cells']['setup']['metadata']['variables'] = variables
            else:
                # For test, add success message
                outputs.append(nbformat.from_dict({
                    "output_type": "stream",
                    "name": "stdout",
                    "text": "The test passed.\n",
                }))
                if role == 'test':
                    unit_test['cells']['test']['outputs'] = outputs

            # Set validity flag
            v = self._get_ut_validity(cell_index, test_name)
            if role == 'setup':
                v['setup_output_valid'] = True
            elif role == 'target':
                v['target_output_valid'] = True
            else:
                v['test_output_valid'] = True

            self._write()
            return outputs

 
    # Methods to support AI


    def _filter_outputs_for_ai(self, outputs):
        """Filters cell outputs to remove images and oversized data before
        sending to AI. Returns a new list of filtered output items."""
        filtered = []
        for output in outputs:
            output_type = output.get('output_type', '')
            if output_type in ('display_data', 'execute_result'):
                data = output.get('data', {})
                data = {k: v for k, v in data.items()
                        if not k.startswith('image/') and k != 'application/pdf'}
                if not data:
                    continue
                output = copy.copy(output)
                output['data'] = data
            if len(json.dumps(output, default=str)) > MAX_OUTPUT_CHARS_FOR_AI:
                continue
            filtered.append(output)
        return filtered


    def _get_cell_json_for_ai(self, cell):
        """Returns the content of a cell for AI processing, in JSON format.
        Needs to be called with the lock held."""
        new_cell = copy.deepcopy(cell)
        new_cell.pop("id", None)
        if cell.cell_type == 'code':
            new_cell.pop("execution_count", None)
            new_cell.metadata.pop('validation', None)
            # We fold the explanation in the code to make the format more standard. 
            explanation = cell.metadata.get('explanation', "")
            new_cell.metadata.pop('explanation', None)
            explanation = ["# " + line for line in explanation.splitlines(keepends=True)]
            explanation_text = "".join(explanation) + "\n"
            new_cell.source = explanation_text + cell.source
        # Remove unit test data from metadata — it's large and not needed for context.
        new_cell.metadata.pop('unit_tests', None)
        new_cell.metadata.pop("code_timestamp", None)
        new_cell.metadata.pop("explanation_timestamp", None)
        new_cell.outputs = []
        if (self.nb.metadata.get('share_output_with_ai', True) and 
            new_cell.cell_type == 'code' and hasattr(cell, 'outputs')): 
            new_cell.outputs = self._filter_outputs_for_ai(new_cell.outputs)
        return new_cell


    def _format_variables_for_ai(self, variables):
        """Format a variables dict into a text summary for AI context."""
        lines = []
        for name, info in variables.items():
            if name in self.default_variables:
                continue
            v_type = info.get('type', 'unknown')
            details = []
            if 'shape' in info:
                details.append(f"shape: {info['shape']}")
            elif 'len' in info:
                details.append(f"length: {info['len']}")
            if 'dtype' in info:
                details.append(f"dtype: {info['dtype']}")
            summary = f"- {name} ({v_type}" + (f", {', '.join(details)}" if details else "") + ")"
            lines.append(summary)
            if 'columns' in info:
                lines.append("  Columns:")
                for col in info['columns']:
                    lines.append(f"  * {col['name']} ({col['dtype']})")
        return "\n".join(lines)


    def _get_target_accessed_variables(self, source):
        """Return the set of variable names accessed (read) by the given source code,
        excluding builtins and names that are only assigned."""
        import ast
        import builtins
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return set()
        loaded = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                if isinstance(node.ctx, ast.Load):
                    loaded.add(node.id)
        builtin_names = set(dir(builtins))
        return loaded - builtin_names


    def _get_previous_code_cell_index(self, index):
        """Returns the index of the last code cell before the given index, or -1 if none exists."""
        assert 0 <= index < len(self.nb.cells)
        for i in range(index - 1, -1, -1):
            if self.nb.cells[i].cell_type == 'code':
                return i
        return -1


    def _get_preceding_code_cell(self, index):
        """Returns the last code cell before the given index, or None if none exists."""
        prev_index = self._get_previous_code_cell_index(index)
        return self.nb.cells[prev_index] if prev_index >= 0 else None
    

    def _get_variables_for_ai(self, cell):
        """Returns a formatted text summary of variables in the kernel
        that are defined just _before_ the cell at index is executed."""
        variables = cell.metadata.get('variables', {})
        return self._format_variables_for_ai(variables)


    def debug_request(self):
        with self._lock:
            self._debug_print_states()


    def _debug_print_states(self):
        """Print all cells and their associated kernel states."""
        import sys
        # Get set of states that actually exist in the kernel
        try:
            kernel_states = set(self._sk_request("GET", "/states").get("states", []))
        except Exception:
            kernel_states = set()
        def state_info(state_name):
            if state_name is None:
                return "None"
            exists = state_name in kernel_states
            return f"{state_name} ({'exists' if exists else 'MISSING'})"
        print("=" * 60)
        print("DEBUG: Notebook cell states")
        print(f"  last_executed_cell: {self.last_executed_cell}")
        print(f"  last_valid_code_cell: {self.last_valid_code_cell}")
        print(f"  last_valid_output_cell: {self.last_valid_output_cell}")
        print(f"  last_valid_test_cell: {self.last_valid_test_cell}")
        print("-" * 60)
        for i, cell in enumerate(self.nb.cells):
            name = cell.metadata.get('name', '') or f'(unnamed {cell.cell_type})'
            cell_state = self._cell_states.get(cell.id)
            print(f"  Cell {i}: {name} [{cell.cell_type}]")
            print(f"    Kernel state after: {state_info(cell_state)}")
            unit_tests = cell.metadata.get('unit_tests', {})
            if unit_tests:
                # State before unit tests = state of the previous code cell
                prev_code_cell = self._get_preceding_code_cell(i)
                if prev_code_cell is not None:
                    prev_state = self._cell_states.get(prev_code_cell.id)
                else:
                    prev_state = None
                for test_name, ut in unit_tests.items():
                    setup_key = f"{cell.id}:{test_name}:setup"
                    target_key = f"{cell.id}:{test_name}:target"
                    test_key = f"{cell.id}:{test_name}:test"
                    setup_state = self._unit_test_states.get(setup_key)
                    target_state = self._unit_test_states.get(target_key)
                    test_state = self._unit_test_states.get(test_key)
                    validity = ut.get('validity', {})
                    print(f"    Unit test: {test_name}")
                    print(f"      State before test:  {state_info(prev_state)}")
                    print(f"      After setup:        {state_info(setup_state)}")
                    print(f"      After target:       {state_info(target_state)}")
                    print(f"      After test:         {state_info(test_state)}")
                    print(f"      Validity: {validity}")
        print("=" * 60)
        sys.stdout.flush()


    def _get_cell_text_for_ai(self, cell):
        """Returns the text representation of a single cell for AI context."""
        lines = cell.source.split("\n")
        if cell.metadata.get('name'):
            s = f"# Cell {cell.metadata.get('name', '')}:\n"
        else:
            s = "# Cell:\n"
        s += "\n".join(lines) + "\n\n"
        if self.nb.metadata.get('share_output_with_ai', True) and len(cell.outputs) > 0:
            clean_outputs = self._filter_outputs_for_ai(cell.outputs)
            s += "# Outputs:\n"
            for o in clean_outputs:
                o_lines = json.dumps(o, default=str, indent=2).split("\n")
                s += "\n".join([f"# {l}" for l in o_lines]) + "\n"
            s += "\n"
        return s


    def _get_preceding_code_for_ai(self, index):
        """Returns text representation of all previous code cells for context."""
        cells = [self._get_cell_json_for_ai(self.nb.cells[i]) for i in range(index)
                if self.nb.cells[i].cell_type != 'test']
        return "".join(self._get_cell_text_for_ai(c) for c in cells)


    def _get_cell_w_change_noted(self, cell):
        """Returns the source code of the cell at index for context."""
        if cell.cell_type != 'code' or cell.source is None or cell.source.strip() == "":
            return None
        source = self._get_cell_text_for_ai(cell)
        if cell.metadata['explanation_timestamp'] < cell.metadata['code_timestamp']:
            return PREVIOUS_CODE_NEEDS_REVISION.format(code_string=source)
        else:
            return PREVIOUS_CODE_EXPLANATION_CHANGED.format(code_string=source)


    def _get_instructions(self, explanation):
        """Returns the explanation with any notebook-wide AI instructions appended."""
        ai_instructions = self.nb.metadata.get('ai_instructions', '')
        if ai_instructions:
            return explanation + "\n\nADDITIONAL INSTRUCTIONS:\n" + ai_instructions
        return explanation
    

    def _is_previous_code_and_output_valid(self, index):
        last_code_cell_idx = self._get_previous_code_cell_index(index)
        if last_code_cell_idx < 0:
            return True # No previous code.
        # If we share output with AI, then we need valid output, but in any case we need valid variables.  
        return self.last_valid_output_cell >= last_code_cell_idx

            
    def _format_ut_subcell_for_ai(self, cell_or_dict, label):
        """Format a unit test sub-cell (or main cell) for AI context.
        Works with both nbformat cell objects (for target) and plain dicts (for setup/test).
        Returns a string like '# Explanation: ...\ncode...' or None if empty."""
        # Handle both nbformat objects (attribute access) and plain dicts
        if hasattr(cell_or_dict, 'metadata'):
            explanation = cell_or_dict.metadata.get('explanation', '')
            source = cell_or_dict.source or ''
        else:
            explanation = cell_or_dict.get('metadata', {}).get('explanation', '')
            source = cell_or_dict.get('source', '')
        if not explanation and not source:
            return None
        lines = []
        if explanation:
            lines.append(f"# {label.capitalize()} explanation:")
            lines.extend(f"# {l}" for l in explanation.split("\n"))
            lines.append("")  # Blank line between explanation and code
        if source:
            lines.append(f"# {label.capitalize()} code:")
            lines.extend(source.split("\n"))
        outputs = cell_or_dict.get('outputs', [])
        if self.nb.metadata.get('share_output_with_ai', True) and len(outputs) > 0:
            clean_outputs = self._filter_outputs_for_ai(outputs)
            lines.append("# Outputs:\n")
            for o in clean_outputs:
                o_lines = json.dumps(o, default=str, indent=2).split("\n")
                lines.append("\n".join([f"# {l}" for l in o_lines]) + "\n")
            lines.append("\n")
        return "\n".join(lines)


    def _ut_extract_error_context(self, outputs):
        """Extract error traceback from unit test sub-cell outputs."""
        for output in reversed(outputs):
            if output.get('output_type') == 'error':
                return ("The previous attempt to run this cell resulted in this error traceback:\n"
                        + "\n".join(getlist(output.get('traceback', []))))
        return None


    def generate_code_cell(self, api_key, index, ai_provider="gemini", model=None, validation_feedback=None, amend_description=False, force_regenerate=False, ask_questions=False, skip_regeneration=True):
        """Generates code for a code or test cell at index using the specified AI provider.

        Returns a 3-tuple ``(new_code, success, amended_explanation)``. When the caller
        requests it (``amend_description``) and the cell had an error that is now fixed,
        the cell's plain-language description is also amended so that regenerating from
        it on a clean slate would avoid the error; the amended text is returned as the
        third element (``None`` otherwise). Amendment is best-effort and never blocks the
        code fix.

        ``force_regenerate`` bypasses the generation-skip fast path below. Set it for
        explicit user actions (the Regenerate button), where returning the existing
        source looks like an AI that changed nothing rather than one that was never
        asked. The run-driven batch generation leaves it False and keeps the skip.

        ``ask_questions`` and ``skip_regeneration`` carry the global settings of the
        same names; the caller reads them (main.py owns the settings file) and passes
        them in. With ``skip_regeneration`` False the fast path is disabled entirely,
        so a cell is regenerated whenever generation is requested."""
        with self._lock:
            assert 0 <= index < len(self.nb.cells)
            cell = self.nb.cells[index]
            assert cell.cell_type in ('code', 'test')
            if not self._is_previous_code_and_output_valid(index):
                raise RuntimeError("Cannot generate code: previous output must be valid.")
            self._requested_generations += 1
            # Gets code context.
            is_test = (cell.cell_type == 'test')
            error_context = self._get_error_context(index)
            # Skip the AI regeneration when the code already matches the
            # (unchanged) description and the accessed variables are unchanged.
            # Conservative: only when the "Skip regeneration when data is
            # unchanged" setting is on, code cells only, never when the user
            # asked for this explicitly, and never when fixing an error or when
            # explicit validation feedback was requested.
            if (skip_regeneration and not force_regenerate
                    and not is_test and validation_feedback is None and not error_context
                    and self._code_matches_description(cell)
                    and self._accessed_vars_unchanged(cell, index)):
                return self._skip_code_generation(cell, index)
            self._performed_generations += 1 
            explanation_used = cell.metadata.get('explanation')
            instructions = self._get_instructions(explanation_used)
            # Hash of exactly the description sent to the AI, recorded below as
            # the description the code was generated from.
            gen_description_hash = self._hash_text(explanation_used)
            files_context = self._get_files_context()
            previous_code_cell = self._get_preceding_code_cell(index)
            variable_context = self._get_variables_for_ai(previous_code_cell) if previous_code_cell else ""
            preceding_code = self._get_preceding_code_for_ai(index)
            previous_code = self._get_cell_w_change_noted(cell)
            # Raw buggy source, captured before it is overwritten with new_code;
            # needed as context if we amend the description below.
            buggy_code = cell.source
            # Mark that an AI request is pending
            if self.ai_request_pending:
                raise RuntimeError("An AI request is already pending.")
            # Only action cells may ask questions; test cells always generate.
            # Whether questions are actually asked is up to the AI.
            ask_questions = (not is_test) and ask_questions
            try:
                self.ai_request_pending = True
                ai_fn_key = "generate_test" if is_test else "generate"
                generate_fn = AI_PROVIDERS[ai_provider][ai_fn_key]
                gen_kwargs = dict(
                    preceding_code=preceding_code,
                    previous_code=previous_code,
                    instructions=instructions,
                    file_context=files_context, error_context=error_context,
                    variable_context=variable_context,
                    validation_context=validation_feedback,
                    model=model,
                    debug=self.debug,
                    dump_ai_requests=self.dump_ai_requests)
                if is_test:
                    new_code = generate_fn(api_key, **gen_kwargs)
                else:
                    # The AI returns either the code, or questions for the user.
                    new_code, questions = generate_fn(
                        api_key, ask_questions=ask_questions, **gen_kwargs)
                    # A cancelled request must not raise.
                    if questions and self.ai_request_pending:
                        raise ClarificationNeeded(questions)
                # If we are still in a request, update the cell.
                if self.ai_request_pending:
                    cell.source = new_code
                    # Pin the code to the description it was generated from.
                    cell.metadata['code_description_hash'] = gen_description_hash
                    cell.metadata.setdefault(
                        'description_hash', self._hash_text(cell.metadata.get('explanation')))
                    # Record the hash of the new source and drop any AI code
                    # explanation that no longer matches the code it described.
                    self._refresh_code_hash(cell)
                    self._clear_validation(cell)
                    cell.metadata['code_timestamp'] = datetime.datetime.now().isoformat()
                    # New code: the old output is not its output. Dropping the
                    # skip's claim along with it is what forces the next run to
                    # really execute, even when the AI reproduced the previous
                    # source byte for byte (the common case for "Fix Code").
                    self._drop_outputs(cell)
                    if is_test:
                        self.last_valid_test_cell = index
                    else:
                        if index <= self.last_executed_cell:
                            self._invalidate_execution(index)
                        # No output is valid after this.
                        self.last_valid_output_cell = min(self.last_valid_output_cell, index - 1)
                        # Invalidate unit tests: target code changed
                        if cell.metadata.get('unit_tests'):
                            self._invalidate_all_unit_tests(index, 'target_output')
                        # Invalidate downstream unit tests: upstream code changed
                        for j in range(index + 1, len(self.nb.cells)):
                            if self.nb.cells[j].metadata.get('unit_tests'):
                                self._invalidate_all_unit_tests(j, 'setup_code')
                        self.last_valid_code_cell = index
                    # Persist the code fix durably before the (best-effort) amend
                    # call below, so a slow or failing amend never loses the fix.
                    self._write()

                    # Amend the description so a clean-slate regeneration would
                    # avoid the error just fixed. Best-effort, action cells only.
                    amended = None
                    if amend_description and error_context and not is_test:
                        try:
                            amend_fn = AI_PROVIDERS[ai_provider]["amend_explanation"]
                            amended = amend_fn(
                                api_key,
                                cell.metadata.get('explanation'),
                                error_context,
                                buggy_code,
                                new_code,
                                model=model,
                                debug=self.debug,
                                dump_ai_requests=self.dump_ai_requests)
                            if amended and amended.strip():
                                amended = amended.strip()
                                cell.metadata['explanation'] = amended
                                # In sync with the just-generated code. Do NOT lower
                                # last_valid_code_cell/output (that would re-invalidate
                                # the fix we just made).
                                cell.metadata['explanation_timestamp'] = cell.metadata['code_timestamp']
                                # The amended description now describes the current
                                # code, so keep description_hash == code_description_hash.
                                amended_hash = self._hash_text(amended)
                                cell.metadata['description_hash'] = amended_hash
                                cell.metadata['code_description_hash'] = amended_hash
                                self._write()
                            else:
                                amended = None
                        except Exception as e:
                            print(f"Warning: failed to amend explanation for cell {index}: {e}")
                            amended = None
                    return new_code, True, amended
                else:
                    # The request was cancelled, return the current code.
                    return None, False, None
            finally:
                self.ai_request_pending = False


    def execute_test_cell(self, index):
        """Executes a test cell using multistate_execute."""
        with self._lock:
            if index < 0 or index >= len(self.nb.cells):
                raise ExecutionError("Cell index out of range")
            cell = self.nb.cells[index]
            if cell.cell_type != 'test':
                return None

            # Build state mapping from named code cells before this index
            state_mapping = {}
            default_state = None
            for i in range(index):
                c = self.nb.cells[i]
                if c.cell_type == 'code':
                    name = c.metadata.get('name')
                    if name and c.id in self._cell_states:
                        state_mapping[f"__state__{name}"] = self._cell_states[c.id]
                    if c.id in self._cell_states:
                        default_state = self._cell_states[c.id]

            exec_id = uuid.uuid4().hex
            self._current_exec_id = exec_id
            try:
                result = self._sk_request("POST", "/multistate_execute", {
                    "code": cell.source,
                    "exec_id": exec_id,
                    "state_mapping": state_mapping,
                    "default_state": default_state,
                })
            finally:
                self._current_exec_id = None

            # Convert outputs to nbformat objects
            outputs = []
            for out in result.get("output", []):
                outputs.append(nbformat.from_dict(out))
            cell.outputs = outputs

            if result.get("error"):
                err = result["error"]
                error_output = nbformat.from_dict({
                    "output_type": "error",
                    "ename": err.get("ename", "Error"),
                    "evalue": err.get("evalue", ""),
                    "traceback": err.get("traceback", []),
                })
                if not any(o.get("output_type") == "error" for o in cell.outputs):
                    cell.outputs.append(error_output)
                self._write()
                raise CellExecutionError(
                    traceback="\n".join(err.get("traceback", [])),
                    ename=err.get("ename", "Error"),
                    evalue=err.get("evalue", ""),
                )

            cell.outputs.append(nbformat.from_dict({
                "output_type": "stream",
                "name": "stdout",
                "text": "The test passed.\n",
            }))
            self._write()
            return cell.outputs


    def generate_unit_test_cell(self, api_key, cell_index, test_name, role,
                                ai_provider="gemini", model=None, validation_feedback=None,
                                ask_questions=False, skip_regeneration=True):
        """Generate code for a unit test sub-cell."""
        if role == 'target':
            # The target is an ordinary action cell, so it obeys the same
            # global settings as a regular generation.
            return self.generate_code_cell(api_key, cell_index,
                                           ai_provider=ai_provider, model=model,
                                           validation_feedback=validation_feedback,
                                           ask_questions=ask_questions,
                                           skip_regeneration=skip_regeneration)
        assert role in ('setup', 'test'), f"Invalid role: {role}"

        with self._lock:
            assert 0 <= cell_index < len(self.nb.cells)
            target_cell = self.nb.cells[cell_index]
            tests = target_cell.metadata.get('unit_tests', {})
            assert test_name in tests
            unit_test = tests[test_name]
            # Gets the validity status for the unit test.
            test_validity = self._get_ut_validity(cell_index, test_name)

            if self.ai_request_pending:
                raise RuntimeError("An AI request is already pending.")

            # First, check that we can generate code for this role based 
            # on validity of previous code and outputs.
            # For setup, we need the prior cell code to be valid, but also we need the 
            # code of the target cell itself to be valid, so we can know which variables it reads.
            if not self._is_previous_code_and_output_valid(cell_index):
                raise RuntimeError("Cannot generate unit test code: status prior to target cell must be ready for generation.")
            if self.last_valid_code_cell < cell_index:
                raise RuntimeError("Cannot generate unit test code: target code cell code is not valid.")
            if role == 'test':
                # For a test cell, we also need the target output to be valid. 
                if not test_validity['target_output_valid']:
                    raise RuntimeError(f"Missing prerequisite for unit test code generation: role: {role}, validity: {test_validity}.")

            # Common context
            sub_cell = unit_test['cells'][role]
            instructions = self._get_instructions(sub_cell['metadata'].get('explanation', ''))
            files_context = self._get_files_context()
            error_context = self._ut_extract_error_context(sub_cell.get('outputs', []))
            preceding_code = self._get_preceding_code_for_ai(cell_index)

            # Hash of the (persisted) generation context. If the sub-cell's code
            # was already generated from this same context, skip the AI and reuse
            # the stored source: this avoids regenerating unit-test code on reload
            # (the context is rebuilt from persisted data, not the live kernel),
            # while a changed explanation / target / upstream code still forces
            # a real regeneration.
            gen_sig = self._hash_text("\x00".join([
                sub_cell['metadata'].get('explanation', '') or '',
                target_cell.source or '',
                preceding_code or '',
                files_context or '',
            ]))
            if (validation_feedback is None and not error_context
                    and (sub_cell.get('source') or '').strip()
                    and sub_cell['metadata'].get('generation_context_hash') == gen_sig):
                test_validity[f'{role}_code_valid'] = True
                self._invalidate_unit_test(
                    cell_index, test_name,
                    'setup_output' if role == 'setup' else 'test_output')
                self._write()
                return sub_cell['source'], True

            # Previous code for the sub-cell being generated
            existing_source = self._get_cell_text_for_ai(sub_cell)
            previous_code = (PREVIOUS_CODE_EXPLANATION_CHANGED.format(code_string=existing_source)
                             if existing_source else None)

            # Role-specific context
            if role == 'setup':
                preceding_code_cell = self._get_preceding_code_cell(cell_index)
                variable_context = self._get_variables_for_ai(preceding_code_cell) if preceding_code_cell else ""
                # Compute variables the target cell accesses that come from previous cells
                prev_variables = preceding_code_cell.metadata.get('variables', {}) if preceding_code_cell else {}
                prev_var_names = set(prev_variables.keys()) - set(self.default_variables.keys())
                target_accessed = self._get_target_accessed_variables(target_cell.source or '')
                relevant_vars = prev_var_names & target_accessed
                if relevant_vars:
                    relevant_info = {k: v for k, v in prev_variables.items() if k in relevant_vars}
                    variables_for_target_context = self._format_variables_for_ai(relevant_info)
                else:
                    variables_for_target_context = None
                setup_cell_context = None  # We're generating setup; previous_code already covers it
                target_cell_context = self._format_ut_subcell_for_ai(target_cell, 'target')
                test_cell_context = None
            else:
                # Role is 'test'.
                target_variables = unit_test['cells'].get('target', {}).get('variables', {})
                variable_context = self._format_variables_for_ai(target_variables)
                variables_for_target_context = None  # Only used for setup
                setup_cell_context = self._format_ut_subcell_for_ai(unit_test['cells']['setup'], 'setup')
                target_cell_context = self._format_ut_subcell_for_ai(target_cell, 'target')
                test_cell_context = None  # We're generating test; previous_code already covers it

            generate_fn = AI_PROVIDERS[ai_provider]["generate_unit_test"]

            # Call AI
            try:
                self.ai_request_pending = True
                new_code = generate_fn(
                    api_key,
                    preceding_code=preceding_code,
                    previous_code=previous_code,
                    instructions=instructions,
                    file_context=files_context,
                    error_context=error_context,
                    variable_context=variable_context,
                    validation_context=validation_feedback,
                    setup_cell_context=setup_cell_context,
                    target_cell_context=target_cell_context,
                    test_cell_context=test_cell_context,
                    variables_for_target_context=variables_for_target_context,
                    role=role,
                    model=model,
                    debug=self.debug,
                    dump_ai_requests=self.dump_ai_requests)
                if self.ai_request_pending:
                    sub_cell['source'] = new_code
                    sub_cell['metadata']['generation_context_hash'] = gen_sig
                    sub_cell['metadata']['code_timestamp'] = datetime.datetime.now().isoformat()
                    sub_cell['outputs'] = []
                    test_validity = self._get_ut_validity(cell_index, test_name)
                    test_validity[f'{role}_code_valid'] = True
                    self._invalidate_unit_test(cell_index, test_name,
                                               'setup_output' if role == 'setup' else 'test_output')
                    self._write()
                    return new_code, True
                else:
                    return None, False
            finally:
                self.ai_request_pending = False


    def cancel_ai_request(self):
        """Cancels any ongoing AI request by interrupting the kernel."""
        self.ai_request_pending = False


    def validate_code_cell(self, api_key, index, ai_provider="gemini", model=None):
        """Validates the code in the cell at index using the specified AI provider."""
        with self._lock:
            if self.ai_request_pending:
                raise RuntimeError("An AI request is already pending.")
            assert 0 <= index < len(self.nb.cells)
            cell = self.nb.cells[index]
            assert cell.cell_type in ('code', 'test')
            code_to_validate = cell.source
            instructions = self._get_instructions(cell.metadata.get('explanation'))
            previous_code = self._get_preceding_code_for_ai(index)
            previous_code_cell = self._get_preceding_code_cell(index)
            variable_context = self._get_variables_for_ai(previous_code_cell) if previous_code_cell else ""
            try:
                self.ai_request_pending = True
                validate_fn = AI_PROVIDERS[ai_provider]["validate"]
                validation_result = validate_fn(api_key, previous_code, code_to_validate,
                                                instructions, variable_context=variable_context,
                                                model=model, debug=self.debug,
                                                dump_ai_requests=self.dump_ai_requests)
                if self.ai_request_pending:
                    validation_result['is_hidden'] = False
                    cell.metadata['validation'] = validation_result
                    self._write()
                    return validation_result
                else:
                    return None
            finally:
                self.ai_request_pending = False


    def explain_code_cell(self, api_key, index, level=DEFAULT_EXPLANATION_DETAIL_LEVEL, use_bullets=DEFAULT_EXPLANATION_USE_BULLETS, use_latex=DEFAULT_EXPLANATION_USE_LATEX, ai_provider="gemini", model=None):
        """Generates a natural-language explanation of the code in the cell at
        index, stored separately from the user's description."""
        with self._lock:
            if self.ai_request_pending:
                raise RuntimeError("An AI request is already pending.")
            assert 0 <= index < len(self.nb.cells)
            cell = self.nb.cells[index]
            assert cell.cell_type in ('code', 'test')
            code_to_explain = cell.source
            instructions = self._get_instructions(cell.metadata.get('explanation'))
            previous_code = self._get_preceding_code_for_ai(index)
            previous_code_cell = self._get_preceding_code_cell(index)
            variable_context = self._get_variables_for_ai(previous_code_cell) if previous_code_cell else ""
            try:
                self.ai_request_pending = True
                explain_fn = AI_PROVIDERS[ai_provider]["explain"]
                explanation = explain_fn(api_key, previous_code, code_to_explain,
                                         instructions, variable_context=variable_context,
                                         level=level, use_bullets=use_bullets, use_latex=use_latex,
                                         model=model, debug=self.debug,
                                         dump_ai_requests=self.dump_ai_requests)
                if self.ai_request_pending:
                    explanation = explanation.strip()
                    # Store in a separate field so we don't override the user's prompt.
                    cell.metadata['ai_code_explanation'] = explanation
                    cell.metadata['ai_code_explanation_timestamp'] = datetime.datetime.now().isoformat()
                    # Pin the explanation to the exact code it describes, so it is
                    # dropped when the code later changes.
                    cell.metadata['code_hash_for_code_explanation'] = self._hash_text(code_to_explain)
                    self._write()
                    return explanation, index
                else:
                    return None, None
            finally:
                self.ai_request_pending = False


    def validate_unit_test_cell(self, api_key, cell_index, test_name, role,
                                ai_provider="gemini", model=None):
        """Validates the code of a unit test sub-cell (setup or test).
        For target role, delegates to validate_code_cell."""
        if role == 'target':
            return self.validate_code_cell(api_key, cell_index,
                                           ai_provider=ai_provider, model=model)
        assert role in ('setup', 'test'), f"Invalid role: {role}"
        with self._lock:
            if self.ai_request_pending:
                raise RuntimeError("An AI request is already pending.")
            assert 0 <= cell_index < len(self.nb.cells)
            target_cell = self.nb.cells[cell_index]
            tests = target_cell.metadata.get('unit_tests', {})
            assert test_name in tests
            unit_test = tests[test_name]
            sub_cell = unit_test['cells'][role]
            code_to_validate = sub_cell.get('source', '')
            instructions = self._get_instructions(sub_cell.get('metadata', {}).get('explanation', ''))
            # Build context similar to generate_unit_test_cell
            preceding_code = self._get_preceding_code_for_ai(cell_index)
            if role == 'setup':
                previous_code_cell = self._get_preceding_code_cell(cell_index)
                variable_context = self._get_variables_for_ai(previous_code_cell) if previous_code_cell else ""
            else:
                target_variables = unit_test['cells'].get('target', {}).get('variables', {})
                variable_context = self._format_variables_for_ai(target_variables)
            try:
                self.ai_request_pending = True
                validate_fn = AI_PROVIDERS[ai_provider]["validate"]
                validation_result = validate_fn(
                    api_key, preceding_code, code_to_validate,
                    instructions, variable_context=variable_context,
                    model=model, debug=self.debug,
                    dump_ai_requests=self.dump_ai_requests)
                if self.ai_request_pending:
                    validation_result['is_hidden'] = False
                    sub_cell.setdefault('metadata', {})['validation'] = validation_result
                    self._write()
                    return validation_result
                else:
                    return None
            finally:
                self.ai_request_pending = False

    def set_unit_test_validation_visibility(self, cell_index, test_name, role, is_hidden):
        """Sets the visibility of the validation message for a unit test sub-cell."""
        with self._lock:
            assert 0 <= cell_index < len(self.nb.cells)
            cell = self.nb.cells[cell_index]
            tests = cell.metadata.get('unit_tests', {})
            assert test_name in tests
            assert role in ('setup', 'test')
            sub_cell = tests[test_name]['cells'][role]
            sub_cell.setdefault('metadata', {}).setdefault('validation', {})['is_hidden'] = is_hidden
            self._write()

    def set_validation_visibility(self, cell_index, is_hidden):
        """Sets the visibility of the validation message for a given cell."""
        with self._lock:
            assert 0 <= cell_index < len(self.nb.cells)
            cell = self.nb.cells[cell_index]
            assert cell.cell_type in ('code', 'test'), f"Only code and test cells can have validation; got {cell.cell_type}"
            if 'validation' not in cell.metadata:
                cell.metadata['validation'] = {}
            cell.metadata['validation']['is_hidden'] = is_hidden
            self._write()


    def set_verification_visibility(self, is_hidden):
        """Sets the visibility of the notebook-level verification verdict bar."""
        with self._lock:
            verification = self.nb.metadata.get('verification')
            if verification:
                verification['is_hidden'] = is_hidden
                self._write()


    def _clear_verification(self):
        """Drop any stored notebook-level verification verdict and its host/path
        binding. Not currently called from any invalidation path (we trust the
        user's edits and let the host/path hash flag mismatches), but kept as a
        primitive for callers that do want to invalidate a verdict."""
        self.nb.metadata.pop('verification', None)
        self.nb.metadata.pop('verified_hash', None)


    def _compute_notebook_hash(self):
        """Hash of (machine id, absolute notebook path). Stored alongside a
        verification result so the verdict is only trusted when the notebook is
        opened from the same path on the same machine where it was verified."""
        try:
            host_id = machineid.id()
        except Exception:
            host_id = ''
        path = os.path.abspath(self.path) if self.path else ''
        return hashlib.sha256(f"{host_id}:{path}".encode("utf-8")).hexdigest()


    def get_verification_status(self):
        """Returns one of:
          'ok'        -- last verification passed AND it was performed on this
                         host/path.
          'mismatch'  -- a verified_hash is stored but no longer matches this
                         host/path (notebook was moved or copied).
          'none'      -- never verified, verification was cleared, or the last
                         verification did not pass."""
        verification = self.nb.metadata.get('verification') or {}
        stored = self.nb.metadata.get('verified_hash')
        if not stored:
            return 'none'
        if stored != self._compute_notebook_hash():
            return 'mismatch'
        return 'ok' if verification.get('is_valid') else 'none'


    def _format_test_cell_for_verify(self, cell):
        """Like _get_cell_text_for_ai, but for test cells in the verify-tests path:
        only the code is included (no description, no outputs). The post-execution
        variables are appended by the caller."""
        lines = cell.source.split("\n")
        name = cell.metadata.get('name')
        header = f"# Test cell {name}:\n" if name else "# Test cell:\n"
        return header + "\n".join(lines) + "\n\n"


    def _build_verify_notebook_payload(self):
        """Builds the user-message payload for NOTEBOOK_VERIFY_INSTRUCTIONS.
        Includes every non-test code cell with description, code, post-execution
        variables, and (gated by share_output_with_ai) outputs."""
        parts = []
        for i, cell in enumerate(self.nb.cells):
            if cell.cell_type != 'code':
                continue
            name = cell.metadata.get('name') or f"cell {i}"
            explanation = cell.metadata.get('explanation', '') or ''
            section = [f"=== {name} ==="]
            section.append("DESCRIPTION:")
            section.append(explanation.strip() or "(no description provided)")
            section.append("")
            section.append(self._get_cell_text_for_ai(cell).rstrip())
            variables = cell.metadata.get('variables', {}) or {}
            var_text = self._format_variables_for_ai(variables)
            section.append("VARIABLES AFTER EXECUTION:")
            section.append(var_text if var_text else "(none)")
            section.append("")
            parts.append("\n".join(section))
        return "\n\n".join(parts)


    def _build_verify_tests_payload(self):
        """Builds the user-message payload for TEST_VERIFY_INSTRUCTIONS.
        Includes every test cell with code and post-execution variables only."""
        parts = []
        for i, cell in enumerate(self.nb.cells):
            if cell.cell_type != 'test':
                continue
            name = cell.metadata.get('name') or f"test cell {i}"
            section = [f"=== {name} ==="]
            section.append(self._format_test_cell_for_verify(cell).rstrip())
            variables = cell.metadata.get('variables', {}) or {}
            var_text = self._format_variables_for_ai(variables)
            section.append("VARIABLES AT EXECUTION TIME:")
            section.append(var_text if var_text else "(none)")
            section.append("")
            parts.append("\n".join(section))
        return "\n\n".join(parts)


    def verify_notebook(self, api_key, ai_provider="gemini", model=None):
        """Audit the whole notebook with two batched AI calls.

        Caller must have already executed the notebook (so cell variables and
        outputs are fresh) -- this method does not run any cells itself.

        Returns a combined verdict dict {is_valid, is_hidden, message,
        notebook: {is_valid, message}, tests?: {is_valid, message}}, and stores
        it on self.nb.metadata['verification'] so it survives reload."""
        with self._lock:
            if self.ai_request_pending:
                raise RuntimeError("An AI request is already pending.")
            provider = AI_PROVIDERS[ai_provider]
            verify_notebook_fn = provider["verify_notebook"]
            verify_tests_fn = provider["verify_tests"]

            has_code_cells = any(c.cell_type == 'code' for c in self.nb.cells)
            has_test_cells = any(c.cell_type == 'test' for c in self.nb.cells)
            try:
                self.ai_request_pending = True
                notebook_result = None
                if has_code_cells:
                    payload = self._build_verify_notebook_payload()
                    notebook_result = verify_notebook_fn(
                        api_key, payload, model=model,
                        debug=self.debug, dump_ai_requests=self.dump_ai_requests)
                if not self.ai_request_pending:
                    return None

                tests_result = None
                if has_test_cells:
                    payload = self._build_verify_tests_payload()
                    tests_result = verify_tests_fn(
                        api_key, payload, model=model,
                        debug=self.debug, dump_ai_requests=self.dump_ai_requests)
                if not self.ai_request_pending:
                    return None

                # Compose a single markdown message with both sub-results so the
                # client can render it directly.
                pieces = []
                if notebook_result is not None:
                    pieces.append("### Notebook")
                    if notebook_result['is_valid']:
                        pieces.append("OK")
                    else:
                        pieces.append(notebook_result['message'] or "Violations were reported.")
                if tests_result is not None:
                    pieces.append("### Tests")
                    if tests_result['is_valid']:
                        pieces.append("OK")
                    else:
                        pieces.append(tests_result['message'] or "Violations were reported.")
                combined_valid = (
                    (notebook_result is None or notebook_result['is_valid']) and
                    (tests_result is None or tests_result['is_valid'])
                )
                combined = {
                    'is_valid': combined_valid,
                    'is_hidden': False,
                    'message': "\n\n".join(pieces).strip(),
                    'timestamp': datetime.datetime.now().isoformat(),
                }
                if notebook_result is not None:
                    combined['notebook'] = notebook_result
                if tests_result is not None:
                    combined['tests'] = tests_result
                self.nb.metadata['verification'] = combined
                # Bind this verdict to the current host + path so a moved or
                # copied notebook is shown as untrusted (mismatch state).
                self.nb.metadata['verified_hash'] = self._compute_notebook_hash()
                self._write()
                return combined
            finally:
                self.ai_request_pending = False


    def clear_outputs(self):
        """Clears all cell outputs (including unit test sub-cells) and resets execution/output state."""
        with self._lock:
            for cell in self.nb.cells:
                if cell.cell_type in ('code', 'test'):
                    self._drop_outputs(cell)
                    # Also clear unit test sub-cell outputs
                    for unit_test in cell.metadata.get('unit_tests', {}).values():
                        unit_test['cells']['setup']['outputs'] = []
                        if 'target' in unit_test['cells']:
                            unit_test['cells']['target']['outputs'] = []
                        unit_test['cells']['test']['outputs'] = []
            self.last_executed_cell = -1
            self.last_valid_output_cell = -1
            self._live_states.clear()
            self._write()

    def set_input_files(self, files, missing_files=[]):
        """Sets the input files for the notebook. Condition-2: for any file that
        LEFT the set (deleted, or replaced by a different-path file), regenerate
        only the code cells whose source cites that file's path — not every cell.
        A pure file *add* changes nothing. (This is also called on every
        Files-tab mount with the unchanged selection, hence the diff.)"""
        with self._lock:
            paths = lambda lst: {f.get('path') for f in (lst or [])}
            old = (paths(self.nb.metadata.get('input_files'))
                   | paths(self.nb.metadata.get('missing_input_files')))
            new = paths(files) | paths(missing_files)
            self.nb.metadata['input_files'] = files
            self.nb.metadata['missing_input_files'] = missing_files
            self._invalidate_cells_for_removed_files(old - new)
            self._write()


    def get_input_files(self):
        """Returns the input files for the notebook."""
        with self._lock:
            return dict(
                input_files=self.nb.metadata.get('input_files', []),
                missing_input_files=self.nb.metadata.get('missing_input_files', [])
            )


    def set_ai_instructions(self, instructions):
        """Sets the notebook-wide AI instructions."""
        with self._lock:
            self.nb.metadata['ai_instructions'] = instructions
            self._write()

    def get_ai_instructions(self):
        """Returns the notebook-wide AI instructions."""
        with self._lock:
            return self.nb.metadata.get('ai_instructions', '')

    def _get_files_context(self):
        """Builds the AI context including input files."""
        context_parts = [
            "Here is a list of file names and paths. "
            "The user may mention input files; to access them, the full path should be used."
            ]
        for file in self.nb.metadata.get('input_files', []):
            context_parts.append(f"* File name: {file['name']} path: {file['path']}\n")
        return "\n".join(context_parts) + "\n"


    def _get_existing_cell_names(self, exclude_index=None):
        """Returns a set of all cell names currently in the notebook.
        If exclude_index is given, the name of that cell is omitted.
        Must be called with self._lock held."""
        names = set()
        for i, cell in enumerate(self.nb.cells):
            if i == exclude_index:
                continue
            name = cell.metadata.get('name')
            if name:
                names.add(name)
        return names

    def _make_unique_name(self, name, existing_names):
        """Appends _1, _2, etc. if name already exists."""
        if name not in existing_names:
            return name
        counter = 1
        while f"{name}_{counter}" in existing_names:
            counter += 1
        return f"{name}_{counter}"

    def generate_cell_name(self, api_key, index, ai_provider, model=None):
        """Generates a unique name for a code cell based on its explanation.
        Always returns a non-empty, unique name; never returns None and never
        raises on bad inputs."""
        with self._lock:
            if index < 0 or index >= len(self.nb.cells):
                return _generate_random_name()
            cell = self.nb.cells[index]
            existing_name = cell.metadata.get('name')
            if existing_name:
                # Ensure it is still unique among the other cells.
                existing = self._get_existing_cell_names(exclude_index=index)
                if existing_name not in existing:
                    return existing_name
                unique_name = self._make_unique_name(existing_name, existing)
                cell.metadata['name'] = unique_name
                try:
                    self._write()
                except Exception as e:
                    print(f"Error writing notebook for cell {index}: {e}")
                return unique_name
            explanation = str(cell.metadata.get('explanation') or '')
            provider_entry = AI_PROVIDERS.get(ai_provider)
            name_fn = provider_entry["name"] if provider_entry else None
        # Call AI outside the lock (network I/O)
        if not explanation.strip() or name_fn is None:
            raw_name = _generate_random_name()
        else:
            try:
                raw_name = name_fn(api_key, explanation, model=model, debug=self.debug, dump_ai_requests=self.dump_ai_requests)
                if not raw_name or not isinstance(raw_name, str):
                    raw_name = _generate_random_name()
                raw_name = raw_name.strip()
            except Exception as e:
                print(f"Error generating name for cell {index}: {e}")
                raw_name = _generate_random_name()
        # Sanitize: split into words, keep first 3, lowercase, remove punctuation, join with underscores
        words = raw_name.split()[:3]
        words = [re.sub(r'[^a-z0-9]', '', w.lower()) for w in words]
        words = [w for w in words if w]  # Remove empty strings
        sanitized = '_'.join(words)
        if not sanitized:
            sanitized = _generate_random_name()
        with self._lock:
            # Re-check in case another thread set it
            if cell.metadata.get('name'):
                return cell.metadata['name']
            existing = self._get_existing_cell_names(exclude_index=index)
            unique_name = self._make_unique_name(sanitized, existing)
            cell.metadata['name'] = unique_name
            try:
                self._write()
            except Exception as e:
                print(f"Error writing notebook for cell {index}: {e}")
            return unique_name

    def _get_error_context(self, cell_index):
        """If the cell has an error, include its traceback as context.

        Recognises the same two shapes as outputs_have_error(): a formal error
        output, and an error-like stderr stream (a traceback or a warning the
        code printed instead of raising). The formal error wins when both are
        present, since its traceback is the more useful context."""
        context_parts = [
            "The previous attempt to run this cell resulted in this error traceback:"
        ]
        cell = self.nb.cells[cell_index]
        if cell.cell_type != 'code':
            return None
        outputs = getlist(cell.get('outputs', []))
        for output in reversed(outputs):
            if output.get('output_type') == 'error':
                traceback = context_parts + getlist(output.get('traceback', []))
                return "\n".join(traceback)
        for output in reversed(outputs):
            if is_error_like_stderr(output):
                return "\n".join(context_parts + [tostring(output.get('text', ''))])
        return None
