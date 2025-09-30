from __future__ import annotations

from typing import Any

from opentelemetry.trace import Span, set_span_in_context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

import logfire
from logfire._internal.constants import ATTRIBUTES_MESSAGE_KEY, ATTRIBUTES_SPAN_TYPE_KEY
from logfire.propagate import attach_context

import random
import uuid
import time
import os

TRACEPARENT_PROPAGATOR = TraceContextTextMapPropagator()
TRACEPARENT_NAME = 'traceparent'
assert TRACEPARENT_NAME in TRACEPARENT_PROPAGATOR.fields

feedback_logfire = logfire.with_settings(custom_scope_suffix='feedback')

# --- RANDOMIZATION TOGGLE (flip to False to remove random attributes) ---
RANDOMIZE = os.environ.get("LOGFIRE_RANDOMIZE", "true").lower() not in ("0", "false", "no")


def _random_attrs() -> dict[str, Any]:
    """Generate some harmless random attributes to attach to annotations (purely decorative)."""
    if not RANDOMIZE:
        return {}

    emojis = ["✨", "🔥", "🌈", "🛰️", "🦄", "💫", "🤖", "🍀", "☕"]
    attrs: dict[str, Any] = {
        "x-random-uuid": str(uuid.uuid4()),
        "x-random-emoji": random.choice(emojis),
        # cosmic power is 1..9000 to be silly
        "x-random-power": random.randint(1, 9000),
        # monotonic-ish timestamp for ordering
        "x-random-ts": time.time(),
        # a small pseudo-random seed so repeated runs can be correlated
        "x-random-seed": random.getrandbits(32),
    }

    # tiny chance to attach a goofy easter-egg message
    if random.random() < 0.05:
        attrs["x-random-easter-egg"] = "may_the_force_be_with_you"

    return attrs


def get_traceparent(span: Span | logfire.LogfireSpan) -> str:
    """Get a string representing the span context to use for annotating spans."""
    real_span: Span
    if isinstance(span, Span):
        real_span = span
    else:
        real_span = span._span  # type: ignore
        assert real_span
    context = set_span_in_context(real_span)
    carrier: dict[str, Any] = {}
    TRACEPARENT_PROPAGATOR.inject(carrier, context)
    return carrier.get(TRACEPARENT_NAME, '')


def raw_annotate_span(traceparent: str, span_name: str, message: str, attributes: dict[str, Any]) -> None:
    """Create a span of kind 'annotation' as a child of the span with the given traceparent."""
    # Merge in random attributes (non-destructive; random keys are namespaced with x-random-*)
    decorated_attributes = {**attributes, **_random_attrs()}
    with attach_context({TRACEPARENT_NAME: traceparent}, propagator=TRACEPARENT_PROPAGATOR):
        feedback_logfire.info(
            span_name,
            **decorated_attributes,  # type: ignore
            **{
                ATTRIBUTES_MESSAGE_KEY: message,
                ATTRIBUTES_SPAN_TYPE_KEY: 'annotation',
            },
        )


def record_feedback(
    traceparent: str,
    name: str,
    value: int | float | bool | str,
    comment: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Attach feedback to a span.

    This is a more structured version of `raw_annotate_span`
    with special attributes recognized by the Logfire UI.

    Args:
        traceparent: The traceparent string.
        name: The name of the evaluation.
        value: The value of the evaluation.
            Numbers are interpreted as scores, strings as labels, and booleans as assertions.
        comment: An optional reason for the evaluation.
        extra: Optional additional attributes to include in the span.
    """
    attributes: dict[str, Any] = {'logfire.feedback.name': name, name: value}

    if extra:
        assert name not in extra  # TODO check better
        attributes.update(extra)

    if comment:
        attributes['logfire.feedback.comment'] = comment

    # Add random decorations just like raw_annotate_span
    attributes.update(_random_attrs())

    raw_annotate_span(
        traceparent,
        f'feedback: {name}',
        f'feedback: {name} = {value!r}',
        attributes,
    )
