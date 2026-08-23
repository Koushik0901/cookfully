#!/usr/bin/env python3
"""Wrapper for hyphen-named entrypoint; delegates to needle_threshold_sweep."""
import pathlib, sys, importlib.util

_underscore = pathlib.Path(__file__).with_name("needle_threshold_sweep.py")
spec = importlib.util.spec_from_file_location("needle_threshold_sweep", _underscore)
mod = importlib.util.module_from_spec(spec)  # type: ignore
sys.modules["needle_threshold_sweep"] = mod
assert spec and spec.loader
spec.loader.exec_module(mod)  # type: ignore
# sync scripts package alias for import scripts.needle_threshold_sweep
try:
    import types
    pkg = types.ModuleType("scripts")
    pkg.__path__ = [str(_underscore.parent)]  # type: ignore
    sys.modules.setdefault("scripts", pkg)
    sys.modules["scripts.needle_threshold_sweep"] = mod
except Exception:
    pass

if __name__ == "__main__":
    mod.main()
