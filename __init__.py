"""Hermes Global Hot plugin registration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .metadata import GlobalHotMetadataStore
from .runtime import GlobalHotRuntime, SOURCE_SERVICE_KEY


def _path_setting(ctx: Any, key: str, fallback: Path) -> Path:
    value = str(ctx.get_config(key, default="") or "").strip()
    return Path(value).expanduser() if value else fallback


def _same_database(left: str | Path, right: str | Path) -> bool:
    left_path = Path(left).expanduser()
    right_path = Path(right).expanduser()
    try:
        if left_path.resolve(strict=False) == right_path.resolve(strict=False):
            return True
        return bool(
            left_path.exists()
            and right_path.exists()
            and left_path.samefile(right_path)
        )
    except (OSError, RuntimeError):
        return False


def _require_compatible_host(ctx: Any) -> None:
    for name in (
        "get_service",
        "register_middleware",
        "register_hook",
        "register_command",
        "on_unload",
    ):
        if not callable(getattr(ctx, name, None)):
            raise RuntimeError(f"Hermes Global Hot requires PluginContext.{name}()")

    try:
        from hermes_cli.middleware import (
            MIDDLEWARE_SCHEMA_VERSION,
            TRANSPORT_SCHEMA_VERSION,
        )
    except ImportError as exc:
        raise RuntimeError(
            "Hermes Global Hot requires hermes.middleware.v2 and "
            "hermes.transport.v3"
        ) from exc

    if MIDDLEWARE_SCHEMA_VERSION != "hermes.middleware.v2":
        raise RuntimeError(
            "Hermes Global Hot requires middleware schema hermes.middleware.v2"
        )
    if TRANSPORT_SCHEMA_VERSION != "hermes.transport.v3":
        raise RuntimeError("Hermes Global Hot requires hermes.transport.v3")


def register(ctx: Any) -> None:
    """Register request projection, scoped execution proof, and receipts."""

    _require_compatible_host(ctx)
    source_service = ctx.get_service(SOURCE_SERVICE_KEY)
    if not callable(getattr(source_service, "read_window", None)):
        raise RuntimeError(
            "Hermes Global Hot requires service " + SOURCE_SERVICE_KEY
        )
    metadata_path = _path_setting(
        ctx,
        "metadata_db",
        Path(ctx.state.data_dir) / "global_hot.sqlite3",
    )
    state_path = Path(ctx.state.data_dir).parent.parent / "state.db"
    if _same_database(state_path, metadata_path):
        raise RuntimeError(
            "Hermes Global Hot metadata_db must not alias Hermes state.db"
        )
    runtime = GlobalHotRuntime(
        source_service,
        GlobalHotMetadataStore(metadata_path),
        source_resolver=lambda: ctx.get_service(SOURCE_SERVICE_KEY),
        max_projection_chars=ctx.get_config(
            "max_projection_chars", default=24_000
        ),
        max_cached_turns=ctx.get_config("max_cached_turns", default=128),
        attempt_ttl_seconds=ctx.get_config(
            "attempt_ttl_seconds", default=600.0
        ),
    )
    command = ctx.register_command(
        "global-hot-status",
        runtime.status_command,
        description="Show body-free Global Hot check and delivery status",
        args_hint="[session_id]",
    )
    if command is None:
        raise RuntimeError("Hermes Global Hot could not register /global-hot-status")

    ctx.register_middleware("llm_request", runtime.llm_request)
    ctx.register_middleware("llm_execution", runtime.llm_execution)
    ctx.register_hook("post_api_request", runtime.post_api_request)
    ctx.register_hook("api_request_error", runtime.api_request_error)
    ctx.on_unload(runtime.clear)
