from __future__ import annotations

from pathlib import Path

from money import publisher, worker


def test_the_publisher_module_is_an_entry_point_that_runs_the_worker(monkeypatch):
    calls = []
    monkeypatch.setattr(worker, "main", lambda: calls.append("worker"))
    assert publisher.main() == 0
    assert calls == ["worker"]


def test_the_publisher_module_runs_main_when_executed():
    source = Path(publisher.__file__).read_text(encoding="utf-8")
    assert 'if __name__ == "__main__":\n    raise SystemExit(main())' in source
