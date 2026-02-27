from datetime import datetime, time

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, jwt_required

from app.auth_utils import roles_required
from app.extensions import db
from app.models import Mesa, MesaEstadoEnum, Pedido, PedidoDetalle, PedidoEstadoEnum, RoleEnum, User
from app.routes.utils import enum_value, error_response, parse_enum
from app.services.order_service import OrderError, add_item_to_order


pedidos_bp = Blueprint("pedidos", __name__, url_prefix="/pedidos")


@pedidos_bp.get("")
@jwt_required()
@roles_required(RoleEnum.ADMIN, RoleEnum.MESERO, RoleEnum.COCINA, RoleEnum.CAJERO)
def list_pedidos():
    query = db.session.query(Pedido)

    estado = request.args.get("estado")
    if estado:
        try:
            estado_enum = parse_enum(PedidoEstadoEnum, estado, "estado")
            query = query.filter(Pedido.estado == estado_enum)
        except ValueError as exc:
            return error_response(str(exc))

    date_from = request.args.get("date_from")
    if date_from:
        try:
            dt_from = datetime.combine(datetime.fromisoformat(date_from).date(), time.min)
            query = query.filter(Pedido.created_at >= dt_from)
        except ValueError:
            return error_response("date_from inválido, usa YYYY-MM-DD")

    date_to = request.args.get("date_to")
    if date_to:
        try:
            dt_to = datetime.combine(datetime.fromisoformat(date_to).date(), time.max)
            query = query.filter(Pedido.created_at <= dt_to)
        except ValueError:
            return error_response("date_to inválido, usa YYYY-MM-DD")

    pedidos = query.order_by(Pedido.created_at.desc(), Pedido.id.desc()).all()
    return jsonify(
        [
            {
                "id": p.id,
                "mesa_id": p.mesa_id,
                "user_id": p.user_id,
                "estado": enum_value(p.estado),
                "total": p.total,
                "created_at": p.created_at.isoformat(),
                "detalles": [
                    {
                        "id": d.id,
                        "platillo_id": d.platillo_id,
                        "cantidad": d.cantidad,
                        "precio_unitario": d.precio_unitario,
                        "subtotal": d.subtotal,
                    }
                    for d in p.detalles
                ],
            }
            for p in pedidos
        ]
    )


@pedidos_bp.post("")
@jwt_required()
@roles_required(RoleEnum.ADMIN, RoleEnum.MESERO)
def create_pedido():
    data = request.get_json() or {}
    mesa_id = data.get("mesa_id")
    user_id = data.get("user_id")

    if not mesa_id or not user_id:
        return error_response("mesa_id y user_id son requeridos")

    try:
        with db.session.begin_nested():
            mesa = db.session.get(Mesa, int(mesa_id))
            user = db.session.get(User, int(user_id))
            if not mesa:
                raise ValueError("Mesa no encontrada")
            if not user:
                raise ValueError("Usuario no encontrado")
            if mesa.estado == MesaEstadoEnum.OCUPADA:
                raise ValueError("Mesa ocupada")

            pedido = Pedido(mesa_id=int(mesa_id), user_id=int(user_id), estado=PedidoEstadoEnum.ABIERTO, total=0.0)
            mesa.estado = MesaEstadoEnum.OCUPADA
            db.session.add(pedido)
    except ValueError as exc:
        db.session.rollback()
        return error_response(str(exc), 404 if "no encontrada" in str(exc) or "no encontrado" in str(exc) else 400)

    return jsonify({"id": pedido.id, "mesa_id": pedido.mesa_id, "user_id": pedido.user_id, "estado": enum_value(pedido.estado), "total": pedido.total}), 201


@pedidos_bp.post("/<int:pedido_id>/items")
@jwt_required()
@roles_required(RoleEnum.ADMIN, RoleEnum.MESERO)
def add_item(pedido_id):
    data = request.get_json() or {}
    platillo_id = data.get("platillo_id")
    cantidad = data.get("cantidad")
    if not platillo_id or cantidad is None:
        return error_response("platillo_id y cantidad son requeridos")

    try:
        with db.session.begin_nested():
            detalle = add_item_to_order(pedido_id=pedido_id, platillo_id=int(platillo_id), cantidad=float(cantidad))
    except OrderError as exc:
        db.session.rollback()
        return error_response(str(exc))

    pedido = db.session.get(Pedido, detalle.pedido_id)
    return jsonify(
        {
            "detalle": {
                "id": detalle.id,
                "pedido_id": detalle.pedido_id,
                "platillo_id": detalle.platillo_id,
                "cantidad": detalle.cantidad,
                "precio_unitario": detalle.precio_unitario,
                "subtotal": detalle.subtotal,
            },
            "pedido_total": pedido.total,
        }
    ), 201


@pedidos_bp.patch("/<int:pedido_id>/items/<int:detalle_id>")
@jwt_required()
@roles_required(RoleEnum.ADMIN, RoleEnum.MESERO)
def update_item(pedido_id, detalle_id):
    data = request.get_json() or {}
    cantidad = data.get("cantidad")
    if cantidad is None:
        return error_response("cantidad es requerida")

    pedido = db.session.get(Pedido, pedido_id)
    if not pedido:
        return error_response("Pedido no encontrado", 404)
    if pedido.estado != PedidoEstadoEnum.ABIERTO:
        return error_response("Solo se pueden editar items en pedidos ABIERTO")

    detalle = db.session.get(PedidoDetalle, detalle_id)
    if not detalle or detalle.pedido_id != pedido_id:
        return error_response("Detalle no encontrado", 404)

    try:
        cantidad_val = float(cantidad)
    except (TypeError, ValueError):
        return error_response("cantidad inválida")
    if cantidad_val <= 0:
        return error_response("cantidad debe ser mayor a 0")

    old_subtotal = float(detalle.subtotal)
    detalle.cantidad = cantidad_val
    detalle.subtotal = float(detalle.precio_unitario) * cantidad_val
    pedido.total = float(pedido.total) - old_subtotal + float(detalle.subtotal)
    db.session.commit()

    return jsonify(
        {
            "detalle": {
                "id": detalle.id,
                "pedido_id": detalle.pedido_id,
                "platillo_id": detalle.platillo_id,
                "cantidad": detalle.cantidad,
                "precio_unitario": detalle.precio_unitario,
                "subtotal": detalle.subtotal,
            },
            "pedido_total": pedido.total,
        }
    )


@pedidos_bp.delete("/<int:pedido_id>/items/<int:detalle_id>")
@jwt_required()
@roles_required(RoleEnum.ADMIN, RoleEnum.MESERO)
def delete_item(pedido_id, detalle_id):
    pedido = db.session.get(Pedido, pedido_id)
    if not pedido:
        return error_response("Pedido no encontrado", 404)
    if pedido.estado != PedidoEstadoEnum.ABIERTO:
        return error_response("Solo se pueden eliminar items en pedidos ABIERTO")

    detalle = db.session.get(PedidoDetalle, detalle_id)
    if not detalle or detalle.pedido_id != pedido_id:
        return error_response("Detalle no encontrado", 404)

    pedido.total = max(0.0, float(pedido.total) - float(detalle.subtotal))
    db.session.delete(detalle)
    db.session.commit()

    return jsonify({"pedido_id": pedido.id, "pedido_total": pedido.total})


@pedidos_bp.patch("/<int:pedido_id>/estado")
@jwt_required()
@roles_required(RoleEnum.ADMIN, RoleEnum.MESERO, RoleEnum.COCINA)
def update_estado(pedido_id):
    data = request.get_json() or {}
    estado_raw = data.get("estado")

    pedido = db.session.get(Pedido, pedido_id)
    if not pedido:
        return error_response("Pedido no encontrado", 404)

    try:
        nuevo_estado = parse_enum(PedidoEstadoEnum, estado_raw, "estado")
    except ValueError as exc:
        return error_response(str(exc))

    if pedido.estado in (PedidoEstadoEnum.CANCELADO, PedidoEstadoEnum.COBRADO):
        return error_response("No se puede cambiar estado de un pedido finalizado")

    if nuevo_estado == PedidoEstadoEnum.COBRADO:
        return error_response("Para COBRADO usa /caja/cobro")

    role = get_jwt().get("role")
    if role == RoleEnum.MESERO.value and nuevo_estado not in (PedidoEstadoEnum.PREPARACION, PedidoEstadoEnum.CANCELADO):
        return error_response("MESERO solo puede enviar a PREPARACION o CANCELAR", 403)
    if role == RoleEnum.COCINA.value and nuevo_estado != PedidoEstadoEnum.SERVIDO:
        return error_response("COCINA solo puede marcar SERVIDO", 403)

    allowed_transitions = {
        PedidoEstadoEnum.ABIERTO: {PedidoEstadoEnum.PREPARACION, PedidoEstadoEnum.CANCELADO},
        PedidoEstadoEnum.PREPARACION: {PedidoEstadoEnum.SERVIDO, PedidoEstadoEnum.CANCELADO},
        PedidoEstadoEnum.SERVIDO: {PedidoEstadoEnum.CANCELADO},
    }
    if nuevo_estado not in allowed_transitions.get(pedido.estado, set()):
        return error_response(f"Transición inválida de {pedido.estado.value} a {nuevo_estado.value}", 400)

    pedido.estado = nuevo_estado
    db.session.commit()

    if nuevo_estado == PedidoEstadoEnum.CANCELADO:
        mesa = db.session.get(Mesa, pedido.mesa_id)
        if mesa:
            mesa.estado = MesaEstadoEnum.LIBRE
            db.session.commit()

    return jsonify({"id": pedido.id, "estado": enum_value(pedido.estado)})
