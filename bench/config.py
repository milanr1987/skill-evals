"""Load skills.toml."""
from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TOKEN_BUDGET = 3_000_000
DEFAULT_MAX_COST_USD = 5.0
PLUGIN_PREFIX = "plugin:"


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class SuiteConfig:
    name: str
    sources: tuple[Path, ...]
    tags: tuple[str, ...]
    allow_tools: tuple[str, ...]
    token_budget: int
    max_cost_usd: float
    ablation: str
    path_map: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class BenchConfig:
    suites: dict[str, SuiteConfig]
    protected: tuple[Path, ...]


def default_installed_plugins() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
    return Path(base) / "plugins" / "installed_plugins.json"


def _local(entry: str, base: Path) -> Path:
    p = Path(entry)
    return p if p.is_absolute() else base / p


def resolve_source(entry: str, installed_plugins: Path, base: Path = Path(".")) -> Path:
    if not entry.startswith(PLUGIN_PREFIX):
        return _local(entry, base)
    plugin_id, _, skill = entry[len(PLUGIN_PREFIX):].partition("/")
    if not skill:
        raise ConfigError(f"source '{entry}' must look like plugin:<id>/<skill>")
    try:
        data = json.loads(installed_plugins.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot read {installed_plugins}: {exc}") from exc
    installs = data.get("plugins", data).get(plugin_id)
    if not installs:
        raise ConfigError(f"plugin is not installed: {plugin_id}")
    user = [i for i in installs if i.get("scope") == "user"] or installs
    return Path(user[0]["installPath"]) / "skills" / skill


def _suite(name: str, raw: dict, installed_plugins: Path, base: Path) -> SuiteConfig:
    if "source" in raw and "sources" in raw:
        raise ConfigError(f"[{name}]: use 'source' or 'sources', not both")
    if "source" in raw:
        entries = [raw["source"]]
    elif "sources" in raw:
        entries = list(raw["sources"])
    else:
        raise ConfigError(f"[{name}]: missing 'source' or 'sources'")
    if not entries:
        raise ConfigError(f"[{name}]: 'sources' is empty")
    path_map = tuple(sorted(raw.get("path_map", {}).items(), key=lambda kv: len(kv[0]), reverse=True))
    return SuiteConfig(
        name=name,
        sources=tuple(resolve_source(e, installed_plugins, base) for e in entries),
        tags=tuple(raw.get("tags", [])),
        allow_tools=tuple(raw.get("allow_tools", ["Write", "Edit"])),
        token_budget=int(raw.get("token_budget", DEFAULT_TOKEN_BUDGET)),
        max_cost_usd=float(raw.get("max_cost_usd", DEFAULT_MAX_COST_USD)),
        ablation=str(raw.get("ablation", "with-without")),
        path_map=path_map,
    )


def _protected(raw: dict, base: Path) -> tuple[Path, ...]:
    paths = [_local(p, base) for p in raw.get("files", [])]
    for d in raw.get("dirs", []):
        paths.extend(sorted(_local(d, base).glob("*.md")))
    return tuple(paths)


def load_config(path: Path, installed_plugins: Path | None = None) -> BenchConfig:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    protect = data.pop("protect", {})
    installed = installed_plugins or default_installed_plugins()
    base = path.resolve().parent
    suites = {name: _suite(name, raw, installed, base) for name, raw in data.items()}
    return BenchConfig(suites=suites, protected=_protected(protect, base))
