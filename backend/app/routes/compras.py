from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app.auth_utils import roles_required
from app.extensions import db
from app.models import Compra, DetalleCompra, RoleEnum
from app.routes.utils import error_response
from app.services.inventory_service import InventoryError, register_purchase


compras_bp = Blueprint("compras", __name__, url_prefix="/compras")


@compras_bp.get("")
@jwt_required()
@roles_required(RoleEnum.ADMIN)
def list_compras():
    query = db.session.query(Compra)

    proveedor = request.args.get("proveedor")
    if proveedor:
        query = query.filter(Compra.proveedor.ilike(f"%{proveedor.strip()}%"))

    date_from = request.args.get("date_from")
    if date_from:
        try:
            query = query.filter(Compra.fecha >= datetime.fromisoformat(date_from))
        except ValueError:
            return error_response("date_from inválido, usa YYYY-MM-DD")

    date_to = request.args.get("date_to")
    if date_to:
        try:
            query = query.filter(Compra.fecha <= datetime.fromisoformat(date_to + "T23:59:59"))
        except ValueError:
            return error_response("date_to inválido, usa YYYY-MM-DD")

    compras = query.order_by(Compra.fecha.desc(), Compra.id.desc()).all()
    return jsonify(
        [
            {
                "id": c.id,
                "proveedor": c.proveedor,
                "fecha": c.fecha.isoformat(),
                "total": c.total,
                "detalles": [
                    {
                        "id": d.id,
                        "producto_id": d.producto_id,
                        "cantidad": d.cantidad,
                        "costo_unitario": d.costo_unitario,
                        "subtotal": d.subtotal,
                    }
                    for d in c.detalles
                ],
            }
            for c in compras
        ]
    )


@compras_bp.post("")
@jwt_required()
@roles_required(RoleEnum.ADMIN)
def create_compra():
    data = request.get_json() or {}
    proveedor = data.get("proveedor")
    fecha_raw = data.get("fecha")
    detalles = data.get("detalles", [])

    if not proveedor or not isinstance(detalles, list) or not detalles:
        return error_response("proveedor y detalles son requeridos")

    try:
        fecha = datetime.fromisoformat(fecha_raw) if fecha_raw else datetime.utcnow()
        with db.session.begin_nested():
            compra = Compra(proveedor=proveedor, fecha=fecha, total=0.0)
            db.session.add(compra)
            db.session.flush()

            total = 0.0
            for item in detalles:
                producto_id = item.get("producto_id")
                cantidad = float(item.get("cantidad", 0))
                costo_unitario = float(item.get("costo_unitario", 0))

                if not producto_id or cantidad <= 0 or costo_unitario < 0:
                    raise ValueError("Detalle de compra inválido")

                subtotal = cantidad * costo_unitario
                det = DetalleCompra(
                    compra_id=compra.id,
                    producto_id=int(producto_id),
                    cantidad=cantidad,
                    costo_unitario=costo_unitario,
                    subtotal=subtotal,
                )
                db.session.add(det)

                register_purchase(
                    producto_id=int(producto_id),
                    cantidad=cantidad,
                    costo_compra=costo_unitario,
                    referencia_tipo="COMPRA",
                    referencia_id=compra.id,
                )
                total += subtotal

            compra.total = total
    except (ValueError, InventoryError) as exc:
        db.session.rollback()
        return error_response(str(exc))

    return jsonify({"id": compra.id, "proveedor": compra.proveedor, "fecha": compra.fecha.isoformat(), "total": compra.total}), 201
