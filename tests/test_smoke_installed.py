"""Provider-free checks for the installed-wheel Runtime-path smoke helper."""

import importlib.util
import json
import sys
import urllib.request
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_smoke_script() -> ModuleType:
    path = PROJECT_ROOT / "scripts" / "smoke_installed.py"
    spec = importlib.util.spec_from_file_location("smoke_installed", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["smoke_installed"] = module
    spec.loader.exec_module(module)
    return module


def test_loopback_provider_fixture_returns_anthropic_sse_without_network() -> None:
    smoke = _load_smoke_script()
    with smoke._provider_fixture() as (base_url, requests):
        request = urllib.request.Request(
            f"{base_url}/v1/messages",
            data=json.dumps(
                {"messages": [{"role": "user", "content": "fixed"}]}
            ).encode(),
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            body = response.read().decode()

    assert len(requests) == 1
    assert "event: message_start" in body
    assert "event: content_block_delta" in body
    assert '"text": "fixture-ok"' in body
    assert "event: message_stop" in body


def test_custom_runtime_core_is_optional_for_standalone_clean_room_mode() -> None:
    source = (PROJECT_ROOT / "scripts" / "smoke_installed.py").read_text()

    assert "if args.custom_runtime_core and not args.custom_runtime:" in source
    assert "--custom-runtime-core requires --custom-runtime" in source
    assert 'runtime_mode = "standalone-clean-room"' in source
    assert '"ANTHROPIC_BASE_URL": provider_base_url' in source
