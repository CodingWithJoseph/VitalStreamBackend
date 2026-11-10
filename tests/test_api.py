from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from vitalstream.config import Settings


def upload(client, *records):
    response = client.post("/v1/me/observations:batch", json={"records": list(records)})
    assert response.status_code == 200, response.text
    return [result["status"] for result in response.json()["results"]]


def test_retry_revisions_conflicts_and_pagination(client, record):
    assert upload(client, record) == ["created"]
    assert upload(client, record) == ["unchanged"]
    assert upload(client, record | {"value": 80}) == ["conflict"]
    assert upload(client, record | {"value": 80, "revision": 2}) == ["updated"]
    assert upload(client, record) == ["stale"]
    assert upload(client, record | {"id": str(uuid4())}) == ["conflict"]
    another = record | {"id": str(uuid4()), "source_record_id": "another"}
    assert upload(client, another) == ["created"]
    page = client.get("/v1/me/observations?limit=1").json()
    assert page["items"][0]["value"] == 80
    assert page["next_cursor"] is not None
    second = client.get(f"/v1/me/observations?cursor={page['next_cursor']}").json()
    assert len(second["items"]) == 1
    assert second["next_cursor"] is None


def test_deletion_is_terminal_and_isolated(client, record):
    upload(client, record)
    client.app.dependency_overrides[client.app.state.auth] = lambda: "bob"
    assert client.get("/v1/me/observations").json()["items"] == []
    assert client.delete(f"/v1/me/observations/{record['id']}").status_code == 404
    assert client.get("/v1/me/insights").json()["status"] == "insufficient_data"
    client.app.dependency_overrides[client.app.state.auth] = lambda: "alice"
    assert client.delete(f"/v1/me/observations/{record['id']}").status_code == 204
    assert upload(client, record | {"revision": 9}) == ["deleted"]
    assert client.get("/v1/me/observations").json()["items"] == []


@pytest.mark.parametrize(
    "change",
    [{"unit": "ms"}, {"value": -1}, {"owner": "bob"}, {"observed_at": "2026-01-01T12:00:00"}],
)
def test_invalid_batch_is_atomic(client, record, change):
    response = client.post("/v1/me/observations:batch", json={"records": [record, record | change]})
    assert response.status_code == 422
    assert client.get("/v1/me/observations").json()["items"] == []


def test_future_record_is_rejected(client, record):
    assert upload(
        client, record | {"observed_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()}
    ) == ["rejected"]


def test_authentication_is_not_optional(signed_client):
    client, token = signed_client
    assert client.get("/v1/me").status_code == 401
    assert client.get("/v1/me", headers=token()).status_code == 200
    for changes in (
        {"aud": "other"},
        {"iss": "https://attacker.example"},
        {"exp": datetime.now(UTC) - timedelta(seconds=1)},
        {"sub": ""},
    ):
        assert client.get("/v1/me", headers=token(**changes)).status_code == 401
    assert client.get("/v1/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401


def test_signed_users_are_isolated(signed_client, record):
    client, token = signed_client
    response = client.post("/v1/me/observations:batch", headers=token(), json={"records": [record]})
    assert response.status_code == 200
    assert client.get("/v1/me/observations", headers=token(sub="bob")).json()["items"] == []


def test_insight_uses_persisted_records_and_recomputes_after_delete(client, record):
    records = []
    for day in range(10):
        records.append(
            record
            | {
                "id": str(uuid4()),
                "source_record_id": str(day),
                "observed_at": (datetime.now(UTC) - timedelta(days=day + 1)).isoformat(),
                "value": 80 if day == 0 else 60,
            }
        )
    upload(client, *records)
    insight = client.get("/v1/me/insights").json()
    assert insight["status"] == "ready"
    assert insight["baseline"] == 60
    assert insight["deviation"] == 20
    client.delete(f"/v1/me/observations/{records[0]['id']}")
    assert client.get("/v1/me/insights").json()["deviation"] == 0


def test_production_fails_closed():
    with pytest.raises(ValueError):
        Settings(environment="production", _env_file=None)


def test_health_and_contract(client):
    assert client.get("/health/ready").status_code == 200
    assert "/v1/me/insights" in client.get("/openapi.json").json()["paths"]
