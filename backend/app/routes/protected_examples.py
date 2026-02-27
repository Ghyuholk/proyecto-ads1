from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from app.auth_utils import roles_required
from app.models import RoleEnum


protected_bp = Blueprint("protected", __name__, url_prefix="/api")


@protected_bp.get("/admin/ping")
@jwt_required()
@roles_required(RoleEnum.ADMIN)
def admin_ping():
    return jsonify({"message": "ok", "scope": "admin"})


@protected_bp.get("/caja/ping")
@jwt_required()
@roles_required(RoleEnum.ADMIN, RoleEnum.CAJERO)
def caja_ping():
    return jsonify({"message": "ok", "scope": "caja"})


@protected_bp.get("/pedidos/ping")
@jwt_required()
@roles_required(RoleEnum.ADMIN, RoleEnum.MESERO, RoleEnum.COCINA)
def pedidos_ping():
    return jsonify({"message": "ok", "scope": "pedidos"})
