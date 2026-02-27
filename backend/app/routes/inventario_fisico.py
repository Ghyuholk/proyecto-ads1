from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app.auth_utils import roles_required
from app.extensions import db
from app.models import (
    InventarioFisico,
    InventarioFisicoDet,
    InventarioFisicoEstadoEnum,
    InventarioFisicoTipoEnum,
    MovimientoTipoEnum,
    Producto,
    RoleEnum,
)
from app.routes.utils import enum_value, error_response, parse_enum
from app.services.inventory_service import InventoryError, register_output, register_positive_adjustment


inventario_fisico_bp = Blueprint("inventario_fisico", __name__, url_prefix="/inventarios-fisicos")


@inventario_fisico_bp.get("")
@jwt_required()
@roles_required(RoleEnum.ADMIN)
def list_inventarios_fisicos():
    query = db.session.query(InventarioFisico)

    estado = request.args.get("estado")
    if estado:
        try:
            estado_enum = parse_enum(InventarioFisicoEstadoEnum, estado, "estado")
            query = query.filter(InventarioFisico.estado == estado_enum)
        except ValueError as exc:
            return error_response(str(exc))

    tipo = request.args.get("tipo")
    if tipo:
        try:
            tipo_enum = parse_enum(InventarioFisicoTipoEnum, tipo, "tipo")
            query = query.filter(InventarioFisico.tipo == tipo_enum)
        except ValueError as exc:
            return error_response(str(exc))

    date_from = request.args.get("date_from")
    if date_from:
        try:
            query = query.filter(InventarioFisico.fecha >= datetime.fromisoformat(date_from))
        except ValueError:
            return error_response("date_from inválido, usa YYYY-MM-DD")

    date_to = request.args.get("date_to")
    if date_to:
        try:
            query = query.filter(InventarioFisico.fecha <= datetime.fromisoformat(date_to + "T23:59:59"))
        except ValueError:
            return error_response("date_to inválido, usa YYYY-MM-DD")

    inventarios = query.order_by(InventarioFisico.fecha.desc(), InventarioFisico.id.desc()).all()
    return jsonify(
        [
            {
                "id": inv.id,
                "tipo": enum_value(inv.tipo),
                "fecha": inv.fecha.isoformat(),
                "estado": enum_value(inv.estado),
                "detalles": [
                    {
                        "id": d.id,
                        "producto_id": d.producto_id,
                        "conteo": d.conteo,
                        "stock_sistema": d.stock_sistema,
                        "diferencia": d.diferencia,
                    }
                    for d in inv.detalles
                ],
            }
            for inv in inventarios
        ]
    )


@inventario_fisico_bp.post("")
@jwt_required()
@roles_required(RoleEnum.ADMIN)
def create_inventario_fisico():
    data = request.get_json() or {}
    tipo_raw = data.get("tipo")
    fecha_raw = data.get("fecha")
    detalles = data.get("detalles", [])

    if not tipo_raw:
        return error_response("tipo es requerido")
    if not isinstance(detalles, list) or not detalles:
        return error_response("detalles debe ser una lista no vacía")

    try:
        tipo = parse_enum(InventarioFisicoTipoEnum, tipo_raw, "tipo")
    except ValueError as exc:
        return error_response(str(exc))

    try:
        fecha = datetime.fromisoformat(fecha_raw) if fecha_raw else datetime.utcnow()
        with db.session.begin_nested():
            inventario = InventarioFisico(tipo=tipo, fecha=fecha, estado=InventarioFisicoEstadoEnum.BORRADOR)
            db.session.add(inventario)
            db.session.flush()

            for item in detalles:
                producto_id = item.get("producto_id")
                conteo = item.get("conteo")
                if not producto_id or conteo is None:
                    raise ValueError("producto_id y conteo son requeridos")

                producto = db.session.get(Producto, int(producto_id))
                if not producto:
                    raise ValueError(f"Producto {producto_id} no encontrado")

                stock_sistema = float(producto.stock_actual)
                conteo_val = float(conteo)
                diferencia = conteo_val - stock_sistema

                det = InventarioFisicoDet(
                    inventario_fisico_id=inventario.id,
                    producto_id=int(producto_id),
                    conteo=conteo_val,
                    stock_sistema=stock_sistema,
                    diferencia=diferencia,
                )
                db.session.add(det)
    except ValueError as exc:
        db.session.rollback()
        return error_response(str(exc), 404 if "no encontrado" in str(exc) else 400)

    return jsonify({"id": inventario.id, "tipo": enum_value(inventario.tipo), "estado": enum_value(inventario.estado)}), 201


@inventario_fisico_bp.post("/<int:inventario_id>/aplicar")
@jwt_required()
@roles_required(RoleEnum.ADMIN)
def apply_inventario_fisico(inventario_id):
    try:
        with db.session.begin_nested():
            inventario = db.session.get(InventarioFisico, inventario_id)
            if not inventario:
                raise ValueError("Inventario físico no encontrado")
            if inventario.estado == InventarioFisicoEstadoEnum.APLICADO:
                raise ValueError("Inventario físico ya aplicado")

            detalles = db.session.query(InventarioFisicoDet).filter(InventarioFisicoDet.inventario_fisico_id == inventario_id).all()
            for det in detalles:
                diferencia = float(det.diferencia)
                if diferencia > 0:
                    register_positive_adjustment(
                        producto_id=det.producto_id,
                        cantidad=diferencia,
                        referencia_tipo="INVENTARIO_FISICO",
                        referencia_id=inventario_id,
                    )
                elif diferencia < 0:
                    register_output(
                        producto_id=det.producto_id,
                        cantidad=abs(diferencia),
                        tipo=MovimientoTipoEnum.AJUSTE_NEG,
                        referencia_tipo="INVENTARIO_FISICO",
                        referencia_id=inventario_id,
                    )
            inventario.estado = InventarioFisicoEstadoEnum.APLICADO
    except ValueError as exc:
        db.session.rollback()
        return error_response(str(exc), 404 if "no encontrado" in str(exc) else 400)
    except InventoryError as exc:
        db.session.rollback()
        return error_response(str(exc))

    return jsonify({"id": inventario.id, "estado": enum_value(inventario.estado)})
