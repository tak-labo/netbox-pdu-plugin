# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Lint
make lint                  # ruff check only
make ci                    # lint + Docker integration tests (mirrors CI)

# Integration tests (requires netbox-docker running at ../netbox-docker)
docker compose -f ../netbox-docker/docker-compose.yml \
  -f ../netbox-docker/docker-compose.override.yml \
  exec netbox python manage.py test netbox_pdu_plugin.tests -v 2

# Run a single test class
docker compose ... exec netbox python manage.py test netbox_pdu_plugin.tests.test_models.ManagedPDUModelTest -v 2

# Unit tests only (no NetBox/DB required)
uvx pytest netbox_pdu_plugin/tests/test_backends_raritan.py
uvx pytest netbox_pdu_plugin/tests/test_backends_unifi.py

# After code changes
docker compose ... exec netbox python manage.py migrate
docker compose ... restart netbox netbox-worker

# Generate migrations (model changes)
docker compose ... exec -e DEVELOPER=True netbox python manage.py makemigrations netbox_pdu_plugin
```

## Architecture

This is a NetBox plugin. NetBox is a Django application — all NetBox base classes, generics, and utilities must be used (not raw Django equivalents).

### Models (`models.py`)

Four models, all inheriting from `NetBoxModel` (except `PDUNetworkInterface` which uses plain `models.Model`):

- **`ManagedPDU`** — 1:1 with NetBox `Device`. Stores API credentials and sync metadata. The central object.
- **`PDUOutlet`** — Per-outlet power readings and status. FK to `ManagedPDU`, optional FK to `Device` (connected device).
- **`PDUInlet`** — Per-inlet power readings (whole-PDU metrics). FK to `ManagedPDU`.
- **`PDUNetworkInterface`** — NIC info for a PDU. Replaced entirely on each sync.

### Vendor Backend System (`backends/`)

The key abstraction. `BasePDUClient` defines the interface; each vendor implements it:

```
backends/
  base.py       # BasePDUClient (ABC) + PDUClientError
  raritan.py    # RaritanPDUClient — JSON-RPC 2.0 over HTTPS
  unifi.py      # UniFiPDUClient  — REST API with session or API key auth
  __init__.py   # get_pdu_client(managed_pdu) — factory function
```

`get_pdu_client()` selects the backend by `managed_pdu.vendor` key. Views and sync logic call only `BasePDUClient` methods — no vendor-specific code outside `backends/`.

To add a vendor: implement `BasePDUClient` → register in `_VENDOR_BACKENDS` → add to `VendorChoices` → migrate.

### Views (`views.py`)

Uses NetBox generics (`netbox.views.generic`) and `@register_model_view`. Key non-CRUD views:

- `ManagedPDUSyncView` — calls `get_pdu_client()`, updates all outlets/inlets/network interfaces, sets `sync_status`/`last_synced`
- `PDUOutletPowerView` — sends power commands (on/off/cycle); cycle enqueues `jobs.update_outlet_status` via `django_rq`
- `PDUOutletPushNameView`, `PDUInletPushNameView` — write names back to PDU; also update `PowerOutlet.label`/`PowerPort.label` on connected NetBox device

### Background Jobs (`jobs.py`)

Single function `update_outlet_status()` — run via RQ after power cycle to refresh outlet state from PDU. Enqueued with `django_rq.enqueue()` in views.

### REST API (`api/`)

Standard NetBox DRF pattern. **`api_password` is intentionally excluded from `ManagedPDUSerializer`** — do not add it.

### GraphQL (`graphql/`)

Strawberry/strawberry-django. Covers all three main models. `enums.py` mirrors `choices.py` for GraphQL consumers.

## Key Conventions

- **Comments and docstrings**: English only
- **Commit messages**: English, one line
- **Line length**: 120 characters (ruff)
- **`isinstance` calls**: use `X | Y` syntax, not `(X, Y)` tuple (UP038)
- **Exception re-raises**: always `raise ... from e` in except blocks (B904)
- **`api_password`** is stored as plaintext — never expose it in API responses or logs
- **`PDUNetworkInterface`** is replaced entirely (delete + recreate) on each sync, not updated in place
- **pre-push hook**: `uvx pre-commit install --hook-type pre-push` (runs lint + Docker tests before every push)
- **UniFi power cycle**: `UniFiPDUClient.set_outlet_power_state('cycle')` calls `time.sleep(3)` internally to wait for the PDU to complete the cycle before re-reading state. This blocks the web worker thread for 3 seconds — known limitation, do not remove the sleep.

## Testing

- **Integration tests** (`tests/test_models.py`, `test_api.py`, `test_views.py`, `test_graphql.py`): require running netbox-docker. Use `manage.py test`.
- **Unit tests** (`tests/test_backends_raritan.py`, `tests/test_backends_unifi.py`): mock HTTP, no DB needed. Use `uvx pytest`.
- View POST tests use superuser (`is_superuser=True`) to bypass NetBox `ObjectPermission` system.
- `testing/configuration.py` is the Django settings file used during CI and Docker test runs.
