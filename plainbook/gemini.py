import re

from google import genai
from google.genai import types

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


def list_gemini_models(api_key):
    """Returns every model the Gemini API offers, as a list of dicts
    {id, display_name, supported_actions} (id without the "models/" prefix)."""
    client = genai.Client(api_key=api_key)
    models = []
    for model in client.models.list():
        model_id = model.name or ""
        if model_id.startswith("models/"):
            model_id = model_id[len("models/"):]
        models.append({
            "id": model_id,
            "display_name": model.display_name or model_id,
            "supported_actions": list(model.supported_actions or []),
        })
    return models


# Text-generation model ids look like "gemini-<version>-<tier>[-<variant>]",
# e.g. gemini-2.5-pro, gemini-3.8-flash, gemini-3.1-pro-preview.  Tiers are
# tried in this order (so "flash-lite" wins over "flash"), which is also the
# display order.  Only the GA (no variant) and "preview" variants are offered;
# specialised variants (-image, -tts, -customtools, ...) are skipped.
_GEMINI_TIERS = ["pro", "flash-lite", "flash"]
_GEMINI_TIER_ORDER = ["pro", "flash", "flash-lite"]
_GEMINI_VARIANTS = {"": 0, "preview": 1}  # lower is preferred

# A general text model supports all of these; image, TTS, audio, live,
# embedding and similar models lack at least one.
_GEMINI_REQUIRED_ACTIONS = {"generateContent", "createCachedContent"}

_GEMINI_ID_RE = re.compile(r"^gemini-(?P<version>\d+(?:\.\d+)*)-(?P<rest>.+)$")


def _parse_gemini_id(model_id):
    """Returns (version_tuple, tier, variant) for a Gemini text model id, or
    None if the id is not of the form gemini-<version>-<tier>[-<variant>]."""
    m = _GEMINI_ID_RE.match(model_id)
    if not m:
        return None
    version = tuple(int(x) for x in m.group("version").split("."))
    rest = m.group("rest")
    for tier in _GEMINI_TIERS:
        if rest == tier:
            return version, tier, ""
        if rest.startswith(tier + "-"):
            return version, tier, rest[len(tier) + 1:]
    return None


def select_gemini_providers(models):
    """Builds the provider entries for the Gemini text tiers found in `models`
    (a list of dicts as returned by list_gemini_models).  For each tier,
    returns the highest-version model and, when there is one, the model of
    the previous version; at equal version a GA model beats a preview.
    Entries have the shape used by AI_PROVIDER_REGISTRY:
    {id, name, major, key_setting, model}."""
    candidates = []  # (tier, version, variant_rank, model)
    for model in models:
        if not _GEMINI_REQUIRED_ACTIONS <= set(model.get("supported_actions") or []):
            continue
        info = _parse_gemini_id(model["id"])
        if not info:
            continue
        version, tier, variant = info
        if variant not in _GEMINI_VARIANTS:
            continue
        candidates.append((tier, version, _GEMINI_VARIANTS[variant], model))

    providers = []
    for tier in _GEMINI_TIER_ORDER:
        # Highest version first; within a version, preferred variant first.
        ranked = sorted(
            (c for c in candidates if c[0] == tier),
            key=lambda c: (c[1], -c[2]), reverse=True)
        picks = []
        for _, version, _, model in ranked:
            if not picks:
                picks.append((version, model))
            elif len(picks) == 1 and version != picks[0][0]:
                picks.append((version, model))
        for i, (_, model) in enumerate(picks):
            providers.append({
                "id": f"gemini:{tier}" + ("-prev" if i else ""),
                "name": model["display_name"],
                "major": "gemini",
                "key_setting": "gemini_api_key",
                "model": model["id"],
            })
    return providers


GEMINI_GENERATE_MODEL = "gemini-2.5-flash"
GEMINI_VALIDATE_MODEL = "gemini-2.5-flash"


def gemini_generate_code(
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
    # 1. Initialize the Gemini client
    client = genai.Client(api_key=api_key)
    model = model or GEMINI_GENERATE_MODEL

    system_instructions = SYSTEM_INSTRUCTIONS
    if ask_questions:
        system_instructions += CLARIFY_INSTRUCTIONS

    # 2. Create the prompt
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

    if debug:
        log_ai_request_size("gemini generate_code", system_instructions, prompt,
                            preceding=preceding_code, instructions=instructions,
                            previous=previous_code, file_context=file_context,
                            error_context=error_context, variable_context=variable_context,
                            validation_context=validation_context)
    if dump_ai_requests:
        dump_ai_request(dump_ai_requests, "gemini generate_code", {
            "model": model,
            "contents": prompt,
            "system_instruction": system_instructions,
        })

    # 3. Generate content
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instructions
        )
    )
    if response.usage_metadata:
        add_tokens(response.usage_metadata.prompt_token_count, response.usage_metadata.candidates_token_count)
    if debug:
        print("Response:", response.text)
    # 4. Process the response
    if ask_questions:
        return parse_generate_response(response.text)
    return strip_markdown_code_fences(response.text), None


def gemini_amend_explanation(
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
    client = genai.Client(api_key=api_key)
    model = model or GEMINI_GENERATE_MODEL

    prompt = build_amend_explanation_prompt(
        explanation, error_context, previous_code, new_code)

    if debug:
        log_ai_request_size("gemini amend_explanation", AMEND_EXPLANATION_INSTRUCTIONS, prompt)
    if dump_ai_requests:
        dump_ai_request(dump_ai_requests, "gemini amend_explanation", {
            "model": model,
            "contents": prompt,
            "system_instruction": AMEND_EXPLANATION_INSTRUCTIONS,
            "max_output_tokens": 1024,
        })

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=AMEND_EXPLANATION_INSTRUCTIONS,
            max_output_tokens=1024,
        ),
    )
    if response.usage_metadata:
        add_tokens(response.usage_metadata.prompt_token_count, response.usage_metadata.candidates_token_count)
    if debug:
        print("Response to explanation amendment:", response.text)
    return (response.text or "").strip()


def gemini_generate_test_code(
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
    client = genai.Client(api_key=api_key)
    model = model or GEMINI_GENERATE_MODEL

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

    if debug:
        log_ai_request_size("gemini generate_test_code", TEST_SYSTEM_INSTRUCTIONS, prompt,
                            preceding=preceding_code, instructions=instructions,
                            previous=previous_code, file_context=file_context,
                            error_context=error_context, variable_context=variable_context,
                            validation_context=validation_context)
    if dump_ai_requests:
        dump_ai_request(dump_ai_requests, "gemini generate_test_code", {
            "model": model,
            "contents": prompt,
            "system_instruction": TEST_SYSTEM_INSTRUCTIONS,
        })

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=TEST_SYSTEM_INSTRUCTIONS
        )
    )
    if response.usage_metadata:
        add_tokens(response.usage_metadata.prompt_token_count, response.usage_metadata.candidates_token_count)
    if debug:
        print("Response:", response.text)
    code = strip_markdown_code_fences(response.text)
    return code


def gemini_generate_unit_test_code(
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
    client = genai.Client(api_key=api_key)
    model = model or GEMINI_GENERATE_MODEL

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

    if debug:
        log_ai_request_size("gemini generate_unit_test", UNIT_TEST_SYSTEM_INSTRUCTIONS, prompt,
                            preceding=preceding_code, instructions=instructions,
                            previous=previous_code, file_context=file_context,
                            error_context=error_context, variable_context=variable_context,
                            validation_context=validation_context)
    if dump_ai_requests:
        dump_ai_request(dump_ai_requests, "gemini generate_unit_test", {
            "model": model,
            "contents": prompt,
            "system_instruction": UNIT_TEST_SYSTEM_INSTRUCTIONS,
        })

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=UNIT_TEST_SYSTEM_INSTRUCTIONS
        )
    )
    if response.usage_metadata:
        add_tokens(response.usage_metadata.prompt_token_count, response.usage_metadata.candidates_token_count)
    if debug:
        print("Response:", response.text)
    code = strip_markdown_code_fences(response.text)
    return code


def gemini_validate_code(api_key, previous_code, code_to_validate, instructions, variable_context=None, model=None, debug=False, dump_ai_requests=False):
    client = genai.Client(api_key=api_key)
    model = model or GEMINI_VALIDATE_MODEL

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

    if debug:
        log_ai_request_size("gemini validate_code", CHECKING_INSTRUCTIONS, prompt,
                            preceding=previous_code, instructions=instructions,
                            variable_context=variable_context)
    if dump_ai_requests:
        dump_ai_request(dump_ai_requests, "gemini validate_code", {
            "model": model,
            "contents": prompt,
            "system_instruction": CHECKING_INSTRUCTIONS,
        })

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=CHECKING_INSTRUCTIONS
        )
    )
    if response.usage_metadata:
        add_tokens(response.usage_metadata.prompt_token_count, response.usage_metadata.candidates_token_count)
    if debug:
        print("Response:", response.text)
    return parse_validation_response(response.text)


def gemini_explain_code(api_key, previous_code, code_to_explain, instructions, variable_context=None, level=DEFAULT_EXPLANATION_DETAIL_LEVEL, use_bullets=DEFAULT_EXPLANATION_USE_BULLETS, use_latex=DEFAULT_EXPLANATION_USE_LATEX, model=None, debug=False, dump_ai_requests=False):
    client = genai.Client(api_key=api_key)
    model = model or GEMINI_VALIDATE_MODEL

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

    if debug:
        log_ai_request_size("gemini explain_code", EXPLAIN_INSTRUCTIONS, prompt,
                            preceding=previous_code, instructions=instructions,
                            variable_context=variable_context)
    if dump_ai_requests:
        dump_ai_request(dump_ai_requests, "gemini explain_code", {
            "model": model,
            "contents": prompt,
            "system_instruction": EXPLAIN_INSTRUCTIONS,
        })

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=EXPLAIN_INSTRUCTIONS
        )
    )
    if response.usage_metadata:
        add_tokens(response.usage_metadata.prompt_token_count, response.usage_metadata.candidates_token_count)
    if debug:
        print("Response:", response.text)
    return response.text


def _gemini_verify(api_key, system_instructions, payload, label, model=None,
                   debug=False, dump_ai_requests=False):
    client = genai.Client(api_key=api_key)
    model = model or GEMINI_VALIDATE_MODEL
    if debug:
        log_ai_request_size(f"gemini {label}", system_instructions, payload)
    if dump_ai_requests:
        dump_ai_request(dump_ai_requests, f"gemini {label}", {
            "model": model,
            "contents": payload,
            "system_instruction": system_instructions,
        })
    response = client.models.generate_content(
        model=model,
        contents=payload,
        config=types.GenerateContentConfig(
            system_instruction=system_instructions
        )
    )
    if response.usage_metadata:
        add_tokens(response.usage_metadata.prompt_token_count, response.usage_metadata.candidates_token_count)
    if debug:
        print("Response:", response.text)
    return parse_verify_response(response.text)


def gemini_verify_notebook(api_key, payload, model=None, debug=False, dump_ai_requests=False):
    return _gemini_verify(api_key, NOTEBOOK_VERIFY_INSTRUCTIONS, payload,
                          "verify_notebook", model=model, debug=debug,
                          dump_ai_requests=dump_ai_requests)


def gemini_verify_tests(api_key, payload, model=None, debug=False, dump_ai_requests=False):
    return _gemini_verify(api_key, TEST_VERIFY_INSTRUCTIONS, payload,
                          "verify_tests", model=model, debug=debug,
                          dump_ai_requests=dump_ai_requests)


def gemini_fold_additions(api_key, explanation=None, additions=None, model=None,
                          debug=False, dump_ai_requests=False):
    """Rewrites `explanation` to absorb `additions`. Returns the rewritten text."""
    client = genai.Client(api_key=api_key)
    model = model or GEMINI_GENERATE_MODEL

    system_instructions = FOLD_SYSTEM_INSTRUCTIONS

    prompt = build_fold_prompt(explanation or '', additions or [])
    if debug:
        log_ai_request_size("gemini fold_additions", system_instructions, prompt,
                            instructions=explanation)
    if dump_ai_requests:
        dump_ai_request(dump_ai_requests, "gemini fold_additions", {
            "model": model,
            "contents": prompt,
            "system_instruction": system_instructions,
            "max_output_tokens": 2048,
        })
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instructions,
            max_output_tokens=2048,
        ),
    )
    if response.usage_metadata:
        add_tokens(response.usage_metadata.prompt_token_count, response.usage_metadata.candidates_token_count)
    if debug:
        print("Response to fold_additions:", response.text)
    return (response.text or '').strip()


def gemini_generate_cell_name(api_key, explanation, model=None, debug=False, dump_ai_requests=False):
    client = genai.Client(api_key=api_key)
    model = model or GEMINI_GENERATE_MODEL
    prompt = build_name_prompt(explanation)
    if debug:
        log_ai_request_size("gemini generate_name", NAME_GENERATION_INSTRUCTIONS, prompt)
    if dump_ai_requests:
        dump_ai_request(dump_ai_requests, "gemini generate_name", {
            "model": model,
            "contents": prompt,
            "system_instruction": NAME_GENERATION_INSTRUCTIONS,
            "max_output_tokens": 50,
        })
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=NAME_GENERATION_INSTRUCTIONS,
            max_output_tokens=50,
        ),
    )
    if response.usage_metadata:
        add_tokens(response.usage_metadata.prompt_token_count, response.usage_metadata.candidates_token_count)
    if debug:
        print("Response to name generation:", response.text)
    return response.text
