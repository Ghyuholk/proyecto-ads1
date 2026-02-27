from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt, jwt_required
from werkzeug.security import check_password_hash, generate_password_hash

from app.auth_utils import get_current_user, roles_required
from app.extensions import db
from app.models import RoleEnum, User
from app.routes.utils import error_response, parse_enum


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.get("/users")
@jwt_required()
@roles_required(RoleEnum.ADMIN)
def list_users():
    users = db.session.query(User).order_by(User.id.asc()).all()
    return jsonify(
        [
            {
                "id": u.id,
                "username": u.username,
                "role": u.role.value,
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat(),
            }
            for u in users
        ]
    )


@auth_bp.post("/register")
@jwt_required(optional=True)
def register():
    data = request.get_json() or {}
    username = data.get("username")
    password = data.get("password")
    role_raw = data.get("role", RoleEnum.MESERO.value)

    if not username or not password:
        return error_response("username y password son requeridos")
    if db.session.query(User).filter(User.username == username).first():
        return error_response("username ya existe")

    # Bootstrap: si no hay usuarios permite crear el primero sin token.
    existing_users = db.session.query(User).count()
    if existing_users > 0:
        claims = get_jwt()
        if claims.get("role") != RoleEnum.ADMIN.value:
            return error_response("Solo ADMIN puede registrar usuarios", 403)

    try:
        role = parse_enum(RoleEnum, role_raw, "role")
    except ValueError as exc:
        return error_response(str(exc))

    user = User(
        username=username,
        password_hash=generate_password_hash(password),
        role=role,
        is_active=True,
    )
    db.session.add(user)
    db.session.commit()

    return jsonify({"id": user.id, "username": user.username, "role": user.role.value}), 201


@auth_bp.post("/login")
def login():
    data = request.get_json() or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return error_response("username y password son requeridos")

    user = db.session.query(User).filter(User.username == username, User.is_active.is_(True)).first()
    if not user or not check_password_hash(user.password_hash, password):
        return error_response("Credenciales inválidas", 401)

    claims = {"role": user.role.value, "username": user.username}
    token = create_access_token(identity=str(user.id), additional_claims=claims)

    return jsonify(
        {
            "access_token": token,
            "user": {
                "id": user.id,
                "username": user.username,
                "role": user.role.value,
            },
        }
    )


@auth_bp.get("/me")
@jwt_required()
def me():
    user = get_current_user()
    if not user or not user.is_active:
        return error_response("Usuario inválido o inactivo", 401)

    return jsonify(
        {
            "user": {
                "id": user.id,
                "username": user.username,
                "role": user.role.value,
                "is_active": user.is_active,
            }
        }
    )
