"""Interface to a local open-weights model (gpt-oss through Ollama), parallel
to claude.py, gemini.py and openai.py.

The model runs on the user's machine, so there is no API key: the `api_key`
argument every provider function takes is accepted and ignored.  The runtime,
the model download and the server lifecycle live in local_models.py; this
module only builds prompts and parses answers, exactly like the cloud
providers do."""
from . import local_models
from .ai_common import (
    SYSTEM_INSTRUCTIONS,
    TEST_SYSTEM_INSTRUCTIONS,
    UNIT_TEST_SYSTEM_INSTRUCTIONS,
    CHECKING_INSTRUCTIONS,
    EXPLAIN_INSTRUCTIONS,
    DEFAULT_EXPLANATION_DETAIL_LEVEL,
    DEFAULT_EXPLANATION_USE_BULLETS,
    DEFAULT_EXPLANATION_USE_LATEX,
    NAME_GENERATION_INSTRUCTIONS,
    AMEND_EXPLANATION_INSTRUCTIONS,
    NOTEBOOK_VERIFY_INSTRUCTIONS,
    TEST_VERIFY_INSTRUCTIONS,
    CLARIFY_INSTRUCTIONS,
    FOLD_SYSTEM_INSTRUCTIONS,
    add_tokens,
    build_context_prompt,
    build_unit_test_prompt,
    build_name_prompt,
    build_amend_explanation_prompt,
    build_fold_prompt,
    dump_ai_request,
    log_ai_request_size,
    parse_generate_response,
    parse_validation_response,
    parse_verify_response,
    strip_markdown_code_fences,
)

# Fallback when no model is passed: the first catalog entry.
LOCAL_MODEL = local_models.LOCAL_MODEL_CATALOG[0]["backend_name"]

# Output caps (num_predict).  A reasoning model spends part of them on its
# reasoning, so these match the roomy OpenAI caps rather than Claude's.
MAX_TOKENS_CODE = 16384
MAX_TOKENS_TEXT = 8192
MAX_TOKENS_SHORT = 4096
MAX_TOKENS_NAME = 1024

# Reasoning effort per kind of task.  Code and verification get the model's
# default effort; the text-only tasks do not need it.
THINK_CODE = "medium"
THINK_TEXT = "low"

# Small models are chattier than the cloud ones; this goes at the end of the
# system instructions of every call whose output is parsed.
LOCAL_OUTPUT_HINT = "\n\nReply with only the requested content, with no preamble and no closing remarks."


def _think_for(model, effort):
    """The `think` value to send, or None for models without that knob."""
    entry = local_models.catalog_entry_by_backend_name(model)
    if entry is not None and not entry.get("supports_think_levels"):
        return None
    return effort


def _respond(model, system, prompt, max_tokens, label,
             debug=False, dump_ai_requests=False, think=None, **log_fields):
    """Sends one request to the local model and returns the answer text.
    Handles the bookkeeping shared by every call: request-size logging,
    request dumping, token accounting, debug printing."""
    backend = local_models.get_backend()
    think = _think_for(model, think)
    if debug:
        log_ai_request_size(f"local {label}", system, prompt, **log_fields)
    if dump_ai_requests:
        dump_ai_request(dump_ai_requests, f"local {label}",
                        backend.request_payload(model, system, prompt, max_tokens, think))
    content, thinking, input_tokens, output_tokens = backend.chat(
        model, system, prompt, max_tokens, think=think)
    add_tokens(input_tokens, output_tokens)
    if debug:
        if thinking:
            print(f"[local {label}] thinking: {len(thinking)} chars")
        print("Response:", content)
    return content


def local_generate_code(
    api_key,
    preceding_code=None,
    previous_code=None,
    instructions=None,
    file_context=None,
    error_context=None,
    variable_context=None,
    validation_context=None,
    model=None,
    debug=False,
    dump_ai_requests=False,
    ask_questions=False):
    """Returns (code, questions).  Normally the AI returns the code, and
    questions is None; if ask_questions is enabled, the AI may instead return a
    list of questions for the user, in which case code is None."""
    model = model or LOCAL_MODEL

    system_instructions = SYSTEM_INSTRUCTIONS
    if ask_questions:
        system_instructions += CLARIFY_INSTRUCTIONS
    system_instructions += LOCAL_OUTPUT_HINT

    prompt = build_context_prompt(
        preceding=preceding_code,
        previous=previous_code,
        file_context=file_context,
        error_context=error_context,
        variable_context=variable_context,
        validation_context=validation_context)
    prompt += f"""
INSTRUCTIONS for New Cell:
{instructions}

Code:
"""
    response_text = _respond(
        model, system_instructions, prompt, MAX_TOKENS_CODE, "generate_code",
        debug=debug, dump_ai_requests=dump_ai_requests, think=THINK_CODE,
        preceding=preceding_code, instructions=instructions,
        previous=previous_code, file_context=file_context,
        error_context=error_context, variable_context=variable_context,
        validation_context=validation_context)
    if ask_questions:
        return parse_generate_response(response_text)
    return strip_markdown_code_fences(response_text), None


def local_amend_explanation(
    api_key,
    explanation,
    error_context,
    previous_code,
    new_code,
    model=None,
    debug=False,
    dump_ai_requests=False):
    """Revise a cell's plain-language description so that regenerating code from it
    would avoid the error that was just fixed. Returns the amended description text."""
    model = model or LOCAL_MODEL
    prompt = build_amend_explanation_prompt(
        explanation, error_context, previous_code, new_code)
    response_text = _respond(
        model, AMEND_EXPLANATION_INSTRUCTIONS + LOCAL_OUTPUT_HINT, prompt, MAX_TOKENS_SHORT,
        "amend_explanation", debug=debug, dump_ai_requests=dump_ai_requests, think=THINK_TEXT)
    return response_text.strip()


def local_generate_test_code(
    api_key,
    preceding_code=None,
    previous_code=None,
    instructions=None,
    file_context=None,
    error_context=None,
    variable_context=None,
    validation_context=None,
    model=None,
    debug=False,
    dump_ai_requests=False):
    model = model or LOCAL_MODEL

    prompt = build_context_prompt(
        preceding=preceding_code,
        previous=previous_code,
        file_context=file_context,
        error_context=error_context,
        variable_context=variable_context,
        validation_context=validation_context)
    prompt += f"""
INSTRUCTIONS for Test Cell:
{instructions}

Code:
"""
    response_text = _respond(
        model, TEST_SYSTEM_INSTRUCTIONS + LOCAL_OUTPUT_HINT, prompt, MAX_TOKENS_CODE,
        "generate_test_code",
        debug=debug, dump_ai_requests=dump_ai_requests, think=THINK_CODE,
        preceding=preceding_code, instructions=instructions,
        previous=previous_code, file_context=file_context,
        error_context=error_context, variable_context=variable_context,
        validation_context=validation_context)
    return strip_markdown_code_fences(response_text)


def local_generate_unit_test_code(
    api_key,
    preceding_code=None,
    previous_code=None,
    instructions=None,
    file_context=None,
    error_context=None,
    variable_context=None,
    validation_context=None,
    setup_cell_context=None,
    target_cell_context=None,
    test_cell_context=None,
    variables_for_target_context=None,
    role=None,
    model=None,
    debug=False,
    dump_ai_requests=False):
    model = model or LOCAL_MODEL

    prompt = build_unit_test_prompt(
        preceding=preceding_code,
        previous=previous_code,
        instructions=instructions,
        file_context=file_context,
        error_context=error_context,
        variable_context=variable_context,
        validation_context=validation_context,
        setup_cell_context=setup_cell_context,
        target_cell_context=target_cell_context,
        test_cell_context=test_cell_context,
        variables_for_target_context=variables_for_target_context,
        role=role)
    response_text = _respond(
        model, UNIT_TEST_SYSTEM_INSTRUCTIONS + LOCAL_OUTPUT_HINT, prompt, MAX_TOKENS_CODE,
        "generate_unit_test",
        debug=debug, dump_ai_requests=dump_ai_requests, think=THINK_CODE,
        preceding=preceding_code, instructions=instructions,
        previous=previous_code, file_context=file_context,
        error_context=error_context, variable_context=variable_context,
        validation_context=validation_context)
    return strip_markdown_code_fences(response_text)


def local_validate_code(api_key, previous_code, code_to_validate, instructions, variable_context=None, model=None, debug=False, dump_ai_requests=False):
    model = model or LOCAL_MODEL

    prompt = build_context_prompt(
        preceding=previous_code,
        variable_context=variable_context
    )
    prompt += f"""

CODE TO VALIDATE:
{code_to_validate}

INSTRUCTIONS for Validation:
{instructions}

Validation Result:
"""
    response_text = _respond(
        model, CHECKING_INSTRUCTIONS + LOCAL_OUTPUT_HINT, prompt, MAX_TOKENS_SHORT, "validate_code",
        debug=debug, dump_ai_requests=dump_ai_requests, think=THINK_CODE,
        preceding=previous_code, instructions=instructions,
        variable_context=variable_context)
    return parse_validation_response(response_text)


def local_explain_code(api_key, previous_code, code_to_explain, instructions, variable_context=None, level=DEFAULT_EXPLANATION_DETAIL_LEVEL, use_bullets=DEFAULT_EXPLANATION_USE_BULLETS, use_latex=DEFAULT_EXPLANATION_USE_LATEX, model=None, debug=False, dump_ai_requests=False):
    model = model or LOCAL_MODEL

    level_instruction = {
        1: "Provide a BRIEF, high-level summary of the code.",
        2: "Provide a NORMAL explanation of the code, covering the main steps.",
        3: "Provide a DETAILED explanation, covering all significant parts of the logic.",
        4: "Provide an EXTREMELY DETAILED, line-by-line or section-by-section breakdown of everything the code does."
    }.get(level, "Provide a normal explanation.")

    if use_bullets:
        level_instruction += " Use bullet points to organize the explanation."
    if use_latex:
        level_instruction += " Use LaTeX for any mathematical equations (e.g., $x^2$, $$\\frac{a}{b}$$). Do this for any mathematical equations that are NEEDED."
    else:
        level_instruction += " Avoid using LaTeX; use plain text for math if possible."

    prompt = build_context_prompt(
        preceding=previous_code,
        variable_context=variable_context
    )
    prompt += f"""

CODE TO EXPLAIN:
{code_to_explain}

INSTRUCTIONS for original cell description:
{instructions}

EXPLANATION GUIDELINE:
{level_instruction}

Explanation:
"""
    return _respond(
        model, EXPLAIN_INSTRUCTIONS, prompt, MAX_TOKENS_TEXT, "explain_code",
        debug=debug, dump_ai_requests=dump_ai_requests, think=THINK_TEXT,
        preceding=previous_code, instructions=instructions,
        variable_context=variable_context)


def _local_verify(api_key, system_instructions, payload, label, model=None,
                  debug=False, dump_ai_requests=False):
    model = model or LOCAL_MODEL
    response_text = _respond(
        model, system_instructions + LOCAL_OUTPUT_HINT, payload, MAX_TOKENS_TEXT, label,
        debug=debug, dump_ai_requests=dump_ai_requests, think=THINK_CODE)
    return parse_verify_response(response_text)


def local_verify_notebook(api_key, payload, model=None, debug=False, dump_ai_requests=False):
    return _local_verify(api_key, NOTEBOOK_VERIFY_INSTRUCTIONS, payload,
                         "verify_notebook", model=model, debug=debug,
                         dump_ai_requests=dump_ai_requests)


def local_verify_tests(api_key, payload, model=None, debug=False, dump_ai_requests=False):
    return _local_verify(api_key, TEST_VERIFY_INSTRUCTIONS, payload,
                         "verify_tests", model=model, debug=debug,
                         dump_ai_requests=dump_ai_requests)


def local_fold_additions(api_key, explanation=None, additions=None, model=None,
                         debug=False, dump_ai_requests=False):
    """Rewrites `explanation` to absorb `additions`. Returns the rewritten text."""
    model = model or LOCAL_MODEL
    prompt = build_fold_prompt(explanation or '', additions or [])
    response_text = _respond(
        model, FOLD_SYSTEM_INSTRUCTIONS + LOCAL_OUTPUT_HINT, prompt, MAX_TOKENS_TEXT,
        "fold_additions",
        debug=debug, dump_ai_requests=dump_ai_requests, think=THINK_TEXT, instructions=explanation)
    return response_text.strip()


def local_generate_cell_name(api_key, explanation, model=None, debug=False, dump_ai_requests=False):
    model = model or LOCAL_MODEL
    prompt = build_name_prompt(explanation)
    response_text = _respond(
        model, NAME_GENERATION_INSTRUCTIONS + LOCAL_OUTPUT_HINT, prompt, MAX_TOKENS_NAME,
        "generate_name", debug=debug, dump_ai_requests=dump_ai_requests, think=THINK_TEXT)
    return response_text.strip()
