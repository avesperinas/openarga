from __future__ import annotations

from hub.declare import Provider

SOURCES = (
    Provider(
        id="apple_health",
        name="Apple Health",
        category="health",
        description="Your steps, heart, activity and sleep of each day, sent by "
        "an iPhone shortcut, and your profile. Connecting shows a "
        "token only once: paste it in the shortcut as Vitals explains"
        " in its settings.",
        capabilities=("push",),
        emits=("health.steps", "health.daily", "health.profile"),
        available=True,
        single=True,
        by_hand=False,
        internal=("ingest_token",),
    ),
)
