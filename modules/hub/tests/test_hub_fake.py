import types

from hub import fake


def test_fake_mode_swaps_a_provider_only_when_it_is_on(monkeypatch) -> None:
    real = types.ModuleType("weather")
    double = types.ModuleType("weather_fake")
    monkeypatch.setitem(fake.FAKES, "weather", double)

    monkeypatch.delenv(fake.MODE, raising=False)
    assert fake.provider("weather", real) is real

    monkeypatch.setenv(fake.MODE, "fake")
    assert fake.provider("weather", real) is double
    assert fake.provider("books", real) is real
