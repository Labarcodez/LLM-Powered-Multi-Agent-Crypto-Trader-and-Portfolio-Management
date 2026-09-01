"""Shared Anthropic API plumbing for all three agents.

Uses the current (2026) Claude API surface exactly as documented by the
`claude-api` skill's Python reference: a bare `anthropic.Anthropic()` client
(resolves ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN / an `ant auth login`
profile — never hardcode a key), `output_config.format` for guaranteed-valid
JSON (not the deprecated `output_format` param), and `cache_control` on the
frozen system prompt so the ~5k tokens of agent instructions are cached
across every tick instead of re-billed each time (RESEARCH.md §8.4 — up to
~90% cost reduction, material at 24/7 cadence).

This module makes NO network call itself unless `call_structured` is
invoked, and it requires a real ANTHROPIC_API_KEY in the environment to do
anything. It has not been exercised end-to-end in the sandbox this was
authored in (no key was available there, and the egress proxy blocks most
outbound hosts) — see RESEARCH.md §12 and examples/demo_run.md for how that
was worked around for this repo's own demonstration.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from crypto_desk.risk.circuit_breakers import CircuitBreaker


class AgentCallError(RuntimeError):
    """Raised when a call could not be completed after the SDK's own retries,
    or when the circuit breaker's consecutive-paid-call lockout trips
    (RESEARCH.md §8.3) — deliberately a different exception type from the
    underlying SDK errors, so callers can catch "this tick failed, handle it"
    without needing to know every anthropic.* exception class.
    """


@dataclass
class StructuredCallResult:
    raw_json: str
    parsed: dict[str, Any]
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int


def get_client():
    """Lazily import and construct the Anthropic client so the rest of this
    package can be imported (and its pure-logic parts unit-tested) even in
    an environment where the `anthropic` package isn't installed yet."""
    import anthropic
    return anthropic.Anthropic()


def call_structured(
    model: str,
    system_prompt: str,
    user_content: str,
    json_schema: dict[str, Any],
    max_tokens: int = 4096,
    circuit_breaker: CircuitBreaker | None = None,
    as_of: date | None = None,
    client=None,
    enable_thinking: bool = False,
) -> StructuredCallResult:
    """One structured-output call. Returns the validated-shape JSON as both
    the raw string and a parsed dict; raises AgentCallError on any failure
    mode this project cares about (auth, rate limit exhausted after SDK
    retries, refusal, or the circuit breaker's call-count lockout).

    The system prompt is cached (`cache_control: {"type": "ephemeral"}`) so
    repeated ticks with the same agent instructions pay full price only
    once per cache window.
    """
    import anthropic  # local import — see get_client() docstring

    if circuit_breaker is not None:
        breach = circuit_breaker.record_paid_call(as_of or date.today())
        if breach is not None:
            raise AgentCallError(breach.message)

    client = client or get_client()

    kwargs: dict[str, Any] = dict(
        model=model,
        max_tokens=max_tokens,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_content}],
        output_config={"format": {"type": "json_schema", "schema": json_schema}},
    )
    if enable_thinking:
        # The Chain-of-Thought capability config (RESEARCH.md §2.2), implemented
        # via the model's native extended thinking rather than a hand-rolled
        # <reasoning> XML tag: on current models this is the faithful
        # modernization of "make the agent deliberate before answering," and it
        # composes cleanly with output_config.format — thinking arrives as a
        # separate `thinking` content block, the guaranteed-valid-JSON `text`
        # block is unaffected and is still what gets parsed below.
        kwargs["thinking"] = {"type": "adaptive"}

    try:
        response = client.messages.create(**kwargs)
    except anthropic.AuthenticationError as e:
        raise AgentCallError(
            "Anthropic API authentication failed — set ANTHROPIC_API_KEY "
            "(or an `ant auth login` profile). See README.md."
        ) from e
    except anthropic.RateLimitError as e:
        raise AgentCallError(f"Rate limited after SDK retries: {e}") from e
    except anthropic.APIStatusError as e:
        raise AgentCallError(f"Anthropic API error ({e.status_code}): {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise AgentCallError(f"Network error calling Anthropic API: {e}") from e

    if response.stop_reason == "refusal":
        detail = getattr(response, "stop_details", None)
        category = getattr(detail, "category", None) if detail else None
        raise AgentCallError(f"Model declined to respond (category={category}).")

    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise AgentCallError("No text content block in response — cannot parse structured output.")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise AgentCallError(f"output_config.format did not yield valid JSON: {e}") from e

    if circuit_breaker is not None:
        circuit_breaker.reset_call_counter()

    usage = response.usage
    return StructuredCallResult(
        raw_json=text,
        parsed=parsed,
        model=response.model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
        cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
    )


REACT_STYLE_INSTRUCTIONS = """\
Interleave brief reasoning with your action: note what the data shows and \
weigh conflicting signals before committing to your structured output. \
This is compulsory background practice across every configuration \
(RESEARCH.md §2.3).

Chain-of-Thought capability config (RESEARCH.md §2.2): pass
`enable_thinking=True` to call_structured() rather than adding a manual
<reasoning> tag instruction here. On the current API, extended thinking
(`thinking: {"type": "adaptive"}`) is the faithful, native equivalent of the
paper's forced step-by-step block — it composes cleanly with
output_config.format's guaranteed-valid-JSON text output, which a
hand-rolled XML tag scheme does not need to work around on this model
generation."""
