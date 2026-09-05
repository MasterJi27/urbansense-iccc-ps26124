"""SQLAlchemy JSON-field writes. Reassignment alone can miss dirty tracking."""

from __future__ import annotations

from sqlalchemy.orm.attributes import flag_modified


def write_json_field(entity, field: str, value) -> None:
    setattr(entity, field, value)
    flag_modified(entity, field)


def write_extra(entity, extra: dict) -> None:
    write_json_field(entity, "extra", extra)
