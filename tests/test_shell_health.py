from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_the_shell_health_check_uses_a_route_that_needs_no_session():
    dockerfile = (ROOT / "shell/Dockerfile").read_text(encoding="utf-8")
    assert "http://127.0.0.1:3000/healthz" in dockerfile
    assert (ROOT / "shell/app/healthz/route.ts").is_file()
