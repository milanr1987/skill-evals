"""Copy skills into a wrapper plugin, rewrite paths, assemble scaffold scripts."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from bench.config import SuiteConfig
from bench.protect import sha256_file

TEXT_SUFFIXES = {
    ".md", ".txt", ".py", ".js", ".mjs", ".cjs", ".ts", ".json",
    ".yaml", ".yml", ".toml", ".sh", ".html", ".css",
}


def home_path_pattern(home: Path | None = None) -> re.Pattern:
    parts = [re.escape(p) for p in re.split(r"[\\/]+", str(home or Path.home())) if p]
    return re.compile(r"[\\/]+".join(parts) + r"(?!\w)", re.IGNORECASE)


class SyncError(Exception):
    pass


def _rewrite(path: Path, path_map: tuple[tuple[str, str], ...], home: re.Pattern) -> list[int]:
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            text = fh.read()
    except UnicodeDecodeError as exc:
        raise SyncError(f"file is not UTF-8: {path}") from exc
    new = text
    for old, repl in path_map:
        new = new.replace(old, repl)
        alt = old.replace("\\", "/")
        if alt != old:
            new = new.replace(alt, repl)
    if new != text:
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(new)
    return [i for i, line in enumerate(new.splitlines(), 1) if home.search(line)]


def _assemble_scaffolds(suite_dir: Path) -> None:
    fixture = suite_dir / "_fixture.sh"
    if not fixture.is_file():
        return
    base = fixture.read_text(encoding="utf-8").replace("\r\n", "\n")
    for case_yaml in sorted((suite_dir / "evals").glob("*/case.yaml")):
        case_dir = case_yaml.parent
        extra = case_dir / "extra.sh"
        body = base
        if extra.is_file():
            body = base.rstrip("\n") + "\n\n" + extra.read_text(encoding="utf-8").replace("\r\n", "\n")
        with open(case_dir / "scaffold.sh", "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)


def _ensure_manifest(suite_dir: Path, name: str) -> None:
    manifest = suite_dir / ".claude-plugin" / "plugin.json"
    if manifest.is_file():
        return
    manifest.parent.mkdir(parents=True, exist_ok=True)
    data = {"name": f"bench-{name}", "version": "0.0.0", "description": "skill-evals wrapper"}
    manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sync_suite(cfg: SuiteConfig, suites_dir: Path) -> dict[str, str]:
    suite_dir = suites_dir / cfg.name
    skills_dir = suite_dir / "skills"
    if skills_dir.exists():
        shutil.rmtree(skills_dir)
    skills_dir.mkdir(parents=True)
    _ensure_manifest(suite_dir, cfg.name)

    hashes: dict[str, str] = {}
    for src in cfg.sources:
        skill_md = src / "SKILL.md"
        if not skill_md.is_file():
            shutil.rmtree(skills_dir)
            raise SyncError(f"no SKILL.md in {src}")
        shutil.copytree(src, skills_dir / src.name)
        hashes[src.name] = sha256_file(skill_md)

    home = home_path_pattern()
    leftovers: list[str] = []
    for f in sorted(skills_dir.rglob("*")):
        if f.is_file() and f.suffix.lower() in TEXT_SUFFIXES:
            for line_no in _rewrite(f, cfg.path_map, home):
                leftovers.append(f"{f.relative_to(skills_dir / f.relative_to(skills_dir).parts[0])}:{line_no}")
    if leftovers:
        shutil.rmtree(skills_dir)
        raise SyncError(f"the copy still contains a path into your home folder ({Path.home()}), add it to path_map: " + ", ".join(leftovers))

    (suite_dir / ".source-hash").write_text(json.dumps(hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _assemble_scaffolds(suite_dir)
    return hashes
