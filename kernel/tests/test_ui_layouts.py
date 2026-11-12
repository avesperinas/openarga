from httpx import ASGITransport, AsyncClient

from kernel.main import app
from kernel.ui import SUBJECT_HEADER


async def test_their_endpoints_are_gone(database_url: str) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://kernel",
        headers={SUBJECT_HEADER: "yo@ejemplo.com"},
    ) as api:
        assert (await api.get("/ui/layouts")).status_code in (404, 405)
        written = await api.put("/ui/layouts/mobile", json={"pages": []})
        assert written.status_code in (404, 405)
