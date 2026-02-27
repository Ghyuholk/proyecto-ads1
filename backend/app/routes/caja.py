from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app.auth_utils import roles_required
from app.extensions import db
from app.models import CierreCaja, Cobro, CobroMetodoEnum, RoleEnum
from app.routes.utils import enum_value, error_response, parse_enum
from app.services.cash_service import CashError, close_cashbox, get_open_cashbox, open_cashbox, register_payment


caja_bp = Blueprint("caja", __name__, url_prefix="/caja")


@caja_bp.get("/estado")
@jwt_required()
@roles_required(RoleEnum.ADMIN, RoleEnum.CAJERO)
def estado_caja():
    apertura = get_open_cashbox()
    if not apertura:
        return jsonify({"abierta": False, "apertura": None})

    total_cobros = db.session.query(db.func.coalesce(db.func.sum(Cobro.monto), 0.0)).filter(Cobro.apertura_caja_id == apertura.id).scalar()
    cierre = db.session.query(CierreCaja).filter(CierreCaja.apertura_caja_id == apertura.id).first()

    return jsonify(
        {
            "abierta": True,
            "apertura": {
                "id": apertura.id,
                "user_id": apertura.user_id,
                "monto_inicial": apertura.monto_inicial,
                "opened_at": apertura.opened_at.isoformat(),
                "estado": enum_value(apertura.estado),
            },
            "total_cobros": float(total_cobros),
            "cerrada": cierre is not None,
        }
    )


@caja_bp.post("/apertura")
@jwt_required()
@roles_required(RoleEnum.ADMIN, RoleEnum.CAJERO)
def apertura_caja():
    data = request.get_json() or {}
    user_id = data.get("user_id")
    monto_inicial = data.get("monto_inicial")

    if not user_id or monto_inicial is None:
        return error_response("user_id y monto_inicial son requeridos")

    try:
        with db.session.begin_nested():
            apertura = open_cashbox(user_id=int(user_id), monto_inicial=float(monto_inicial))
    except CashError as exc:
        db.session.rollback()
        return error_response(str(exc))

    return jsonify(
        {
            "id": apertura.id,
            "user_id": apertura.user_id,
            "monto_inicial": apertura.monto_inicial,
            "opened_at": apertura.opened_at.isoformat(),
            "estado": enum_value(apertura.estado),
        }
    ), 201


@caja_bp.post("/cobro")
@jwt_required()
@roles_required(RoleEnum.ADMIN, RoleEnum.CAJERO)
def cobro():
    data = request.get_json() or {}
    pedido_id = data.get("pedido_id")
    metodo_raw = data.get("metodo")

    if not pedido_id or not metodo_raw:
        return error_response("pedido_id y metodo son requeridos")

    try:
        metodo = parse_enum(CobroMetodoEnum, metodo_raw, "metodo")
    except ValueError as exc:
        return error_response(str(exc))

    try:
        with db.session.begin_nested():
            cobro_obj = register_payment(pedido_id=int(pedido_id), metodo=metodo)
    except CashError as exc:
        db.session.rollback()
        return error_response(str(exc))

    return jsonify(
        {
            "id": cobro_obj.id,
            "pedido_id": cobro_obj.pedido_id,
            "apertura_caja_id": cobro_obj.apertura_caja_id,
            "metodo": enum_value(cobro_obj.metodo),
            "monto": cobro_obj.monto,
            "paid_at": cobro_obj.paid_at.isoformat(),
        }
    ), 201


@caja_bp.post("/cierre")
@jwt_required()
@roles_required(RoleEnum.ADMIN, RoleEnum.CAJERO)
def cierre():
    data = request.get_json() or {}
    apertura_caja_id = data.get("apertura_caja_id")
    if not apertura_caja_id:
        return error_response("apertura_caja_id es requerido")

    try:
        with db.session.begin_nested():
            cierre_obj = close_cashbox(apertura_id=int(apertura_caja_id))
    except CashError as exc:
        db.session.rollback()
        return error_response(str(exc))

    return jsonify(
        {
            "id": cierre_obj.id,
            "apertura_caja_id": cierre_obj.apertura_caja_id,
            "total_ventas": cierre_obj.total_ventas,
            "total_efectivo": cierre_obj.total_efectivo,
            "total_tarjeta": cierre_obj.total_tarjeta,
            "total_transferencia": cierre_obj.total_transferencia,
            "closed_at": cierre_obj.closed_at.isoformat(),
        }
    ), 201
