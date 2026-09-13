"""Interface to OpenAI models, parallel to claude.py and gemini.py.

This module is named openai.py but imports the `openai` SDK: under absolute
imports that resolves to the installed package, not to this file, as long as
plainbook is run as a package (the `plainbook` entry point or
`python -m plainbook.main`), which is how it is always launched."""
import os
import re

import openai

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

# Fallback when no model is passed.  Override with OPENAI_MODEL.
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5")

# Output caps.  Reasoning models spend part of max_output_tokens on reasoning,
# so these are roomier than the equivalent Claude caps.
MAX_TOKENS_CODE = 16384
MAX_TOKENS_TEXT = 8192
MAX_TOKENS_SHORT = 4096
MAX_TOKENS_NAME = 256


def _get_client(api_key):
    return openai.OpenAI(api_key=api_key)


def list_openai_models(api_key):
    """Returns every model the OpenAI API offers, as a list of
    (model_id, created) tuples (created is a Unix timestamp)."""
    client = _get_client(api_key)
    return [(m.id, m.created) for m in client.models.list()]


# General-purpose text models are "gpt-<version>" optionally followed by ONE
# alphabetic word: a size tier (mini, nano) or a codename (e.g. gpt-6-astra).
# Anything else -- dated snapshots (gpt-5-2025-08-07), multi-word variants
# (gpt-5.2-chat-latest, gpt-5-search-api), gpt-4o, o3, gpt-image-2 -- is not
# matched.  Known specialised single-word variants are excluded explicitly.
_OPENAI_ID_RE = re.compile(r"^gpt-(?P<version>\d+(?:\.\d+)*)(?:-(?P<tier>[a-z]+))?$")
_OPENAI_SPECIALISED = {"pro", "codex", "chat", "search", "audio", "realtime",
                       "image", "transcribe", "live", "turbo", "instruct"}
# Tiers listed first, in this order; other tiers (codenames) follow, newest first.
_OPENAI_TIER_ORDER = ["", "mini", "nano"]


def _parse_openai_id(model_id):
    """Returns (version_tuple, tier) for a general-purpose GPT model id, or
    None.  The flagship tier is ""."""
    m = _OPENAI_ID_RE.match(model_id)
    if not m:
        return None
    tier = m.group("tier") or ""
    if tier in _OPENAI_SPECIALISED:
        return None
    version = tuple(int(x) for x in m.group("version").split("."))
    return version, tier


def _openai_name(version, tier):
    return f"GPT-{'.'.join(map(str, version))}" + (f" {tier.capitalize()}" if tier else "")


def select_openai_providers(models):
    """Builds the provider entries for the GPT tiers found in `models` (a list
    of (model_id, created) as returned by list_openai_models).  For each tier,
    returns the highest-version model and, when there is one, the model of the
    previous version.  Entries have the shape used by AI_PROVIDER_REGISTRY:
    {id, name, major, key_setting, model}."""
    by_tier = {}  # tier -> list of (version, created, model_id)
    for model_id, created in models:
        info = _parse_openai_id(model_id)
        if info:
            version, tier = info
            by_tier.setdefault(tier, []).append((version, created, model_id))

    def tier_order(tier):
        if tier in _OPENAI_TIER_ORDER:
            return (0, _OPENAI_TIER_ORDER.index(tier), "")
        newest = max(c for _, c, _ in by_tier[tier])
        return (1, -newest, tier)

    providers = []
    for tier in sorted(by_tier, key=tier_order):
        picks = []
        for version, _, model_id in sorted(by_tier[tier], reverse=True):
            if not picks:
                picks.append((version, model_id))
            elif len(picks) == 1 and version != picks[0][0]:
                picks.append((version, model_id))
        for i, (version, model_id) in enumerate(picks):
            providers.append({
                "id": "openai:gpt" + (f"-{tier}" if tier else "") + ("-prev" if i else ""),
                "name": _openai_name(version, tier),
                "major": "openai",
                "key_setting": "openai_api_key",
                "model": model_id,
            })
    return providers


def _respond(client, model, system, prompt, max_output_tokens, label,
             debug=False, dump_ai_requests=False, reasoning_effort=None, **log_fields):
    """Sends one request through the Responses API and returns the output text.
    Handles the bookkeeping shared by every call: request-size logging, request
    dumping, token accounting, debug printing.  `reasoning_effort`, when given,
    is sent as the reasoning effort; models that do not accept the parameter
    reject it with a BadRequestError, in which case the request is retried
    without it."""
    if debug:
        log_ai_request_size(f"openai {label}", system, prompt, **log_fields)
    request = {
        "model": model,
        "instructions": system,
        "input": prompt,
        "max_output_tokens": max_output_tokens,
    }
    if reasoning_effort:
        request["reasoning"] = {"effort": reasoning_effort}
    if dump_ai_requests:
        dump_ai_request(dump_ai_requests, f"openai {label}", request)
    try:
        response = client.responses.create(**request)
    except openai.BadRequestError:
        if "reasoning" not in request:
            raise
        del request["reasoning"]
        response = client.responses.create(**request)
    add_tokens(response.usage.input_tokens, response.usage.output_tokens)
    text = response.output_text
    if debug:
        if response.status == "incomplete":
            reason = response.incomplete_details and response.incomplete_details.reason
            print(f"Warning: openai {label} response incomplete ({reason})")
        print("Response:", text)
    return text


def openai_generate_code(
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
    client = _get_client(api_key)
    model = model or OPENAI_MODEL

    system_instructions = SYSTEM_INSTRUCTIONS
    if ask_questions:
        system_instructions += CLARIFY_INSTRUCTIONS

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
        client, model, system_instructions, prompt, MAX_TOKENS_CODE, "generate_code",
        debug=debug, dump_ai_requests=dump_ai_requests,
        preceding=preceding_code, instructions=instructions,
        previous=previous_code, file_context=file_context,
        error_context=error_context, variable_context=variable_context,
        validation_context=validation_context)
    if ask_questions:
        return parse_generate_response(response_text)
    return strip_markdown_code_fences(response_text), None


def openai_amend_explanation(
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
    client = _get_client(api_key)
    model = model or OPENAI_MODEL
    prompt = build_amend_explanation_prompt(
        explanation, error_context, previous_code, new_code)
    response_text = _respond(
        client, model, AMEND_EXPLANATION_INSTRUCTIONS, prompt, MAX_TOKENS_SHORT,
        "amend_explanation", debug=debug, dump_ai_requests=dump_ai_requests)
    return response_text.strip()


def openai_generate_test_code(
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
    client = _get_client(api_key)
    model = model or OPENAI_MODEL

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
        client, model, TEST_SYSTEM_INSTRUCTIONS, prompt, MAX_TOKENS_CODE, "generate_test_code",
        debug=debug, dump_ai_requests=dump_ai_requests,
        preceding=preceding_code, instructions=instructions,
        previous=previous_code, file_context=file_context,
        error_context=error_context, variable_context=variable_context,
        validation_context=validation_context)
    return strip_markdown_code_fences(response_text)


def openai_generate_unit_test_code(
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
    client = _get_client(api_key)
    model = model or OPENAI_MODEL

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
        client, model, UNIT_TEST_SYSTEM_INSTRUCTIONS, prompt, MAX_TOKENS_CODE, "generate_unit_test",
        debug=debug, dump_ai_requests=dump_ai_requests,
        preceding=preceding_code, instructions=instructions,
        previous=previous_code, file_context=file_context,
        error_context=error_context, variable_context=variable_context,
        validation_context=validation_context)
    return strip_markdown_code_fences(response_text)


def openai_validate_code(api_key, previous_code, code_to_validate, instructions, variable_context=None, model=None, debug=False, dump_ai_requests=False):
    client = _get_client(api_key)
    model = model or OPENAI_MODEL

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
        client, model, CHECKING_INSTRUCTIONS, prompt, MAX_TOKENS_SHORT, "validate_code",
        debug=debug, dump_ai_requests=dump_ai_requests,
        preceding=previous_code, instructions=instructions,
        variable_context=variable_context)
    return parse_validation_response(response_text)


def openai_explain_code(api_key, previous_code, code_to_explain, instructions, variable_context=None, level=DEFAULT_EXPLANATION_DETAIL_LEVEL, use_bullets=DEFAULT_EXPLANATION_USE_BULLETS, use_latex=DEFAULT_EXPLANATION_USE_LATEX, model=None, debug=False, dump_ai_requests=False):
    client = _get_client(api_key)
    model = model or OPENAI_MODEL

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
        client, model, EXPLAIN_INSTRUCTIONS, prompt, MAX_TOKENS_TEXT, "explain_code",
        debug=debug, dump_ai_requests=dump_ai_requests,
        preceding=previous_code, instructions=instructions,
        variable_context=variable_context)


def _openai_verify(api_key, system_instructions, payload, label, model=None,
                   debug=False, dump_ai_requests=False):
    client = _get_client(api_key)
    model = model or OPENAI_MODEL
    response_text = _respond(
        client, model, system_instructions, payload, MAX_TOKENS_TEXT, label,
        debug=debug, dump_ai_requests=dump_ai_requests)
    return parse_verify_response(response_text)


def openai_verify_notebook(api_key, payload, model=None, debug=False, dump_ai_requests=False):
    return _openai_verify(api_key, NOTEBOOK_VERIFY_INSTRUCTIONS, payload,
                          "verify_notebook", model=model, debug=debug,
                          dump_ai_requests=dump_ai_requests)


def openai_verify_tests(api_key, payload, model=None, debug=False, dump_ai_requests=False):
    return _openai_verify(api_key, TEST_VERIFY_INSTRUCTIONS, payload,
                          "verify_tests", model=model, debug=debug,
                          dump_ai_requests=dump_ai_requests)


def openai_fold_additions(api_key, explanation=None, additions=None, model=None,
                          debug=False, dump_ai_requests=False):
    """Rewrites `explanation` to absorb `additions`. Returns the rewritten text."""
    client = _get_client(api_key)
    model = model or OPENAI_MODEL
    prompt = build_fold_prompt(explanation or '', additions or [])
    response_text = _respond(
        client, model, FOLD_SYSTEM_INSTRUCTIONS, prompt, MAX_TOKENS_TEXT, "fold_additions",
        debug=debug, dump_ai_requests=dump_ai_requests, instructions=explanation)
    return response_text.strip()


def openai_generate_cell_name(api_key, explanation, model=None, debug=False, dump_ai_requests=False):
    """A trivial summarization: ask for minimal reasoning, since reasoning would
    only add latency, cost, and eat into the small output cap."""
    client = _get_client(api_key)
    model = model or OPENAI_MODEL
    prompt = build_name_prompt(explanation)
    response_text = _respond(
        client, model, NAME_GENERATION_INSTRUCTIONS, prompt, MAX_TOKENS_NAME, "generate_name",
        debug=debug, dump_ai_requests=dump_ai_requests, reasoning_effort="minimal")
    return response_text.strip()
