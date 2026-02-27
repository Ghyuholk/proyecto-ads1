from functools import wraps

from flask import jsonify
from flask_jwt_extended import get_jwt, get_jwt_identity

from app.extensions import db
from app.models import RoleEnum, User


def get_current_user():
    identity = get_jwt_identity()
    if identity is None:
        return None
    return db.session.get(User, int(identity))


def roles_required(*allowed_roles):
    allowed = {role.value if isinstance(role, RoleEnum) else str(role) for role in allowed_roles}

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            claims = get_jwt()
            role = claims.get("role")
            if role not in allowed:
                return jsonify({"error": "No autorizado para este recurso"}), 403

            user = get_current_user()
            if not user or not user.is_active:
                return jsonify({"error": "Usuario inválido o inactivo"}), 401

            return fn(*args, **kwargs)

        return wrapper

    return decorator
