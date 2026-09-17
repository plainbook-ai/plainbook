import ast
import json
import os
import re
import string
from datetime import datetime

SPACES_AND_PUNCTUATION_PATTERN = f"^[{re.escape(string.punctuation + string.whitespace)}]+"

NEWLINE_INDENTATION = '\n    '

CHARS_PER_TOKEN = 4
MAX_TOKENS_PER_ARGUMENT = 10_000
_MAX_CHARS_PER_ARGUMENT = MAX_TOKENS_PER_ARGUMENT * CHARS_PER_TOKEN

SYSTEM_INSTRUCTIONS = """
You are an assistant that writes Python code for Jupyter cells, and your task is to
write the code for one Jupyter cell.
You are given specific instructions on what the new cell should do.
To help write the code, you are also given the previous cells of the Jupyter notebook
(in JSON format), along with their output (if any) and a description of the variables
that are present after executing those cells.
Return ONLY the code, no markdown formatting or explanations.
To display Pandas dataframes, you can simply return the dataframe variable name,
and the notebook will render it appropriately.
"""

# Marks a response that asks questions instead of returning code.
CLARIFY_SENTINEL = "NEEDS_CLARIFICATION"

# Appended to SYSTEM_INSTRUCTIONS when the notebook allows asking questions.
# You decide which of the two responses to give; the notebook handles both.
CLARIFY_INSTRUCTIONS = f"""

You may give one of TWO responses, and it is up to you to choose which:

1. THE CODE. If you know what the cell should do, just write the code, as
   described above. This is the normal case, and what you should do whenever the
   instructions and the context leave you without real doubts.

2. QUESTIONS. If the instructions are genuinely ambiguous, so that a wrong guess
   would produce the wrong result, ask the user instead of guessing.

Choose questions only for doubts that actually change the code you would write.
In particular, do NOT ask about:
- Anything the context already answers. The preceding code, FILE CONTEXT, and
  VARIABLE CONTEXT are available to you; if they settle the point, use them.
- Anything the user has already addressed. Answers to earlier questions are
  folded into the instructions, so if the instructions give you enough to
  proceed, you MUST NOT ask again.
- Refinements you can reasonably decide yourself, such as variable naming,
  formatting, or the choice among equivalent implementations.

To ask questions, respond with EXACTLY this format and NOTHING else (no
preamble, no explanations, no code):
{CLARIFY_SENTINEL}
- <your first question>
- <your second question>

Rules for questions:
- One question per line, each line starting with "- ".
- Ask at most 3 questions.
- Make each question specific and easy to answer (offer the likely options when
  you can).
"""

TEST_SYSTEM_INSTRUCTIONS = """
You are an assistant that writes Python test code for Jupyter notebook test cells.
Your task is to write code that tests the correctness of previous notebook cells.

Test cells can access the state of the notebook after any previous code cell
using the pattern: __state__<cell_name>.<variable_name>
The name of each code cell can be found in its cell.metadata["name"] field
in the notebook JSON provided as context.

For example, if a code cell has metadata name "load_data" and defines a variable `df`,
you access it in the test as: __state__load_data.df

When the instructions mention "this cell" or "the current cell", they refer to
the most recent code cell before this test cell.  The variables in this cell
can be accessed in the test using the same __state__<cell_name>.<variable_name> pattern, 
or they can also be accessed directly as <variable_name> without the __state__ prefix.

You are given the previous cells of the Jupyter notebook (in JSON format),
along with their output (if any) and a description of available variables.
Return ONLY the code, no markdown formatting or explanations.
Use assert statements for testing.
"""

UNIT_TEST_SYSTEM_INSTRUCTIONS = """
You are an assistant that writes Python code for unit tests within a Jupyter-like notebook.
A unit test consists of three phases run in sequence:
1. SETUP: Prepares test data (e.g., creates small sample datasets, mock inputs).
2. TARGET: The notebook cell being tested (you do NOT write this).
3. TEST: Checks that the target cell produced correct results, using assert statements.

You will be asked to generate code for either the SETUP or the TEST phase.
You are given the preceding notebook cells (in JSON format), their outputs, and variable descriptions.
You may also be given the setup cell, target cell, and/or existing test cell for context.

Return ONLY the code, no markdown formatting or explanations.
For the TEST phase, use assert statements to verify correctness.
"""

NAME_GENERATION_INSTRUCTIONS = """You need to summarize what a notebook cell does using two or three words.
You will be given the cell's explanation, which describes what the cell does.
Please return at least 2 words, and at most 3. Return only these words."""

AMEND_EXPLANATION_INSTRUCTIONS = """You maintain the plain-language description of a Jupyter notebook cell.
In this notebook, each cell's Python code is generated automatically from its description.

The code generated for one cell raised an error, and the code has just been corrected.
Revise that cell's description so that, if code were regenerated from scratch using only
the revised description and the surrounding notebook, it would avoid the error that was
just fixed.

Rules:
- Preserve the original intent, scope, wording style, and level of detail.
- Make the SMALLEST change necessary to prevent the error from recurring -- for example a
  required dependency or import, an edge case to handle, an assumption about a column, type,
  or format, an order of operations, or a correction of a factual mistake in the original wording.
- Describe WHAT the cell should do, in plain language, not HOW to write the Python. Do not
  paste code, function names, or snippets into the description unless the original description
  already referred to them.
- Do not mention the error, the fix, or that anything was changed. The result must read as a
  clean, standalone description.
- Keep it concise. If the original description already implies the corrected behavior, return
  it essentially unchanged.

Return ONLY the revised description text, with no markdown fences, headings, quotes, or commentary."""

CHECKING_INSTRUCTIONS = """
You are an assistant that validates Python code for Jupyter cells.
Your task is to check whether a Jupyter notebook cell does what it specified in its instructions.
You are given the instructions, the code of the cell to verify,
and you are also given all previous cells of the Jupyter notebook (in JSON format),
including with their output (if any).
You are also given a description of the variables that are present after executing those
previous cells.
You should return the words YES (if the code meets the instructions) or NO (if it does not),
followed by a brief explanation.
"""

VALIDATION_FEEDBACK_PREAMBLE = """The previous code for this cell does not seem to be correct.
Here are comments on it given by an AI model:"""

EXPLAIN_INSTRUCTIONS = """
You are an assistant that explains Python code in natural language.
Your task is to explain every part of the code provided to you.
The explanation should be aimed at someone who is knowledgeable on the subject matter
(e.g., data science, machine learning) but does not know the syntax of Python or how to code.
The explanation should be clear, concise, and sufficient for a domain expert to understand
the logic and implementation details without needing to read the code themselves.
Do not include markdown code fences in your response, just the natural language explanation.
"""

# Defaults for the "Explain code" options — the single source of truth. Referenced
# by the /explain_code and /set_explain_options endpoints (main.py) and by the
# explain-code functions/method (gemini.py, claude.py, plainbook.py). Change here only.
DEFAULT_EXPLANATION_DETAIL_LEVEL = 1   # 1 Brief .. 4 Expert
DEFAULT_EXPLANATION_USE_BULLETS = False
DEFAULT_EXPLANATION_USE_LATEX = False

# Whether the AI may reply to an action cell with questions instead of code.
DEFAULT_ASK_QUESTIONS = False

# Whether a cell whose description and inputs are unchanged may be left alone
# instead of being regenerated. Off: every generation request calls the AI.
DEFAULT_SKIP_REGENERATION = True

# Whether "Fix Code" also rewrites the cell's description, so that regenerating
# from scratch would avoid the error just fixed. Turned off, fixing an error
# changes the code only, the description the user wrote stands, and the separate
# amend_explanation AI call is not made at all. Read via the settings file in
# main.py; this is the fallback when nothing has been saved.
DEFAULT_FIX_ERROR_AMENDS_DESCRIPTION = True

NOTEBOOK_VERIFY_INSTRUCTIONS = """
You are auditing a Jupyter notebook on behalf of a user who needs assurance that the
notebook is both correct and safe to run.
You will receive every non-test code cell in order. For each cell you are given:
  - the human-written description (the intended behavior),
  - the Python code,
  - the variables present after executing the cell,
  - and possibly the cell's output.

For every cell, verify BOTH of the following:
  (a) The code implements what the description says (no missing steps, no extra steps
      beyond what the description implies, no logic that contradicts it).
  (b) The code performs no dangerous operations. Treat as dangerous, in particular:
      deleting or overwriting files (os.remove, shutil.rmtree, Path.unlink, open(..., 'w')
      on paths the description does not call out), modifying environment variables,
      mutating system configuration or registry, executing shell commands
      (os.system, subprocess.*, !shell, %%bash), installing packages,
      and network calls to hosts the description does not mention.
      Reading input files the description references is NOT dangerous.

Reply on the very first line with EXACTLY one of these tokens:
  OK            -- if every cell passes both (a) and (b).
  VIOLATIONS    -- if any cell fails either check.

If VIOLATIONS, follow on the next line with a markdown bullet list. Each bullet must
name the offending cell (use its name if given, else "cell N") and describe the issue
in one sentence. Do not include any other prose.
"""

TEST_VERIFY_INSTRUCTIONS = """
You are auditing the test cells of a Jupyter notebook for safety only.
You will receive every test cell in order. For each cell you are given the Python code
and the variables present at the time of execution. You are NOT given a description and
you should NOT verify whether the test logic is "correct" -- only whether it is safe.

Verify that no test cell performs dangerous operations. Treat as dangerous, in particular:
deleting or overwriting files (os.remove, shutil.rmtree, Path.unlink, open(..., 'w') on
arbitrary paths), modifying environment variables, mutating system configuration,
executing shell commands (os.system, subprocess.*, !shell, %%bash), installing packages,
and network calls. Assertions, comparisons, and reads of in-memory variables are fine.

Reply on the very first line with EXACTLY one of these tokens:
  OK            -- if every test cell is safe.
  VIOLATIONS    -- if any test cell performs a dangerous operation.

If VIOLATIONS, follow on the next line with a markdown bullet list. Each bullet must
name the offending test cell (use its name if given, else "test cell N") and describe
the dangerous operation in one sentence. Do not include any other prose.
"""

VARIABLES_FOR_TARGET_DESCRIPTION = """In generating the test setup, the goal is to set the value of these variables, 
possibly simplifying them if they are long or complex, so that a human can make sense of their values 
and can check the results of the execution of the test cell.  The variables are these:\n"""

UNIT_TEST_SETUP_ROLE = """You are asked to generate code for the setup cell, 
which is in charge of setting up the precise conditions in which the target cell is executed.
If you generate values for any variables or datasets, please keep them as simple as possible while still being valid,
so a human can easily understand them and check the results.  
If you generate any data, display it, so users know the inputs of the computation.
"""

UNIT_TEST_TEST_ROLE = """You are asked to generate code for the test cell, 
which needs to check whether the unit test succeeded.  Below is the assertion that you need to verify.
Generate code to test the validity of the assertion.  
Please check no more, and no less, than the validity of the assertion. 
In particular, do not generate code that checks other aspects of the result just because you expect they should hold.
"""

def build_name_prompt(explanation):
    """Builds the prompt for cell name generation."""
    return f"""This is the cell explanation:
{explanation}

Summarize what this cell does in 2-3 words:"""


def build_amend_explanation_prompt(explanation, error_context, previous_code, new_code):
    """Builds the prompt for amending a cell's description after its code was fixed."""
    error_context = truncate_to_token_limit(error_context)
    previous_code = truncate_to_token_limit(previous_code)
    new_code = truncate_to_token_limit(new_code)
    return f"""Original description of the cell:
{explanation}

When code was generated from that description and run, it produced this error:
{error_context}

The code that produced the error:
{previous_code}

The corrected code, which now runs without the error:
{new_code}

Revise the original description, following the rules, so that regenerating code from it
would avoid this error. Return only the revised description:"""


FOLD_SYSTEM_INSTRUCTIONS = """
You are consolidating the plain-language description of a single notebook cell.
You are given an ORIGINAL description, followed by a list of ADDITIONAL GUIDANCE
items that were appended incrementally to refine what the cell should do.

Rewrite the ORIGINAL description so that it fully incorporates every item of
ADDITIONAL GUIDANCE, as if the whole thing had been written that way from the
start. The result must read as one coherent, natural description authored by a
single person for another reader.

Rules:
- Do NOT add, remove, or infer any behavior beyond what is stated in the
  original description and the guidance items.
- Where a guidance item conflicts with the original (or with an earlier
  guidance item), the LATER instruction wins; drop the superseded wording.
- Preserve the original voice and level of detail. Do not add commentary,
  headings, preambles, or explanations of your changes.
- Return ONLY the rewritten description text, nothing else.
"""


def build_fold_prompt(explanation, additions):
    """Builds the prompt to fold `additions` (oldest first) into the explanation."""
    guidance = "\n".join(f"- {a}" for a in additions)
    return f"""ORIGINAL description:
{explanation}

ADDITIONAL GUIDANCE (in the order it was added, oldest first; later items win on conflict):
{guidance}

Rewritten description:"""


# Session-level token accumulator
_session_tokens = {"input": 0, "output": 0}

def add_tokens(input_tokens, output_tokens=None):
    """Accumulate token usage from an AI API call."""
    _session_tokens["input"] += input_tokens or 0
    _session_tokens["output"] += output_tokens or 0

def get_session_tokens():
    """Return current session token totals."""
    return dict(_session_tokens)

def reset_session_tokens():
    """Zero out session token counters."""
    _session_tokens["input"] = 0
    _session_tokens["output"] = 0


def _chars_and_tokens(n):
    """Format a char count with approximate token count."""
    return f"{n} chars (~{n // CHARS_PER_TOKEN} tokens)"


def _breakdown_preceding(preceding_json):
    """Parse preceding notebook JSON and return char counts per category."""
    if not preceding_json:
        return {}
    try:
        nb = json.loads(preceding_json)
    except (json.JSONDecodeError, TypeError):
        return {}
    description_chars = 0
    code_chars = 0
    output_chars = 0
    variable_chars = 0
    for cell in nb.get("cells", []):
        cell_type = cell.get("cell_type", "")
        source = cell.get("source", "")
        outputs = cell.get("outputs", [])
        metadata = cell.get("metadata", {})
        if cell_type == "markdown":
            description_chars += len(source)
        elif cell_type == "code":
            explanation = metadata.get("explanation", "")
            description_chars += len(explanation)
            code_chars += len(source)
        if outputs:
            output_chars += len(json.dumps(outputs, default=str))
        variables = metadata.get("variables")
        if variables:
            variable_chars += len(json.dumps(variables, default=str))
    return {
        "description": description_chars,
        "code": code_chars,
        "outputs": output_chars,
        "variables": variable_chars,
    }


def log_ai_request_size(label, system_instructions, prompt, *,
                         preceding=None, instructions=None, previous=None,
                         file_context=None, error_context=None,
                         variable_context=None, validation_context=None):
    """Log the size of an AI request when debug mode is on."""
    sys_len = len(system_instructions)
    prompt_len = len(prompt)
    total = sys_len + prompt_len
    print(f"[AI {label}] system={sys_len} prompt={prompt_len} total={total} chars (~{total // CHARS_PER_TOKEN} tokens)", flush=True)
    # Breakdown of preceding notebook context.
    breakdown = _breakdown_preceding(preceding)
    if breakdown:
        parts = [f"{k}={_chars_and_tokens(v)}" for k, v in breakdown.items() if v]
        print(f"  Preceding context:\n    {NEWLINE_INDENTATION.join(parts)}", flush=True)
    # Breakdown of other fields.
    fields = [
        ("instructions", instructions),
        ("previous_code", previous),
        ("file_context", file_context),
        ("error_context", error_context),
        ("variable_context", variable_context),
        ("validation_context", validation_context),
    ]
    parts = [f"{name}={_chars_and_tokens(len(val))}" for name, val in fields if val]
    if parts:
        print(f"  Cell information:\n    {NEWLINE_INDENTATION.join(parts)}", flush=True)


def dump_ai_request(dump_dest, label, request_payload):
    """Dump an AI request either to stdout or to a file in a folder.

    Args:
        dump_dest: True to print to stdout, or a folder path to save as a JSON file.
        label: A short label describing the request (e.g. "claude generate_code").
        request_payload: A dict representing the exact API request parameters.
    """
    if dump_dest is True:
        separator = "=" * 72
        print(separator)
        print(f"[AI REQUEST: {label}]")
        print(separator)
        print(json.dumps(request_payload, indent=4, ensure_ascii=False))
        print(separator, flush=True)
    else:
        os.makedirs(dump_dest, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")[:23]
        safe_label = label.replace(" ", "_")
        filename = f"{timestamp}_{safe_label}.txt"
        filepath = os.path.join(dump_dest, filename)
        separator = "=" * 72
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"[AI REQUEST: {label}]\n")
            for key, value in request_payload.items():
                f.write(f"\n{separator}\n")
                f.write(f"{key}:\n")
                f.write(f"{separator}\n")
                if isinstance(value, str):
                    f.write(value)
                elif isinstance(value, list):
                    # e.g. messages: list of dicts with role/content
                    for item in value:
                        if isinstance(item, dict):
                            for k, v in item.items():
                                f.write(f"\n--- {k} ---\n")
                                f.write(str(v))
                        else:
                            f.write(str(item))
                        f.write("\n")
                else:
                    f.write(str(value))
                f.write("\n")
        print(f"[AI REQUEST: {label}] saved to {filepath}", flush=True)


def clean_start(text):
    return re.sub(SPACES_AND_PUNCTUATION_PATTERN, '', text)


def truncate_to_token_limit(text):
    """Truncate text to fit within the per-argument token limit.
    Keeps the tail (most recent content) and prepends a truncation marker."""
    if not text or len(text) <= _MAX_CHARS_PER_ARGUMENT:
        return text
    return "[...truncated...]\n" + text[-_MAX_CHARS_PER_ARGUMENT:]


def build_context_prompt(
    preceding=None,
    previous=None,
    file_context=None,
    error_context=None,
    variable_context=None,
    validation_context=None):
    preceding = truncate_to_token_limit(preceding)
    previous = truncate_to_token_limit(previous)
    file_context = truncate_to_token_limit(file_context)
    error_context = truncate_to_token_limit(error_context)
    variable_context = truncate_to_token_limit(variable_context)
    validation_context = truncate_to_token_limit(validation_context)
    prompt = f"""
CONTEXT (Existing Notebook Code):
{preceding}

"""
    if previous:
        prompt += previous + "\n\n"
    if error_context:
        prompt += f"""
ERROR CONTEXT:
{error_context}

"""
    if file_context:
        prompt += f"""
FILE CONTEXT:
{file_context}

"""
    if variable_context:
        prompt += f"""
VARIABLE CONTEXT (Variables currently in memory):
{variable_context}

"""
    if validation_context:
        prompt += f"""
VALIDATION FEEDBACK:
{VALIDATION_FEEDBACK_PREAMBLE}
{validation_context}

"""
    return prompt


def build_unit_test_prompt(
    preceding=None,
    previous=None,
    instructions=None,
    file_context=None,
    error_context=None,
    variable_context=None,
    validation_context=None,
    setup_cell_context=None,
    target_cell_context=None,
    test_cell_context=None,
    variables_for_target_context=None,
    role=None):
    """Build prompt for unit test code generation (setup or test role)."""
    prompt = build_context_prompt(
        preceding=preceding,
        previous=previous,
        file_context=file_context,
        error_context=error_context,
        variable_context=variable_context,
        validation_context=validation_context)
    if setup_cell_context:
        prompt += f"""
UNIT TEST SETUP CELL:
{setup_cell_context}

"""
    if target_cell_context:
        prompt += f"""
TARGET CELL BEING TESTED:
{target_cell_context}

"""
    if test_cell_context:
        prompt += f"""
EXISTING TEST CELL:
{test_cell_context}

"""
    if variables_for_target_context:
        prompt += f"""
VARIABLES USED BY TARGET CELL:
{VARIABLES_FOR_TARGET_DESCRIPTION}
{variables_for_target_context}

"""
    role_label = "Setup" if role == "setup" else "Test"
    role_elucidation = UNIT_TEST_SETUP_ROLE if role == "setup" else UNIT_TEST_TEST_ROLE
    prompt += f"""
INSTRUCTIONS for Unit Test {role_label} Cell:
{role_elucidation}

{instructions}

Code:
"""
    return prompt


def strip_markdown_code_fences(code):
    """Strip ```python and ``` markdown fences from generated code,
    tolerating leading/trailing whitespace around the fences."""
    code = code.strip()
    if code.startswith("```python"):
        code = code[len("```python"):].strip()
    elif code.startswith("```"):
        code = code[3:].strip()
    if code.endswith("```"):
        code = code[:-3].strip()
    return code


def _extract_questions(text):
    """Returns the questions in a clarification response, or None if it is not one."""
    lines = (text or "").strip().splitlines()
    # Scan all lines: the sentinel is sometimes preceded by a preamble.
    sentinel_idx = None
    for i, line in enumerate(lines):
        if line.strip().upper().startswith(CLARIFY_SENTINEL):
            sentinel_idx = i
            break
    if sentinel_idx is None:
        return None
    questions = []
    for line in lines[sentinel_idx + 1:]:
        line = line.strip()
        if not line:
            continue
        line = re.sub(r'^([-*•]|\d+[.)])\s*', '', line).strip()
        if line:
            questions.append(line)
    return questions or ["Could you provide more detail about what this cell should do?"]


def parse_generate_response(text):
    """Parse a generation response into (code, None), or (None, questions) if it
    asked for clarification."""
    questions = _extract_questions(text)
    if questions is not None:
        return None, questions

    code = strip_markdown_code_fences(text)
    # A non-code reply would be a SyntaxError on run; surface it as a question.
    try:
        ast.parse(code)
    except SyntaxError:
        msg = code.strip()
        if msg:
            return None, [msg]
    return code, None


# The verdict is asked for as a bare YES or NO at the start of the reply, but
# models dress it up: Claude has been seen to answer "**YES**", and a heading, a
# block quote, a list marker, surrounding quotes or a tick are all just as
# likely. Rather than enumerate the decorations, skip everything at the front
# that is not a letter and read the letters that follow: if they spell YES or NO
# and a letter does not continue them, that is the verdict. A plain
# startswith("YES") saw none of this and fell through to the "no verdict"
# branch, which reports the cell as invalid -- so a model saying YES was shown
# to the user in a red bar.
# Matched, rather than searched, on purpose: a YES or NO further into the text is
# prose, not a verdict, and "there is no error" would read as a rejection.
# The trailing guard is a lookahead for a letter rather than \b, because \b
# treats the underscore of "__YES__" as a word character and so would not fire
# there. Either way it stops "NOTE:" and "Nothing is wrong" matching NO, which
# the old startswith("NO") did not: both were read as rejections.
VALIDATION_VERDICT_PATTERN = re.compile(
    r"""^[^A-Za-z]*              # whatever precedes the verdict: ** ## > - " ` ( space
        (?P<verdict>YES|NO)      # the verdict, in any case...
        (?![A-Za-z])             # ...not merely the start of NOTE or YESTERDAY
    """,
    re.IGNORECASE | re.VERBOSE,
)


def parse_validation_response(text):
    """Parse a YES/NO validation response into a result dict.

    The verdict decides is_valid but is left in the message: the user should see
    what the model actually said, and the pattern only has to recognise the
    verdict, not excise it. (Removing it was fiddly as well as unwanted -- it
    meant deciding whether a dash after the verdict was a separator or the first
    bullet of the explanation.)"""
    r = (text or "").strip()
    match = VALIDATION_VERDICT_PATTERN.match(r)
    if match:
        return dict(is_valid=match.group("verdict").upper() == "YES", message=r)
    # No verdict to be found. Fail closed -- an unreviewed cell must not look
    # approved -- but say why, because the reply itself may read as approval and
    # a bare red bar over approving text is baffling.
    return dict(is_valid=False,
                message="The AI did not begin its answer with YES or NO, so its "
                        "verdict could not be read. Its reply follows.\n\n" + r)


def parse_verify_response(text):
    """Parse an OK / VIOLATIONS verification response into a result dict.
    The first line carries the verdict; the rest is the (markdown) message body."""
    r = text.strip()
    first, _, rest = r.partition("\n")
    head = first.strip().upper()
    body = rest.strip()
    if head.startswith("OK"):
        return dict(is_valid=True, message=body)
    if head.startswith("VIOLATIONS"):
        # If the model did not include any body, surface a generic message so the
        # red bar is never empty.
        return dict(is_valid=False, message=body or "Violations were reported but no details were given.")
    # Fallback: model did not follow the protocol -- treat as a violation and
    # show the entire response so the user can see what happened.
    return dict(is_valid=False, message=r)
