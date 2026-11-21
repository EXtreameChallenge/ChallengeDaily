"""B34 legacy module aliases.

The implementation modules now live in core/, services/ and integrations/.
Historical imports such as ``import config`` or ``from collector import Collector``
are kept working through a lazy meta-path finder.  Nothing is eagerly imported;
each alias is resolved the first time it is requested.
"""
from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import pkgutil
import sys
import types
from pathlib import Path

_PACKAGES = ("core", "services", "integrations")
_ROOT = Path(__file__).resolve().parent
_MAP = None
_INSTALLED = False


def _build_map():
    mapping = {}
    for pkg in _PACKAGES:
        pkg_dir = _ROOT / pkg
        if not pkg_dir.is_dir():
            continue
        for info in pkgutil.iter_modules([str(pkg_dir)]):
            if info.name.startswith("_"):
                continue
            if info.name in mapping:
                raise RuntimeError(f"legacy module name collision: {info.name}")
            mapping[info.name] = f"{pkg}.{info.name}"
    return mapping


class _AliasModule(types.ModuleType):
    """A thin proxy so aliases and canonical modules share attribute state."""

    def __init__(self, name, target):
        super().__init__(name)
        object.__setattr__(self, "_cd_target", target)

    def __getattribute__(self, name):
        if name == "__dict__":
            return object.__getattribute__(
                object.__getattribute__(self, "_cd_target"), "__dict__"
            )
        return object.__getattribute__(self, name)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_cd_target"), name)

    def __setattr__(self, name, value):
        if name.startswith("__") and name.endswith("__"):
            object.__setattr__(self, name, value)
        else:
            setattr(object.__getattribute__(self, "_cd_target"), name, value)

    def __delattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            object.__delattr__(self, name)
        else:
            delattr(object.__getattribute__(self, "_cd_target"), name)

    def __dir__(self):
        return dir(object.__getattribute__(self, "_cd_target"))

    def __repr__(self):
        return repr(object.__getattribute__(self, "_cd_target"))


class _AliasLoader(importlib.abc.Loader):
    def __init__(self, target):
        self.target = target

    def create_module(self, spec):
        target_module = importlib.import_module(self.target)
        return _AliasModule(spec.name, target_module)

    def exec_module(self, module):
        return None


class _AliasFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        target_name = _MAP.get(fullname)
        if not target_name:
            return None
        return importlib.util.spec_from_loader(fullname, _AliasLoader(target_name))


def install():
    global _MAP, _INSTALLED
    if _INSTALLED:
        return
    _MAP = _build_map()
    sys.meta_path.insert(0, _AliasFinder())
    _INSTALLED = True


def module_map():
    """Return a copy of the legacy-name -> package-name mapping."""
    install()
    return dict(_MAP)
