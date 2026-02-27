from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app.auth_utils import roles_required
from app.extensions import db
from app.models import MovimientoInventario, Producto, RoleEnum
from app.routes.utils import enum_value, error_response
from app.services.inventory_service import InventoryError, register_purchase


inventario_bp = Blueprint("inventario", __name__)

ALLOWED_UNITS = {
    "kg": "kg",
    "kilo": "kg",
    "kilos": "kg",
    "g": "g",
    "lt": "lt",
    "l": "lt",
    "litro": "lt",
    "litros": "lt",
    "ml": "ml",
    "unidad": "unidad",
    "u": "unidad",
}


def normalize_unit(raw_value):
    if raw_value is None:
        return None

    unit = str(raw_value).strip().lower()
    normalized = ALLOWED_UNITS.get(unit)
    if not normalized:
        return None
    return normalized


@inventario_bp.get("/productos")
@jwt_required()
@roles_required(RoleEnum.ADMIN, RoleEnum.CAJERO, RoleEnum.COCINA)
def list_productos():
    productos = db.session.query(Producto).order_by(Producto.nombre.asc()).all()
    return jsonify(
        [
            {
                "id": p.id,
                "nombre": p.nombre,
                "unidad": p.unidad,
                "stock_actual": p.stock_actual,
                "costo_promedio": p.costo_promedio,
                "activo": p.activo,
            }
            for p in productos
        ]
    )


@inventario_bp.post("/productos")
@jwt_required()
@roles_required(RoleEnum.ADMIN)
def create_producto():
    data = request.get_json() or {}
    nombre = data.get("nombre")
    unidad = normalize_unit(data.get("unidad"))

    if not nombre or not unidad:
        return error_response("nombre y unidad son requeridos (unidad: kg, g, lt, ml, unidad)")

    stock_inicial = float(data.get("stock_actual", 0.0))
    costo_inicial = float(data.get("costo_promedio", 0.0))
    if stock_inicial < 0:
        return error_response("stock_actual no puede ser negativo")
    if stock_inicial > 0 and costo_inicial < 0:
        return error_response("costo_promedio no puede ser negativo")

    try:
        with db.session.begin_nested():
            producto = Producto(
                nombre=nombre,
                unidad=unidad,
                stock_actual=0.0,
                costo_promedio=0.0,
                activo=bool(data.get("activo", True)),
            )
            db.session.add(producto)
            db.session.flush()

            if stock_inicial > 0:
                register_purchase(
                    producto_id=producto.id,
                    cantidad=stock_inicial,
                    costo_compra=costo_inicial,
                    referencia_tipo="PRODUCTO_INICIAL",
                    referencia_id=producto.id,
                )
    except InventoryError as exc:
        db.session.rollback()
        return error_response(str(exc))

    return jsonify({"id": producto.id, "nombre": producto.nombre, "stock_actual": producto.stock_actual}), 201


@inventario_bp.patch("/productos/<int:producto_id>")
@jwt_required()
@roles_required(RoleEnum.ADMIN)
def update_producto(producto_id):
    producto = db.session.get(Producto, producto_id)
    if not producto:
        return error_response("Producto no encontrado", 404)

    data = request.get_json() or {}
    if "nombre" in data:
        producto.nombre = data["nombre"]
    if "unidad" in data:
        unidad = normalize_unit(data["unidad"])
        if not unidad:
            return error_response("unidad inválida (permitidas: kg, g, lt, ml, unidad)")
        producto.unidad = unidad
    if "activo" in data:
        producto.activo = bool(data["activo"])

    db.session.commit()
    return jsonify(
        {
            "id": producto.id,
            "nombre": producto.nombre,
            "unidad": producto.unidad,
            "stock_actual": producto.stock_actual,
            "costo_promedio": producto.costo_promedio,
            "activo": producto.activo,
        }
    )


@inventario_bp.get("/kardex/<int:producto_id>")
@jwt_required()
@roles_required(RoleEnum.ADMIN, RoleEnum.CAJERO, RoleEnum.COCINA)
def get_kardex(producto_id):
    producto = db.session.get(Producto, producto_id)
    if not producto:
        return error_response("Producto no encontrado", 404)

    movimientos = (
        db.session.query(MovimientoInventario)
        .filter(MovimientoInventario.producto_id == producto_id)
        .order_by(MovimientoInventario.created_at.asc(), MovimientoInventario.id.asc())
        .all()
    )

    return jsonify(
        {
            "producto": {
                "id": producto.id,
                "nombre": producto.nombre,
                "stock_actual": producto.stock_actual,
                "costo_promedio": producto.costo_promedio,
            },
            "movimientos": [
                {
                    "id": m.id,
                    "tipo": enum_value(m.tipo),
                    "referencia_tipo": m.referencia_tipo,
                    "referencia_id": m.referencia_id,
                    "cantidad": m.cantidad,
                    "costo_unitario": m.costo_unitario,
                    "saldo_cantidad": m.saldo_cantidad,
                    "costo_promedio_resultante": m.costo_promedio_resultante,
                    "created_at": m.created_at.isoformat(),
                }
                for m in movimientos
            ],
        }
    )
