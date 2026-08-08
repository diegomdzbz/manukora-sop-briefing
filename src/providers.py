"""Model providers for the narrative layer.

The narrative layer asks for one thing: prose that satisfies a JSON schema. Both providers
here enforce that server-side — Anthropic through structured outputs, Google through
`responseSchema` — so the guarantee the architecture rests on is the same either way, and
neither can return a briefing missing a section.

Selection is by whichever key is present, Anthropic first. That is not a hedge: the
narrative layer is the one place in this project where the vendor is genuinely an
implementation detail, because everything that matters — the figures, the ranking, the
business rules — was decided before the call is made. Keeping it swappable costs about
forty lines and means the pipeline runs with whatever credential is on hand.

No SDK is required. Both are plain HTTPS calls over the standard library, so a reviewer can
clone this and run it without installing a client for a vendor they may not use. The
`anthropic` package is used when it is installed, and the raw endpoint when it is not.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

TIMEOUT_SECONDS = 180


class ProviderError(RuntimeError):
    """A provider could not produce a response. See RUNBOOK.md."""


class NoProviderConfigured(ProviderError):
    """Neither key is set."""


# --------------------------------------------------------------------------------------


def _post_json(url: str, payload: dict, headers: dict[str, str]) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:600]
        raise ProviderError(f"HTTP {exc.code} from {url.split('?')[0]}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ProviderError(f"Could not reach {url.split('?')[0]}: {exc.reason}") from exc


def _strip_unsupported(schema: dict) -> dict:
    """Convert the schema to the dialect Gemini accepts.

    Google's `responseSchema` is an OpenAPI subset and rejects `additionalProperties`,
    which the Anthropic schema uses to forbid extra fields. Dropping it loosens the
    contract slightly — Gemini could in principle return an unexpected key — so
    `check_against_facts()` in schema.py remains the backstop for both providers.
    """
    if not isinstance(schema, dict):
        return schema
    out = {k: v for k, v in schema.items() if k != "additionalProperties"}
    if "properties" in out:
        out["properties"] = {k: _strip_unsupported(v) for k, v in out["properties"].items()}
    if "items" in out:
        out["items"] = _strip_unsupported(out["items"])
    return out


# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Provider:
    """How the finished briefing records which model wrote it."""

    vendor: str
    model: str
    schema_enforcement: str

    @property
    def label(self) -> str:
        return f"{self.vendor} {self.model}"


class AnthropicProvider:
    """Claude, via structured outputs.

    The project default. `output_config.format` constrains the response to the schema at
    the API layer, so a malformed shape is retried by the model rather than parsed
    hopefully here.
    """

    info = Provider("Anthropic", "claude-opus-5", "structured outputs (output_config.format)")

    # The reasoning is already done — every figure was computed and tested before this
    # call. Medium is the right tier for writing it up, and is a deliberate cost decision.
    EFFORT = "medium"
    MAX_TOKENS = 16000

    def __init__(self, api_key: str) -> None:
        self._key = api_key

    def generate(self, system: str, user: str, schema: dict) -> dict:
        payload = {
            "model": self.info.model,
            "max_tokens": self.MAX_TOKENS,
            "system": system,
            "output_config": {
                "effort": self.EFFORT,
                "format": {"type": "json_schema", "schema": schema},
            },
            "messages": [{"role": "user", "content": user}],
        }
        data = _post_json(
            "https://api.anthropic.com/v1/messages",
            payload,
            {
                "x-api-key": self._key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )

        stop = data.get("stop_reason")
        if stop == "max_tokens":
            raise ProviderError(
                f"Response hit the {self.MAX_TOKENS} token ceiling and is incomplete. "
                "Raise MAX_TOKENS or lower EFFORT."
            )
        if stop == "refusal":
            raise ProviderError("The model declined this request. See RUNBOOK.md.")

        text = next(
            (b.get("text") for b in data.get("content", []) if b.get("type") == "text"), None
        )
        if not text:
            raise ProviderError("Anthropic returned no text block.")
        return json.loads(text)


class GeminiProvider:
    """Gemini, via `responseSchema`.

    Same guarantee as the Anthropic path — the schema is enforced by the API, not checked
    after the fact.
    """

    # gemini-2.5-flash returns 404 for accounts created after its deprecation — the error
    # is "no longer available to new users", which reads like a bad model name until you
    # read it twice. Pinned to a current model; `GET /v1beta/models` lists what a given
    # key can actually reach.
    info = Provider("Google", "gemini-3.6-flash", "responseSchema (generationConfig)")

    def __init__(self, api_key: str) -> None:
        self._key = api_key

    def generate(self, system: str, user: str, schema: dict) -> dict:
        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": _strip_unsupported(schema),
            },
        }
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.info.model}:generateContent?key={self._key}"
        )
        data = _post_json(url, payload, {"content-type": "application/json"})

        candidates = data.get("candidates") or []
        if not candidates:
            raise ProviderError(f"Gemini returned no candidates: {json.dumps(data)[:400]}")

        reason = candidates[0].get("finishReason")
        if reason and reason not in ("STOP", "MAX_TOKENS"):
            raise ProviderError(f"Gemini stopped early: {reason}. See RUNBOOK.md.")

        parts = candidates[0].get("content", {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts)
        if not text.strip():
            raise ProviderError("Gemini returned an empty response.")
        return json.loads(text)


# --------------------------------------------------------------------------------------


def select_provider() -> AnthropicProvider | GeminiProvider:
    """Pick a provider from whichever key is available, Anthropic first.

    Raises rather than falling back to a stub: a briefing that silently came from nowhere
    is the one failure mode this project exists to prevent.
    """
    if key := os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicProvider(key)
    if key := os.environ.get("GEMINI_API_KEY"):
        return GeminiProvider(key)
    raise NoProviderConfigured(
        "No model provider configured. Set ANTHROPIC_API_KEY or GEMINI_API_KEY "
        "(see .env.example), or use `--no-llm` to render the briefing without a model."
    )
