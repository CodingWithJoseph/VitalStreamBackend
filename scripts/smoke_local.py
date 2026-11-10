"""Exercise LOCAL Compose OIDC authorization-code/PKCE + API using temporary test users.

No user credentials or tokens are printed. Creates/deletes only its own local test identities.
"""

import base64
import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit, urlunsplit
from uuid import uuid4

import httpx
from dotenv import dotenv_values


class LoginForm(HTMLParser):
    action = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "form" and attributes.get("id") == "kc-form-login":
            self.action = attributes["action"]


def main():
    # JOSEPH-AUTH: this harness currently gets HTTP 400 on the Keycloak login POST.
    # Inspect the visible error and localhost/emulator cookie-host differences before
    # changing auth configuration. Do not log tokens or disable PKCE/issuer checks.
    config = dotenv_values(".env")
    identity = "http://localhost:8080"
    api = "http://localhost:8000"
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        response = client.post(
            identity + "/realms/master/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": "admin",
                "password": config["KEYCLOAK_ADMIN_PASSWORD"],
            },
        )
        response.raise_for_status()
        admin = {"Authorization": "Bearer " + response.json()["access_token"]}
        created = []

        def new_session():
            username, password = "smoke-" + uuid4().hex, secrets.token_urlsafe(32)
            response = client.post(
                identity + "/admin/realms/vitalstream/users",
                headers=admin,
                json={
                    "username": username,
                    "enabled": True,
                    "firstName": "Synthetic",
                    "lastName": "Test",
                    "email": username + "@example.invalid",
                    "emailVerified": True,
                    "credentials": [{"type": "password", "value": password, "temporary": False}],
                },
            )
            response.raise_for_status()
            user_id = response.headers["location"].rsplit("/", 1)[-1]
            created.append(user_id)
            verifier, state = secrets.token_urlsafe(48), secrets.token_urlsafe(24)
            challenge = (
                base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
                .decode()
                .rstrip("=")
            )
            redirect = "com.vitalstream.android:/oauth2redirect"
            with httpx.Client(timeout=20, follow_redirects=False) as browser:
                page = browser.get(
                    identity + "/realms/vitalstream/protocol/openid-connect/auth",
                    params={
                        "client_id": "vitalstream-android",
                        "redirect_uri": redirect,
                        "response_type": "code",
                        "scope": "openid profile",
                        "state": state,
                        "nonce": secrets.token_urlsafe(16),
                        "code_challenge": challenge,
                        "code_challenge_method": "S256",
                        "prompt": "login",
                    },
                )
                page.raise_for_status()
                form = LoginForm()
                form.feed(page.text)
                assert form.action, "Expected Keycloak login form"
                action = urlsplit(form.action)
                # The emulator uses 10.0.2.2. This host-side test reaches the same local service.
                action_url = urlunsplit(("http", "localhost:8080", action.path, action.query, ""))
                login = browser.post(action_url, data={"username": username, "password": password})
                if login.status_code not in (302, 303):
                    errors = [
                        re.sub(r"<[^>]+>", "", fragment)
                        for fragment in re.findall(
                            r"<(?:h1|p)[^>]*>(.*?)</(?:h1|p)>", login.text, re.S
                        )
                    ]
                    raise AssertionError(f"Login status {login.status_code}: {errors}")
                callback = parse_qs(urlsplit(login.headers["location"]).query)
                assert callback["state"] == [state]
                token = browser.post(
                    identity + "/realms/vitalstream/protocol/openid-connect/token",
                    data={
                        "grant_type": "authorization_code",
                        "client_id": "vitalstream-android",
                        "redirect_uri": redirect,
                        "code": callback["code"][0],
                        "code_verifier": verifier,
                    },
                )
                token.raise_for_status()
                return {"Authorization": "Bearer " + token.json()["access_token"]}

        try:
            alice, bob = new_session(), new_session()
            assert client.get(api + "/v1/me").status_code == 401
            assert client.get(api + "/v1/me", headers=alice).status_code == 200
            records = [
                dict(
                    id=str(uuid4()),
                    source="synthetic",
                    source_record_id=str(day),
                    revision=1,
                    value=72 if day == 1 else 60 + day % 4,
                    observed_at=(datetime.now(UTC) - timedelta(days=day)).isoformat(),
                    unit="bpm",
                    metric="resting_heart_rate",
                    synthetic=True,
                )
                for day in range(1, 15)
            ]
            first = client.post(
                api + "/v1/me/observations:batch", headers=alice, json={"records": records}
            )
            first.raise_for_status()
            assert {item["status"] for item in first.json()["results"]} == {"created"}
            retry = client.post(
                api + "/v1/me/observations:batch", headers=alice, json={"records": records}
            )
            assert {item["status"] for item in retry.json()["results"]} == {"unchanged"}
            assert len(client.get(api + "/v1/me/observations", headers=alice).json()["items"]) == 14
            assert client.get(api + "/v1/me/observations", headers=bob).json()["items"] == []
            result = client.get(api + "/v1/me/insights", headers=alice).json()
            assert result["status"] == "ready" and result["history_days"] == 13
            for record in records:
                assert (
                    client.delete(
                        api + "/v1/me/observations/" + record["id"], headers=alice
                    ).status_code
                    == 204
                )
            print(
                "PASS: OIDC PKCE, JWT audience/issuer, PostgreSQL persistence, "
                "retry deduplication, user isolation, insights and deletion"
            )
        finally:
            for user_id in created:
                client.delete(
                    identity + "/admin/realms/vitalstream/users/" + user_id, headers=admin
                ).raise_for_status()


if __name__ == "__main__":
    main()
