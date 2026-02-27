from enum import Enum

from flask import jsonify


def error_response(message, status=400):
    return jsonify({"error": message}), status


def parse_enum(enum_cls, raw_value, field_name):
    if raw_value is None:
        raise ValueError(f"{field_name} es requerido")
    try:
        return enum_cls(raw_value)
    except ValueError as exc:
        valid = ", ".join([e.value for e in enum_cls])
        raise ValueError(f"{field_name} inválido. Valores permitidos: {valid}") from exc


def enum_value(value):
    if isinstance(value, Enum):
        return value.value
    return value
