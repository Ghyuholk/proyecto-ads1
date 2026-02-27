from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app.auth_utils import roles_required
from app.extensions import db
from app.models import Platillo, PlatilloIngrediente, Producto, RoleEnum
from app.routes.utils import error_response


platillos_bp = Blueprint("platillos", __name__, url_prefix="/platillos")


def _validate_ingredientes_payload(ingredientes):
    if not isinstance(ingredientes, list) or not ingredientes:
        raise ValueError("ingredientes debe ser una lista no vacía")

    parsed = []
    seen = set()
    for item in ingredientes:
        producto_id = item.get("producto_id")
        cantidad_por_unidad = item.get("cantidad_por_unidad")
        if not producto_id or cantidad_por_unidad is None:
            raise ValueError("producto_id y cantidad_por_unidad son requeridos")

        try:
            producto_id_int = int(producto_id)
            cantidad_val = float(cantidad_por_unidad)
        except (TypeError, ValueError) as exc:
            raise ValueError("producto_id y cantidad_por_unidad deben ser numéricos") from exc

        if cantidad_val <= 0:
            raise ValueError("cantidad_por_unidad debe ser mayor a 0")
        if producto_id_int in seen:
            raise ValueError(f"producto_id duplicado en receta: {producto_id_int}")

        producto = db.session.get(Producto, producto_id_int)
        if not producto:
            raise ValueError(f"Producto {producto_id_int} no existe")
        if not producto.activo:
            raise ValueError(f"Producto {producto_id_int} está inactivo")

        parsed.append({"producto_id": producto_id_int, "cantidad_por_unidad": cantidad_val})
        seen.add(producto_id_int)

    return parsed


@platillos_bp.get("")
@jwt_required()
@roles_required(RoleEnum.ADMIN, RoleEnum.CAJERO, RoleEnum.MESERO, RoleEnum.COCINA)
def list_platillos():
    platillos = db.session.query(Platillo).order_by(Platillo.nombre.asc()).all()
    result = []
    for p in platillos:
        result.append(
            {
                "id": p.id,
                "nombre": p.nombre,
                "precio": p.precio,
                "activo": p.activo,
                "ingredientes": [
                    {
                        "id": i.id,
                        "producto_id": i.producto_id,
                        "cantidad_por_unidad": i.cantidad_por_unidad,
                    }
                    for i in p.ingredientes
                ],
            }
        )
    return jsonify(result)


@platillos_bp.post("")
@jwt_required()
@roles_required(RoleEnum.ADMIN, RoleEnum.COCINA)
def create_platillo():
    data = request.get_json() or {}
    nombre = data.get("nombre")
    precio = data.get("precio")
    ingredientes = data.get("ingredientes")

    if not nombre or precio is None:
        return error_response("nombre y precio son requeridos")

    try:
        precio_val = float(precio)
    except (TypeError, ValueError):
        return error_response("precio inválido")
    if precio_val <= 0:
        return error_response("precio debe ser mayor a 0")

    try:
        with db.session.begin_nested():
            platillo = Platillo(nombre=nombre, precio=precio_val, activo=bool(data.get("activo", True)))
            db.session.add(platillo)
            db.session.flush()

            if ingredientes is not None:
                parsed_ingredientes = _validate_ingredientes_payload(ingredientes)
                for item in parsed_ingredientes:
                    db.session.add(
                        PlatilloIngrediente(
                            platillo_id=platillo.id,
                            producto_id=item["producto_id"],
                            cantidad_por_unidad=item["cantidad_por_unidad"],
                        )
                    )
    except ValueError as exc:
        db.session.rollback()
        return error_response(str(exc))

    db.session.commit()
    return jsonify({"id": platillo.id, "nombre": platillo.nombre, "precio": platillo.precio, "activo": platillo.activo}), 201


@platillos_bp.post("/<int:platillo_id>/ingredientes")
@jwt_required()
@roles_required(RoleEnum.ADMIN, RoleEnum.COCINA)
def add_ingredientes(platillo_id):
    data = request.get_json() or {}
    ingredientes = data.get("ingredientes", [])

    platillo = db.session.get(Platillo, platillo_id)
    if not platillo:
        return error_response("Platillo no encontrado", 404)

    try:
        parsed_ingredientes = _validate_ingredientes_payload(ingredientes)
        with db.session.begin_nested():
            db.session.query(PlatilloIngrediente).filter(PlatilloIngrediente.platillo_id == platillo_id).delete()
            created = []
            for item in parsed_ingredientes:
                ing = PlatilloIngrediente(
                    platillo_id=platillo_id,
                    producto_id=item["producto_id"],
                    cantidad_por_unidad=item["cantidad_por_unidad"],
                )
                db.session.add(ing)
                created.append(ing)
    except ValueError as exc:
        db.session.rollback()
        return error_response(str(exc))

    db.session.commit()
    return jsonify(
        {
            "platillo_id": platillo_id,
            "ingredientes": [
                {
                    "id": i.id,
                    "producto_id": i.producto_id,
                    "cantidad_por_unidad": i.cantidad_por_unidad,
                }
                for i in created
            ],
        }
    ), 201


@platillos_bp.patch("/<int:platillo_id>")
@jwt_required()
@roles_required(RoleEnum.ADMIN, RoleEnum.COCINA)
def update_platillo(platillo_id):
    platillo = db.session.get(Platillo, platillo_id)
    if not platillo:
        return error_response("Platillo no encontrado", 404)

    data = request.get_json() or {}
    if "nombre" in data:
        platillo.nombre = data["nombre"]
    if "precio" in data:
        try:
            precio_val = float(data["precio"])
        except (TypeError, ValueError):
            return error_response("precio inválido")
        if precio_val <= 0:
            return error_response("precio debe ser mayor a 0")
        platillo.precio = precio_val
    if "activo" in data:
        platillo.activo = bool(data["activo"])
    if "ingredientes" in data:
        try:
            parsed_ingredientes = _validate_ingredientes_payload(data["ingredientes"])
            with db.session.begin_nested():
                db.session.query(PlatilloIngrediente).filter(PlatilloIngrediente.platillo_id == platillo_id).delete()
                for item in parsed_ingredientes:
                    db.session.add(
                        PlatilloIngrediente(
                            platillo_id=platillo_id,
                            producto_id=item["producto_id"],
                            cantidad_por_unidad=item["cantidad_por_unidad"],
                        )
                    )
        except ValueError as exc:
            db.session.rollback()
            return error_response(str(exc))

    db.session.commit()
    return jsonify({"id": platillo.id, "nombre": platillo.nombre, "precio": platillo.precio, "activo": platillo.activo})
