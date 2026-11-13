"""Small HTML form parser shared by the form-contract regression tests."""
from __future__ import annotations

from dataclasses import dataclass, replace
from html.parser import HTMLParser


@dataclass(frozen=True)
class ParsedField:
    name: str
    field_id: str | None
    field_type: str
    # Submitted values of a ``<select>``'s ``<option>`` children, in document
    # order (an option without ``value`` submits its text). Empty for other
    # field types.
    options: tuple[str, ...] = ()


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
        # Index into ``_fields`` of the named <select> being parsed, its
        # collected option values, and the text of a value-less <option>.
        self._select_index: int | None = None
        self._select_options: list[str] = []
        self._option_text: list[str] | None = None

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

        if tag.lower() == "option":
            if self._select_index is not None:
                self._finish_option()
                value = attrs_map.get("value")
                if value is None:
                    self._option_text = []
                else:
                    self._select_options.append(value)
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
        if tag.lower() == "select":
            self._finish_select()
            self._select_index = len(self._fields) - 1
            self._select_options = []

    def handle_data(self, data: str) -> None:
        if self._option_text is not None:
            self._option_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered == "option":
            self._finish_option()
        elif lowered == "select":
            self._finish_select()
        elif lowered == "form" and self._inside_form:
            self._finish_form()

    def _finish_option(self) -> None:
        if self._option_text is not None:
            self._select_options.append(" ".join("".join(self._option_text).split()))
            self._option_text = None

    def _finish_select(self) -> None:
        self._finish_option()
        if self._select_index is not None:
            field = self._fields[self._select_index]
            self._fields[self._select_index] = replace(
                field, options=tuple(self._select_options)
            )
        self._select_index = None
        self._select_options = []

    def close(self) -> None:
        super().close()
        if self._inside_form:
            self._finish_form()

    def _finish_form(self) -> None:
        self._finish_select()
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
