# Joseph's backend and AI assignments

## 1. Finish the live authentication integration (first priority)

Files: `scripts/smoke_local.py`, `infra/keycloak/realm.json`, `compose.yaml`, Android `auth/AuthManager.kt`.

The implemented design is browser authorization code + PKCE, encrypted Android token storage/refresh, and FastAPI RS256/JWKS validation. Unit tests pass, but the local Keycloak login POST in the smoke script returns 400.

Trace discovery, authorization, cookie creation, login submission and callback separately. Compare the advertised emulator host `10.0.2.2` with the smoke script's `localhost` transport. Inspect the visible error and cookie domain/path/Secure rules without logging credentials, codes or tokens. Check the form's required hidden inputs. Avoid solving this by disabling issuer, audience, state, nonce or PKCE checks.

Done when: the smoke script passes, Android browser login/registration completes, a restart restores the encrypted session, refresh works, logout removes local credentials, and a second account sees none of the first account's data. Device sign-out currently leaves the browser's SSO session intact and cached observations remain account-scoped.

## 2. Daily feature storage (JOSEPH-B1)

Location: `src/vitalstream/main.py`, insight endpoint. Introduce a migration and a table keyed by owner/source/day/feature version. Recompute affected days after uploads, corrections and deletion; preserve source observations. Move expensive aggregation out of request handling when volume justifies it.

Acceptance: correcting yesterday changes today's insight, retries do not double-count, missing days remain missing, users stay isolated, and updates invalidate old results. Add PostgreSQL integration tests before switching the endpoint.

## 3. Train and evaluate a model (JOSEPH-M3)

Location: `src/vitalstream/analytics.py`. Keep the existing statistical method as your benchmark. Select a dataset whose measurements and outcome labels match the intended feature; document access/license, sampling rate and limitations. Define chronological/person-held-out splits before fitting transforms. Compare false alerts and detection performance against the benchmark. Use the same versioned output interface.

Acceptance: reproducible evaluation, no future-data leakage, source/method differences handled explicitly, documented failure cases. Synthetic fixtures test implementation; they cannot validate illness or flare prediction claims.

## Before real-data release

Configure a real HTTPS issuer/API, production settings and public privacy documentation; add deletion/account-management UX, rate limits and operational monitoring. Keycloak `start-dev`, HTTP emulator addresses and self-registration settings are local conveniences. Broad vendor integrations, circadian/flare features and provider access are not implemented in this draft.

## Stop the review stack

The implementation session started containers under project `vitalstream-review`. Run `docker compose -p vitalstream-review stop` from this repository to stop them without deleting data.
