"""Small HTML form parser shared by the form-contract regression tests."""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser


@dataclass(frozen=True)
class ParsedField:
    name: str
    field_id: str | None
    field_type: str


@dataclass(frozen=True)
class ParsedForm:
    action: str | None
    method: str
    fields: tuple[ParsedField, ...]

    @property
    def names(self) -> frozenset[str]:
        return frozenset(field.name for field in self.fields)


class _FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[ParsedForm] = []
        self._action: str | None = None
        self._method = "get"
        self._fields: list[ParsedField] = []
        self._inside_form = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {key.lower(): value for key, value in attrs}
        if tag.lower() == "form":
            if self._inside_form:
                self._finish_form()
            self._inside_form = True
            self._action = attrs_map.get("action")
            self._method = (attrs_map.get("method") or "get").lower()
            self._fields = []
            return

        if not self._inside_form or tag.lower() not in {"input", "select", "textarea"}:
            return

        name = (attrs_map.get("name") or "").strip()
        field_type = (attrs_map.get("type") or tag).lower()
        if (
            not name
            or name == "csrf_token"
            or field_type in {"submit", "button", "reset", "image"}
        ):
            return
        self._fields.append(
            ParsedField(
                name=name,
                field_id=attrs_map.get("id"),
                field_type=field_type,
            )
        )

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "form" and self._inside_form:
            self._finish_form()

    def close(self) -> None:
        super().close()
        if self._inside_form:
            self._finish_form()

    def _finish_form(self) -> None:
        self.forms.append(
            ParsedForm(
                action=self._action,
                method=self._method,
                fields=tuple(self._fields),
            )
        )
        self._inside_form = False
        self._action = None
        self._method = "get"
        self._fields = []


def parse_forms(html: str) -> list[ParsedForm]:
    parser = _FormParser()
    parser.feed(html)
    parser.close()
    return parser.forms


def field_by_id(form: ParsedForm, field_id: str) -> ParsedField:
    matches = [field for field in form.fields if field.field_id == field_id]
    assert len(matches) == 1, (
        f"expected exactly one field #{field_id} in {form.action or 'current action'}, "
        f"found {matches!r}"
    )
    return matches[0]


def csrf_field(html: str) -> tuple[str, str]:
    """Return the rendered (name, value) pair for the page's CSRF field."""
    marker = 'name="csrf_token"'
    marker_index = html.find(marker)
    assert marker_index >= 0, "rendered form has no csrf_token field"
    value_marker = 'value="'
    value_start = html.find(value_marker, marker_index)
    assert value_start >= 0, "rendered csrf_token field has no value"
    value_start += len(value_marker)
    value_end = html.find('"', value_start)
    assert value_end >= 0, "rendered csrf_token value is unterminated"
    return "csrf_token", html[value_start:value_end]
