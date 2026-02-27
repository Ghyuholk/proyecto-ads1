from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app.auth_utils import roles_required
from app.extensions import db
from app.models import Mesa, MesaEstadoEnum, Pedido, PedidoEstadoEnum, RoleEnum
from app.routes.utils import enum_value, error_response, parse_enum


mesas_bp = Blueprint("mesas", __name__, url_prefix="/mesas")


@mesas_bp.get("")
@jwt_required()
@roles_required(RoleEnum.ADMIN, RoleEnum.CAJERO, RoleEnum.MESERO, RoleEnum.COCINA)
def list_mesas():
    mesas = db.session.query(Mesa).order_by(Mesa.numero.asc()).all()
    return jsonify([
        {"id": m.id, "numero": m.numero, "estado": enum_value(m.estado)}
        for m in mesas
    ])


@mesas_bp.post("")
@jwt_required()
@roles_required(RoleEnum.ADMIN, RoleEnum.MESERO)
def create_mesa():
    data = request.get_json() or {}
    numero = data.get("numero")
    estado_raw = data.get("estado", MesaEstadoEnum.LIBRE.value)

    if numero is None:
        return error_response("numero es requerido")

    try:
        estado = parse_enum(MesaEstadoEnum, estado_raw, "estado")
    except ValueError as exc:
        return error_response(str(exc))

    mesa = Mesa(numero=int(numero), estado=estado)
    db.session.add(mesa)
    db.session.commit()
    return jsonify({"id": mesa.id, "numero": mesa.numero, "estado": enum_value(mesa.estado)}), 201


@mesas_bp.patch("/<int:mesa_id>")
@jwt_required()
@roles_required(RoleEnum.ADMIN, RoleEnum.MESERO)
def update_mesa(mesa_id):
    mesa = db.session.get(Mesa, mesa_id)
    if not mesa:
        return error_response("Mesa no encontrada", 404)

    data = request.get_json() or {}
    if "estado" in data:
        try:
            nuevo_estado = parse_enum(MesaEstadoEnum, data["estado"], "estado")
        except ValueError as exc:
            return error_response(str(exc))
        if nuevo_estado == MesaEstadoEnum.LIBRE:
            pedidos_activos = (
                db.session.query(Pedido)
                .filter(
                    Pedido.mesa_id == mesa_id,
                    Pedido.estado.notin_([PedidoEstadoEnum.CANCELADO, PedidoEstadoEnum.COBRADO]),
                )
                .count()
            )
            if pedidos_activos > 0:
                return error_response("No se puede liberar mesa con pedido activo")
        mesa.estado = nuevo_estado

    if "numero" in data:
        mesa.numero = int(data["numero"])

    db.session.commit()
    return jsonify({"id": mesa.id, "numero": mesa.numero, "estado": enum_value(mesa.estado)})
