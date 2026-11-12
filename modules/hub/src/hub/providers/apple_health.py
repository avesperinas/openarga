from __future__ import annotations

from hub.declare import Provider

SOURCES = (
    Provider(
        id="apple_health",
        name="Apple Salud",
        category="health",
        description="Tus pasos, tu corazón, tu actividad y tu sueño de cada día, que manda un "
        "atajo del iPhone, y tu ficha. Al conectar sale un token que se enseña una sola vez: "
        "pégalo en el atajo como explica Vitals en sus ajustes.",
        capabilities=("push",),
        emits=("health.steps", "health.daily", "health.profile"),
        available=True,
        single=True,
        by_hand=False,
        internal=("ingest_token",),
    ),
)
