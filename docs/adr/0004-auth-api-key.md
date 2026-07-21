# ADR-0004: Static API-key auth; no JWT/OAuth2

**Status:** Accepted · July 2026

## Decision
`X-API-Key` header checked with constant-time comparison against
`PLATFORM_API_KEY` (auth disabled when unset, for local dev). `/health`
remains open for probes.

## Why not JWT / OAuth2
Both exist to manage **user identity**: sessions, scopes, token refresh,
federation. This API has exactly one caller — its operator. Encoding "one
static caller" into OAuth2 flows is security theater that adds an attack
surface (token handling bugs) without adding a control.

## Adopt triggers
- A second distinct user or tenant → per-key issuance, then JWT
- Third-party integrations needing delegated scopes → OAuth2
