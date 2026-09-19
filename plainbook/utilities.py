"""Utility code that is not part of the notebook logic proper.

Currently: support for installing pip packages for missing Python modules.
The import (module) name does not always match the pip package name
(e.g. the module ``cv2`` is provided by the package ``opencv-python``).
PyPI has no API to look up a package by import name, so we use the mapping
maintained by the pipreqs project, which was built by scanning the wheels
published on PyPI; a small builtin map serves as offline fallback.
"""

import json
import re

import requests

# URL of the import-name -> package-name mapping maintained by pipreqs.
# Plain text, one "module:package" entry per line.
PIPREQS_MAPPING_URL = "https://raw.githubusercontent.com/bndr/pipreqs/master/pipreqs/mapping"

# Builtin fallback for the most common cases in which the module and
# package names differ, used when the online mapping cannot be fetched.
MODULE_TO_PACKAGE = {
    "bs4": "beautifulsoup4",
    "cv2": "opencv-python",
    "dateutil": "python-dateutil",
    "PIL": "Pillow",
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
}

# Code executed in the kernel to install a package.  pip's output is captured
# and reported back as a single JSON object on stdout.  %s is replaced with
# the package name as a Python string literal.
PIP_INSTALL_CODE = """
import json, subprocess, sys
_r = subprocess.run([sys.executable, "-m", "pip", "install", %s],
                    capture_output=True, text=True)
print(json.dumps({"returncode": _r.returncode,
                  "stdout": _r.stdout, "stderr": _r.stderr}))
"""

# The pipreqs mapping, fetched lazily and cached for the server's lifetime.
_module_to_package_cache = None


def _get_module_mapping():
    """Returns the module -> package mapping, fetching it from the pipreqs
    repository on first use.  On fetch failure returns the builtin fallback
    (and retries the fetch on the next call)."""
    global _module_to_package_cache
    if _module_to_package_cache is None:
        try:
            resp = requests.get(PIPREQS_MAPPING_URL, timeout=5)
            resp.raise_for_status()
            mapping = dict(MODULE_TO_PACKAGE)
            for line in resp.text.splitlines():
                module, sep, package = line.partition(":")
                if sep and module and package:
                    mapping[module.strip()] = package.strip()
            _module_to_package_cache = mapping
        except Exception:
            return MODULE_TO_PACKAGE
    return _module_to_package_cache


def resolve_package_name(module_name):
    """Returns the name of the pip package providing `module_name`.
    Raises ValueError if the module name is not a plausible identifier."""
    module_name = (module_name or '').split('.')[0].strip()
    if not re.fullmatch(r'[A-Za-z0-9_\-]+', module_name):
        raise ValueError(f"Invalid module name: {module_name!r}")
    return _get_module_mapping().get(module_name, module_name)


def parse_pip_install_result(stdout_text):
    """Parses the JSON report printed by PIP_INSTALL_CODE.
    Returns (success, output_text)."""
    try:
        r = json.loads(stdout_text)
    except (json.JSONDecodeError, TypeError):
        return False, stdout_text or "pip install produced no output."
    output = (r.get("stdout") or "")
    if r.get("stderr"):
        output += ("\n" if output else "") + r["stderr"]
    return r.get("returncode") == 0, output.strip()
