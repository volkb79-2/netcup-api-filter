"""Default-deny guard for request metadata that can expose forwarded headers."""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"

# `/myip` intentionally echoes X-Forwarded-For and X-Real-IP for diagnostics.
DIAGNOSTIC_ALLOWLIST = {("netcup_api_filter/api/dns_api.py", "my_ip")}
# This one call inspects names only to decide whether to log the zero-hop warning.
KEYS_ALLOWLIST = {
    ("netcup_api_filter/app.py", "warn_if_forwarded_headers_are_ignored"),
}
REQUEST_SURFACES = {
    "headers": "headers",
    "environ": "environ",
    "access-route": "access_route",
    "remote-route": "remote_route",
    "forwarded": "forwarded",
}
NON_PYTHON_SURFACE = re.compile(
    r"\brequest\s*\.\s*(?:headers|environ|access_route|remote_route|forwarded|"
    r"x[-_]forwarded(?:[-_][a-z0-9_-]*)?|x[-_]real[-_]ip|client[-_]ip|"
    r"true[-_]client[-_]ip|cf[-_]connecting[-_]ip|via|proxy[-_][a-z0-9_-]*)\b",
    re.IGNORECASE,
)


def _is_forwarded_header_name(value: str) -> bool:
    normalized = value.strip().lower().replace("_", "-")
    while normalized.startswith("http-"):
        normalized = normalized[5:]
    return (
        normalized in {
            "forwarded", "x-forwarded", "x-real-ip", "client-ip",
            "true-client-ip", "cf-connecting-ip", "via",
        }
        or normalized.startswith("x-forwarded-")
        or normalized.startswith("proxy-")
    )


def _literal_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _target_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        return [name for element in node.elts for name in _target_names(element)]
    return []


def _is_getattr_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) >= 2
    )


def _request_attribute_kind(name: str) -> str | None:
    normalized = name.strip().lower().replace("_", "-")
    if normalized in REQUEST_SURFACES:
        return REQUEST_SURFACES[normalized]
    if _is_forwarded_header_name(normalized):
        return "forwarded-adjacent attribute"
    return None


def _imported_request_aliases(tree: ast.Module) -> set[str]:
    aliases = {"request"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "flask":
            for imported in node.names:
                if imported.name == "request":
                    aliases.add(imported.asname or imported.name)
    return aliases


def _surface_kind(
    node: ast.AST,
    request_aliases: set[str],
    surface_aliases: dict[str, str],
) -> str | None:
    if isinstance(node, ast.Name):
        return surface_aliases.get(node.id)
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        if node.value.id in request_aliases:
            return _request_attribute_kind(node.attr)
    if _is_getattr_call(node):
        base, name = node.args[:2]
        if isinstance(base, ast.Name) and base.id in request_aliases:
            literal_name = _literal_string(name)
            if literal_name is not None:
                return _request_attribute_kind(literal_name)
    return None


def _collect_aliases(tree: ast.Module):
    request_aliases = _imported_request_aliases(tree)
    surface_aliases: dict[str, str] = {}
    assignments = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr))
    ]
    for _ in range(len(assignments) + 1):
        changed = False
        for node in assignments:
            value = node.value
            if isinstance(value, ast.Name) and value.id in request_aliases:
                kind = "request"
            else:
                kind = _surface_kind(value, request_aliases, surface_aliases)
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                for name in _target_names(target):
                    if kind == "request" and name not in request_aliases:
                        request_aliases.add(name)
                        changed = True
                    elif kind not in {None, "request"} and surface_aliases.get(name) != kind:
                        surface_aliases[name] = kind
                        changed = True
        if not changed:
            break
    return request_aliases, surface_aliases


def _parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return parents


def _function_scope(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> ast.AST | None:
    current = parents.get(node)
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            return current
        current = parents.get(current)
    return None


def _scope_name(scope: ast.AST | None) -> str | None:
    if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return scope.name
    return None


def _source_line(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> int:
    current: ast.AST | None = node
    while current is not None:
        line = getattr(current, "lineno", None)
        if line is not None:
            return line
        current = parents.get(current)
    return 1


def _literal_get_name(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str | None:
    accessor = parents.get(node)
    if not (
        isinstance(accessor, ast.Attribute)
        and accessor.attr == "get"
        and accessor.value is node
    ):
        return None
    call = parents.get(accessor)
    if not (
        isinstance(call, ast.Call)
        and call.func is accessor
        and len(call.args) == 1
        and not call.keywords
    ):
        return None
    return _literal_string(call.args[0])


def _literal_subscript_name(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str | None:
    parent = parents.get(node)
    if isinstance(parent, ast.Subscript) and parent.value is node:
        return _literal_string(parent.slice)
    return None


def _literal_membership_name(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str | None:
    parent = parents.get(node)
    if (
        isinstance(parent, ast.Compare)
        and len(parent.ops) == 1
        and isinstance(parent.ops[0], ast.In)
        and len(parent.comparators) == 1
        and parent.comparators[0] is node
    ):
        return _literal_string(parent.left)
    return None


def _diagnostic_echo_is_allowed(
    node: ast.AST,
    surface: str,
    relpath: str,
    parents: dict[ast.AST, ast.AST],
) -> bool:
    scope = _function_scope(node, parents)
    if surface != "headers" or (relpath, _scope_name(scope)) not in DIAGNOSTIC_ALLOWLIST:
        return False
    name = _literal_get_name(node, parents)
    return name is not None and name.strip().lower().replace("_", "-") in {
        "x-forwarded-for", "x-real-ip",
    }


def _zero_hop_keys_call_is_allowed(
    node: ast.AST,
    surface: str,
    relpath: str,
    tree: ast.Module,
    parents: dict[ast.AST, ast.AST],
    request_aliases: set[str],
    surface_aliases: dict[str, str],
) -> bool:
    scope = _function_scope(node, parents)
    if (
        surface != "headers"
        or (relpath, _scope_name(scope)) not in KEYS_ALLOWLIST
        or not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef))
    ):
        return False
    method = parents.get(node)
    call = parents.get(method) if isinstance(method, ast.Attribute) else None
    loop = parents.get(call) if isinstance(call, ast.Call) else None
    if not (
        isinstance(method, ast.Attribute)
        and method.attr == "keys"
        and method.value is node
        and isinstance(call, ast.Call)
        and call.func is method
        and not call.args
        and not call.keywords
        and isinstance(loop, ast.comprehension)
        and loop.iter is call
    ):
        return False

    keys_calls = [
        candidate
        for candidate in ast.walk(scope)
        if isinstance(candidate, ast.Call)
        and isinstance(candidate.func, ast.Attribute)
        and candidate.func.attr == "keys"
        and _surface_kind(candidate.func.value, request_aliases, surface_aliases) == "headers"
    ]
    return len(keys_calls) == 1 and keys_calls[0] is call


def _safe_surface_occurrence(
    node: ast.AST,
    surface: str,
    relpath: str,
    tree: ast.Module,
    parents: dict[ast.AST, ast.AST],
    request_aliases: set[str],
    surface_aliases: dict[str, str],
) -> bool:
    if surface in {"headers", "environ"}:
        name = (
            _literal_get_name(node, parents)
            or _literal_subscript_name(node, parents)
            or _literal_membership_name(node, parents)
        )
        if name is not None and not _is_forwarded_header_name(name):
            return True
    if _diagnostic_echo_is_allowed(node, surface, relpath, parents):
        return True
    return _zero_hop_keys_call_is_allowed(
        node, surface, relpath, tree, parents, request_aliases, surface_aliases
    )


def _dynamic_request_getattr(node: ast.AST, request_aliases: set[str]) -> bool:
    return (
        _is_getattr_call(node)
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id in request_aliases
        and _literal_string(node.args[1]) is None
    )


def _raw_header_reads_from_source(
    source: str,
    relpath: str = "<synthetic>.py",
) -> list[tuple[int, str]]:
    tree = ast.parse(source, filename=relpath)
    request_aliases, surface_aliases = _collect_aliases(tree)
    parents = _parent_map(tree)
    violations: set[tuple[int, str]] = set()

    for node in ast.walk(tree):
        if _dynamic_request_getattr(node, request_aliases):
            violations.add((
                _source_line(node, parents),
                "dynamic request attribute access; read a literal header name or add a justified allowlist entry",
            ))

        surface = _surface_kind(node, request_aliases, surface_aliases)
        if surface is None:
            continue
        if _safe_surface_occurrence(
            node, surface, relpath, tree, parents, request_aliases, surface_aliases
        ):
            continue
        violations.add((
            _source_line(node, parents),
            f"unapproved request.{surface} access; read one literal header name or add a justified allowlist entry",
        ))

    return sorted(violations)


def _raw_header_reads(path: Path) -> list[tuple[int, str]]:
    relpath = path.relative_to(SRC).as_posix()
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    if path.suffix == ".py":
        return _raw_header_reads_from_source(source, relpath)

    return [
        (lineno, "unapproved request metadata access; read one literal header name or add a justified allowlist entry")
        for lineno, line in enumerate(source.splitlines(), start=1)
        if NON_PYTHON_SURFACE.search(line)
    ]


def test_src_never_reads_client_address_from_forwarded_headers():
    violations = []
    for path in sorted(path for path in SRC.rglob("*") if path.is_file()):
        relpath = path.relative_to(SRC).as_posix()
        for lineno, description in _raw_header_reads(path):
            violations.append(f"{relpath}:{lineno}: {description}")

    assert not violations, (
        "Read a single literal header name with .get(), [], or literal membership, "
        "or add a justified allowlist entry; forbidden request metadata access:\n"
        + "\n".join(violations)
    )


@pytest.mark.parametrize("source", [
    'def f(): return request.headers.getlist("X-Forwarded-For")',
    'def f(): return request.headers.get_all("HTTP_X_FORWARDED_FOR")',
    'def f(): return request.headers.GETLIST(" x_forwarded_for ")',
    'def f(): return getattr(request.headers, "get")("X-Forwarded-For")',
    'def f(name): return getattr(request.headers, name)("X-Forwarded-For")',
    'HEADER = "X-Forwarded-For"\ndef f(): return request.headers.get(HEADER)',
    'def f(): name = "X-Forwarded-" + "For"; return request.headers.get(name)',
    'def f(name):\n    request.headers.get("X-Forwarded-For")\n    return request.headers.get(name)',
    'def f(name):\n    request.environ.get("HTTP_X_FORWARDED_FOR")\n    return request.environ.get(name)',
    'def f(): return request.environ.get("HTTP_X_FORWARDED_FOR")',
    'def f(): return request.environ["HTTP_X_REAL_IP"]',
    'def f(): return request.environ.get("HTTP_FORWARDED")',
    'def f(): return request.environ["HTTP_X_FORWARDED_FOR"]',
    'def f(): return request.headers.__getitem__("X-Forwarded-For")',
    'def f(): return getattr(request.environ, "get")("HTTP_FORWARDED")',
    'from flask import request as req\ndef f(): return req.headers.get("X-Forwarded-For")',
    'def f():\n    headers = request.headers\n    key = "X-Forwarded-" + "For"\n    return headers.get_all(key)',
    'def f():\n    env = request.environ\n    key = "HTTP_X_FORWARDED_" + "HOST"\n    return env[key]',
])
def test_synthetic_forwarded_header_bypasses_are_rejected(source):
    assert _raw_header_reads_from_source(source)


@pytest.mark.parametrize("source", [
    '''def f():
    for name, value in request.headers.items():
        if name.lower() == "x-forwarded-for":
            return value
''',
    '''def f():
    for name, value in request.headers.to_wsgi_list():
        if name.lower() == "x-forwarded-for":
            return value
''',
    'def f(): return request.headers.values()',
    '''def f():
    for name, value in request.environ.items():
        if name == "HTTP_X_FORWARDED_FOR":
            return value
''',
    '''def f():
    for name in request.headers:
        if name.lower() == "x-forwarded-for":
            return name
''',
    'def f(): return list(request.headers)',
    'def f(): return dict(request.environ)',
    'def f(): return request.headers.copy()',
    'def f(): return request.headers.to_dict()',
    'def f(): return request.environ.lists()',
    'def f(): return request.headers.keys()',
    '''def f(name):
    names = request.headers.keys()
    return request.headers[name]
''',
])
def test_synthetic_header_enumeration_bypasses_are_rejected(source):
    assert _raw_header_reads_from_source(source)


@pytest.mark.parametrize("source", [
    'def f(): return helper(**request.headers)',
    'def f(): return helper(**request.environ)',
    'def f(): return str(request.headers)',
    'def f(): return repr(request.environ)',
    'def f(): return f"{request.headers}"',
    'def f(): return helper(request.headers)',
    'def f(): return request.headers',
    'def f():\n    x = request.headers\n    helper(x)',
    'def f(): return lambda: request.headers',
    'def f(): return [value for value in request.headers.values()]',
    'def f(): return [name for name in request.headers]',
    'def f(): return request.remote_route',
    'def f(): return request.access_route',
    'def f(): return getattr(request, name)',
])
def test_synthetic_whole_mapping_exposures_are_rejected(source):
    assert _raw_header_reads_from_source(source)


@pytest.mark.parametrize("attribute", [
    "forwarded", "x_forwarded_for", "x_real_ip", "client_ip",
    "true_client_ip", "cf_connecting_ip", "via", "proxy_ip",
])
def test_forwarded_adjacent_request_attributes_are_rejected(attribute):
    source = f"def f(): return request.{attribute}"
    assert _raw_header_reads_from_source(source)


@pytest.mark.parametrize("header_name", [
    "Forwarded", "X-Forwarded-For", "X_Forwarded_Host", "X-Real-IP",
    "Client-IP", "True-Client-IP", "CF-Connecting-IP", "Via", "Proxy-Client-IP",
    "HTTP_X_FORWARDED_FOR",
])
def test_forwarded_adjacent_literal_header_names_are_rejected(header_name):
    source = f'def f(): return request.headers.get("{header_name}")'
    assert _raw_header_reads_from_source(source)


@pytest.mark.parametrize("source", [
    'def f(): return request.headers.get("Authorization")',
    'def f(): return request.headers.get("User-Agent")',
    'def f(): return "X-Foo" in request.headers',
    'def f(): return request.headers["X-Foo"]',
    'def f(): return request.environ.get("REQUEST_METHOD")',
    'def f(): return request.environ["REQUEST_METHOD"]',
])
def test_literal_non_forwarded_header_reads_are_allowed(source):
    assert _raw_header_reads_from_source(source) == []


def test_diagnostic_echo_is_allowed_only_at_the_myip_allowlist_entry():
    diagnostic_echo = '''
def my_ip():
    return {
        "x-forwarded-for": request.headers.get("X-Forwarded-For"),
        "x-real-ip": request.headers.get("X-Real-IP"),
    }
'''

    assert _raw_header_reads_from_source(
        diagnostic_echo, "netcup_api_filter/api/dns_api.py"
    ) == []
    assert _raw_header_reads_from_source(diagnostic_echo)
    assert _raw_header_reads(SRC / "netcup_api_filter/api/dns_api.py") == []


def test_zero_hop_keys_check_is_allowed_only_at_the_real_app_site():
    actual_app = SRC / "netcup_api_filter/app.py"
    assert _raw_header_reads(actual_app) == []

    generic_keys_inspection = '''def f():
    return any(name for name in request.headers.keys())
'''
    assert _raw_header_reads_from_source(generic_keys_inspection)


def test_local_header_labels_are_not_request_header_aliases():
    source = '''def f():
    headers = ["Timestamp", "Action", "Status", "Source IP", "Details"]
    return [label for label in headers]
'''

    assert _raw_header_reads_from_source(source) == []
