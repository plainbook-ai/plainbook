"""Tests for building the AI provider registry from the model APIs' listings.
These exercise the pure selection functions with fixtures mirroring real API
output; no network access is needed."""
import random
from datetime import datetime, timezone

from plainbook.claude import select_claude_providers
from plainbook.gemini import select_gemini_providers


ENTRY_KEYS = {"id", "name", "major", "key_setting", "model"}


def _d(s):
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)


# (id, created_at) as returned by the Anthropic API in September 2026.
CLAUDE_MODELS = [
    ("claude-fable-5-1", _d("2026-08-28")),
    ("claude-opus-5", _d("2026-07-24")),
    ("claude-sonnet-5", _d("2026-06-29")),
    ("claude-fable-5", _d("2026-06-07")),
    ("claude-opus-4-8", _d("2026-05-28")),
    ("claude-opus-4-7", _d("2026-04-14")),
    ("claude-sonnet-4-6", _d("2026-02-17")),
    ("claude-opus-4-6", _d("2026-02-04")),
    ("claude-opus-4-5-20251101", _d("2025-11-24")),
    ("claude-haiku-4-5-20251001", _d("2025-10-15")),
    ("claude-sonnet-4-5-20250929", _d("2025-09-29")),
]


def _by_id(providers):
    return {p["id"]: p for p in providers}


class TestClaude:
    def test_latest_and_previous_per_family(self):
        by_id = _by_id(select_claude_providers(CLAUDE_MODELS))
        assert by_id["claude:opus"]["model"] == "claude-opus-5"
        assert by_id["claude:opus-prev"]["model"] == "claude-opus-4-8"
        assert by_id["claude:sonnet"]["model"] == "claude-sonnet-5"
        assert by_id["claude:sonnet-prev"]["model"] == "claude-sonnet-4-6"
        assert by_id["claude:fable"]["model"] == "claude-fable-5-1"
        assert by_id["claude:fable-prev"]["model"] == "claude-fable-5"
        # Only one haiku exists, so there is no previous generation.
        assert by_id["claude:haiku"]["model"] == "claude-haiku-4-5-20251001"
        assert "claude:haiku-prev" not in by_id

    def test_names_and_shape(self):
        by_id = _by_id(select_claude_providers(CLAUDE_MODELS))
        assert by_id["claude:opus-prev"]["name"] == "Claude Opus 4.8"
        assert by_id["claude:haiku"]["name"] == "Claude Haiku 4.5"
        assert by_id["claude:fable"]["name"] == "Claude Fable 5.1"
        for p in by_id.values():
            assert set(p) == ENTRY_KEYS
            assert p["major"] == "claude"
            assert p["key_setting"] == "claude_api_key"

    def test_order_is_by_family_then_latest_first(self):
        ids = [p["id"] for p in select_claude_providers(CLAUDE_MODELS)]
        assert ids == [
            "claude:fable", "claude:fable-prev",
            "claude:opus", "claude:opus-prev",
            "claude:sonnet", "claude:sonnet-prev",
            "claude:haiku",
        ]

    def test_independent_of_api_order(self):
        expected = select_claude_providers(CLAUDE_MODELS)
        shuffled = list(CLAUDE_MODELS)
        random.Random(0).shuffle(shuffled)
        assert select_claude_providers(shuffled) == expected

    def test_legacy_id_layout_and_unknown_family(self):
        models = [
            ("claude-3-5-sonnet-20241022", _d("2024-10-22")),
            ("claude-3-opus-20240229", _d("2024-02-29")),
            ("claude-zephyr-6", _d("2027-01-01")),
            ("not-a-claude-model", _d("2027-01-02")),
        ]
        by_id = _by_id(select_claude_providers(models))
        assert by_id["claude:sonnet"]["model"] == "claude-3-5-sonnet-20241022"
        assert by_id["claude:sonnet"]["name"] == "Claude Sonnet 3.5"
        assert by_id["claude:opus"]["model"] == "claude-3-opus-20240229"
        # Unknown families are offered too, after the known ones.
        assert by_id["claude:zephyr"]["model"] == "claude-zephyr-6"
        assert [p["id"] for p in select_claude_providers(models)][-1] == "claude:zephyr"
        assert len(by_id) == 3

    def test_same_version_snapshots_collapse(self):
        # Two snapshots of the same version are one generation; the previous
        # generation is the next distinct version.
        models = [
            ("claude-opus-5-20260801", _d("2026-08-01")),
            ("claude-opus-5-20260701", _d("2026-07-01")),
            ("claude-opus-4-8", _d("2026-05-28")),
        ]
        by_id = _by_id(select_claude_providers(models))
        assert by_id["claude:opus"]["model"] == "claude-opus-5-20260801"
        assert by_id["claude:opus-prev"]["model"] == "claude-opus-4-8"


TEXT = ["generateContent", "countTokens", "createCachedContent", "batchGenerateContent"]
IMAGE = ["generateContent", "countTokens", "batchGenerateContent"]
TTS = ["countTokens", "generateContent"]
EMBED = ["embedContent", "countTextTokens", "countTokens"]


def _g(model_id, display_name, actions=TEXT):
    return {"id": model_id, "display_name": display_name, "supported_actions": actions}


# Mirrors the Gemini API listing in September 2026 (subset).
GEMINI_MODELS = [
    _g("gemini-2.5-flash", "Gemini 2.5 Flash"),
    _g("gemini-2.5-pro", "Gemini 2.5 Pro"),
    _g("gemini-2.5-flash-preview-tts", "Gemini 2.5 Flash Preview TTS", TTS),
    _g("gemma-4-31b-it", "Gemma 4 31B IT", ["generateContent", "countTokens"]),
    _g("gemini-flash-latest", "Gemini Flash Latest"),
    _g("gemini-pro-latest", "Gemini Pro Latest"),
    _g("gemini-2.5-flash-lite", "Gemini 2.5 Flash-Lite"),
    _g("gemini-2.5-flash-image", "Nano Banana", IMAGE),
    _g("gemini-3-flash-preview", "Gemini 3 Flash Preview"),
    _g("gemini-3.1-pro-preview", "Gemini 3.1 Pro Preview"),
    _g("gemini-3.1-pro-preview-customtools", "Gemini 3.1 Pro Preview Custom Tools"),
    _g("gemini-3.1-flash-lite-preview", "Gemini 3.1 Flash Lite Preview"),
    _g("gemini-3.1-flash-lite", "Gemini 3.1 Flash Lite"),
    _g("gemini-3-pro-image-preview", "Nano Banana Pro", IMAGE),
    _g("gemini-3-pro-image", "Nano Banana Pro", IMAGE),
    _g("gemini-3.5-flash", "Gemini 3.5 Flash"),
    _g("gemini-3.5-flash-lite", "Gemini 3.5 Flash Lite"),
    _g("gemini-omni-flash-preview", "Gemini Omni Flash Preview", ["generateContent", "countTokens"]),
    _g("gemini-3.6-flash", "Gemini 3.6 Flash"),
    _g("gemini-3.7-flash", "Gemini 3.7 Flash"),
    _g("gemini-3.8-flash", "Gemini 3.8 Flash"),
    _g("gemini-robotics-er-2-preview", "Gemini Robotics-ER 2 Preview"),
    _g("gemini-embedding-2", "Gemini Embedding 2", EMBED),
]


class TestGemini:
    def test_latest_and_previous_per_tier(self):
        by_id = _by_id(select_gemini_providers(GEMINI_MODELS))
        assert by_id["gemini:pro"]["model"] == "gemini-3.1-pro-preview"
        assert by_id["gemini:pro-prev"]["model"] == "gemini-2.5-pro"
        assert by_id["gemini:flash"]["model"] == "gemini-3.8-flash"
        assert by_id["gemini:flash-prev"]["model"] == "gemini-3.7-flash"
        assert by_id["gemini:flash-lite"]["model"] == "gemini-3.5-flash-lite"
        assert by_id["gemini:flash-lite-prev"]["model"] == "gemini-3.1-flash-lite"
        assert len(by_id) == 6

    def test_names_from_display_name_and_shape(self):
        by_id = _by_id(select_gemini_providers(GEMINI_MODELS))
        assert by_id["gemini:pro"]["name"] == "Gemini 3.1 Pro Preview"
        assert by_id["gemini:flash"]["name"] == "Gemini 3.8 Flash"
        for p in by_id.values():
            assert set(p) == ENTRY_KEYS
            assert p["major"] == "gemini"
            assert p["key_setting"] == "gemini_api_key"

    def test_order(self):
        ids = [p["id"] for p in select_gemini_providers(GEMINI_MODELS)]
        assert ids == [
            "gemini:pro", "gemini:pro-prev",
            "gemini:flash", "gemini:flash-prev",
            "gemini:flash-lite", "gemini:flash-lite-prev",
        ]

    def test_non_text_and_special_variants_never_selected(self):
        selected = {p["model"] for p in select_gemini_providers(GEMINI_MODELS)}
        for bad in ["gemini-3-pro-image", "gemini-3-pro-image-preview",
                    "gemini-2.5-flash-preview-tts", "gemini-3.1-pro-preview-customtools",
                    "gemini-embedding-2", "gemini-omni-flash-preview",
                    "gemini-flash-latest", "gemini-pro-latest", "gemma-4-31b-it"]:
            assert bad not in selected

    def test_ga_preferred_over_preview_at_same_version(self):
        models = [
            _g("gemini-3.1-flash-lite-preview", "Gemini 3.1 Flash Lite Preview"),
            _g("gemini-3.1-flash-lite", "Gemini 3.1 Flash Lite"),
            _g("gemini-3-flash-preview", "Gemini 3 Flash Preview"),
        ]
        by_id = _by_id(select_gemini_providers(models))
        assert by_id["gemini:flash-lite"]["model"] == "gemini-3.1-flash-lite"
        assert "gemini:flash-lite-prev" not in by_id
        # A lone preview is still offered.
        assert by_id["gemini:flash"]["model"] == "gemini-3-flash-preview"
        assert "gemini:flash-prev" not in by_id

    def test_version_ordering(self):
        # 3 < 3.1 < 3.10, and "3" is a distinct generation from "3.1".
        models = [
            _g("gemini-3-flash", "3"),
            _g("gemini-3.10-flash", "3.10"),
            _g("gemini-3.1-flash", "3.1"),
        ]
        by_id = _by_id(select_gemini_providers(models))
        assert by_id["gemini:flash"]["model"] == "gemini-3.10-flash"
        assert by_id["gemini:flash-prev"]["model"] == "gemini-3.1-flash"

    def test_empty_listing(self):
        assert select_gemini_providers([]) == []
        assert select_claude_providers([]) == []
