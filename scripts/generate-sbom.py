from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

CDXGEN_VERSION = "12.8.2"
ROOT_PURL = "pkg:generic/vigor-vine@0.1.0"
FRONTEND_PURL = "pkg:npm/vigor-vine-web@0.1.0"
BACKEND_PURL = "pkg:pypi/vigor-vine@0.1.0"
LEGACY_ROOT_PURL = "pkg:pypi/gym-focused recipe & nutrition planner@latest"

EXPECTED_DIRECT_LICENSES = {
    "pkg:pypi/fastapi@": "MIT",
    "pkg:pypi/pydantic@": "MIT",
    "pkg:pypi/sqlalchemy@": "MIT",
    "pkg:pypi/alembic@": "MIT",
    "pkg:pypi/psycopg@": "LGPL-3.0-only",
    "pkg:pypi/celery@": "BSD-3-Clause",
    "pkg:pypi/redis@": "MIT",
    "pkg:pypi/httpx@": "BSD-3-Clause",
    "pkg:pypi/recipe-scrapers@": "MIT",
    "pkg:pypi/ingredient-parser-nlp@": "MIT",
    "pkg:pypi/pint@": "0BSD",
    "pkg:pypi/ortools@": "Apache-2.0",
    "pkg:pypi/mcp@": "MIT",
    "pkg:npm/react@": "MIT",
    "pkg:npm/react-router-dom@": "MIT",
    "pkg:npm/%40tanstack/react-query@": "MIT",
    "pkg:npm/react-hook-form@": "MIT",
    "pkg:npm/zod@": "MIT",
    "pkg:npm/%40radix-ui/react-dialog@": "MIT",
    "pkg:npm/vite@": "MIT",
    "pkg:npm/vitest@": "MIT",
    "pkg:npm/%40playwright/test@": "Apache-2.0",
}


def _license_text(component: dict[str, Any]) -> str:
    values: list[str] = []
    for entry in component.get("licenses", []):
        license_value = entry.get("license", {})
        value = license_value.get("id") or license_value.get("name") or entry.get("expression")
        if value:
            values.append(str(value))
    return " OR ".join(values)


def _generate(root: Path, raw_output: Path) -> None:
    environment = os.environ.copy()
    environment.pop("NODE_PATH", None)
    subprocess.run(
        [
            "pnpm",
            "dlx",
            f"@cyclonedx/cdxgen@{CDXGEN_VERSION}",
            "-t",
            "python",
            "-t",
            "js",
            "--no-install-deps",
            "--fail-on-error",
            "--spec-version",
            "1.6",
            "--profile",
            "license-compliance",
            "--json-pretty",
            "-o",
            str(raw_output),
            ".",
        ],
        cwd=root,
        env=environment,
        check=True,
    )


def _normalize(bom: dict[str, Any]) -> None:
    if bom.get("bomFormat") != "CycloneDX" or bom.get("specVersion") != "1.6":
        raise RuntimeError("cdxgen did not produce a CycloneDX 1.6 document")
    components: list[dict[str, Any]] = bom["components"]
    frontend = dict(bom["metadata"]["component"])
    frontend.pop("components", None)
    if frontend.get("purl") != FRONTEND_PURL:
        raise RuntimeError("cdxgen did not identify the locked frontend application")
    frontend["licenses"] = [{"license": {"name": "Proprietary"}}]
    if not any(component.get("purl") == FRONTEND_PURL for component in components):
        components.append(frontend)

    root_component = {
        "type": "application",
        "bom-ref": ROOT_PURL,
        "name": "Vigor & Vine",
        "version": "0.1.0",
        "purl": ROOT_PURL,
        "licenses": [{"license": {"name": "Proprietary"}}],
        "properties": [
            {"name": "vigor-vine:python-lock", "value": "backend/uv.lock"},
            {"name": "vigor-vine:node-lock", "value": "frontend/pnpm-lock.yaml"},
            {"name": "vigor-vine:generator", "value": f"cdxgen {CDXGEN_VERSION}"},
        ],
    }
    bom["metadata"]["component"] = root_component

    dependencies: list[dict[str, Any]] = bom["dependencies"]
    for dependency in dependencies:
        if dependency.get("ref") == FRONTEND_PURL:
            dependency["dependsOn"] = [
                value for value in dependency.get("dependsOn", []) if value != LEGACY_ROOT_PURL
            ]
    dependencies.append({"ref": ROOT_PURL, "dependsOn": [BACKEND_PURL, FRONTEND_PURL]})

    missing = [component for component in components if not _license_text(component)]
    if {(item.get("purl"), item.get("name")) for item in missing} != {
        ("pkg:pypi/mypy-extensions@1.1.0", "mypy-extensions")
    }:
        raise RuntimeError(f"unexpected missing license metadata: {missing!r}")
    missing[0]["licenses"] = [{"license": {"id": "MIT"}}]
    missing[0].setdefault("properties", []).append(
        {
            "name": "vigor-vine:license-metadata-source",
            "value": "https://github.com/python/mypy_extensions/blob/1.1.0/LICENSE",
        }
    )


def _verify(bom: dict[str, Any]) -> None:
    components: list[dict[str, Any]] = bom["components"]
    by_purl = {str(component.get("purl", "")): component for component in components}
    for prefix, expected in EXPECTED_DIRECT_LICENSES.items():
        matches = [component for purl, component in by_purl.items() if purl.startswith(prefix)]
        if len(matches) != 1 or expected not in _license_text(matches[0]):
            raise RuntimeError(f"license mismatch for {prefix}: {matches!r}")
    missing = [component.get("purl") for component in components if not _license_text(component)]
    if missing:
        raise RuntimeError(f"components without license metadata: {missing}")
    incompatible = [
        (component.get("purl"), _license_text(component))
        for component in components
        if re.search(r"(?:AGPL|(?<!L)GPL-[23]\.0|Commons Clause)", _license_text(component))
    ]
    if incompatible:
        raise RuntimeError(f"unapproved dependency licenses: {incompatible}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and verify the locked CycloneDX SBOM.")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / "artifacts" / "sbom.json"
    raw_output = root / "artifacts" / ".sbom.raw.json"
    if not args.verify_only:
        _generate(root, raw_output)
        bom = json.loads(raw_output.read_text(encoding="utf-8"))
        _normalize(bom)
        _verify(bom)
        output.write_text(json.dumps(bom, indent=2) + "\n", encoding="utf-8")
        raw_output.unlink()
    else:
        bom = json.loads(output.read_text(encoding="utf-8"))
        _verify(bom)
    print(f"verified CycloneDX 1.6 SBOM with {len(bom['components'])} components")


if __name__ == "__main__":
    main()
