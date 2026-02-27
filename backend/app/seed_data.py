import os

from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import Mesa, MesaEstadoEnum, MovimientoInventario, Platillo, PlatilloIngrediente, Producto, RoleEnum, User
from app.services.inventory_service import register_purchase


SEED_USERS = [
    ("admin", "admin123", RoleEnum.ADMIN),
    ("cajero", "cajero123", RoleEnum.CAJERO),
    ("mesero", "mesero123", RoleEnum.MESERO),
    ("cocina", "cocina123", RoleEnum.COCINA),
]

SEED_PRODUCTS = [
    {"nombre": "Arroz", "unidad": "kg", "stock": 20, "costo": 2.8},
    {"nombre": "Pollo", "unidad": "kg", "stock": 18, "costo": 5.9},
    {"nombre": "Papa", "unidad": "kg", "stock": 25, "costo": 1.7},
    {"nombre": "Aceite", "unidad": "lt", "stock": 12, "costo": 4.4},
    {"nombre": "Sal", "unidad": "kg", "stock": 5, "costo": 0.9},
]

SEED_PLATILLOS = [
    {
        "nombre": "Pollo con arroz",
        "precio": 18.0,
        "ingredientes": [
            ("Pollo", 0.25),
            ("Arroz", 0.15),
            ("Sal", 0.01),
        ],
    },
    {
        "nombre": "Papas fritas",
        "precio": 8.0,
        "ingredientes": [
            ("Papa", 0.30),
            ("Aceite", 0.05),
            ("Sal", 0.005),
        ],
    },
]


def seed_admin_user(username=None, password=None):
    admin_username = (username or os.getenv("ADMIN_USERNAME") or "admin").strip()
    admin_password = (password or os.getenv("ADMIN_PASSWORD") or "admin123").strip()
    if not admin_username or not admin_password:
        raise ValueError("ADMIN_USERNAME y ADMIN_PASSWORD son requeridos")

    user = db.session.query(User).filter_by(username=admin_username).first()
    if not user:
        user = User(
            username=admin_username,
            password_hash=generate_password_hash(admin_password),
            role=RoleEnum.ADMIN,
            is_active=True,
        )
        db.session.add(user)
        created = 1
    else:
        user.password_hash = generate_password_hash(admin_password)
        user.role = RoleEnum.ADMIN
        user.is_active = True
        created = 0

    db.session.flush()
    return {"admin_user": admin_username, "created": created}


def seed_initial_data():
    created = {"users": 0, "mesas": 0, "productos": 0, "platillos": 0, "ingredientes": 0}

    for username, password, role in SEED_USERS:
        user = db.session.query(User).filter_by(username=username).first()
        if not user:
            user = User(
                username=username,
                password_hash=generate_password_hash(password),
                role=role,
                is_active=True,
            )
            db.session.add(user)
            created["users"] += 1

    for numero in range(1, 7):
        mesa = db.session.query(Mesa).filter_by(numero=numero).first()
        if not mesa:
            db.session.add(Mesa(numero=numero, estado=MesaEstadoEnum.LIBRE))
            created["mesas"] += 1

    db.session.flush()

    for spec in SEED_PRODUCTS:
        producto = db.session.query(Producto).filter_by(nombre=spec["nombre"]).first()
        if not producto:
            producto = Producto(
                nombre=spec["nombre"],
                unidad=spec["unidad"],
                stock_actual=0.0,
                costo_promedio=0.0,
                activo=True,
            )
            db.session.add(producto)
            db.session.flush()

            register_purchase(
                producto_id=producto.id,
                cantidad=float(spec["stock"]),
                costo_compra=float(spec["costo"]),
                referencia_tipo="SEED",
                referencia_id=producto.id,
            )
            created["productos"] += 1

    db.session.flush()

    for plat_spec in SEED_PLATILLOS:
        platillo = db.session.query(Platillo).filter_by(nombre=plat_spec["nombre"]).first()
        if not platillo:
            platillo = Platillo(nombre=plat_spec["nombre"], precio=float(plat_spec["precio"]), activo=True)
            db.session.add(platillo)
            db.session.flush()
            created["platillos"] += 1

        for nombre_producto, cantidad in plat_spec["ingredientes"]:
            producto = db.session.query(Producto).filter_by(nombre=nombre_producto).first()
            if not producto:
                continue

            ingrediente = (
                db.session.query(PlatilloIngrediente)
                .filter_by(platillo_id=platillo.id, producto_id=producto.id)
                .first()
            )
            if not ingrediente:
                db.session.add(
                    PlatilloIngrediente(
                        platillo_id=platillo.id,
                        producto_id=producto.id,
                        cantidad_por_unidad=float(cantidad),
                    )
                )
                created["ingredientes"] += 1

    db.session.flush()

    # Verifica consistencia mínima de kardex para productos seed.
    for spec in SEED_PRODUCTS:
        producto = db.session.query(Producto).filter_by(nombre=spec["nombre"]).first()
        if not producto:
            continue
        mov = (
            db.session.query(MovimientoInventario)
            .filter(MovimientoInventario.producto_id == producto.id)
            .order_by(MovimientoInventario.created_at.desc(), MovimientoInventario.id.desc())
            .first()
        )
        if mov and round(float(producto.stock_actual), 6) != round(float(mov.saldo_cantidad), 6):
            raise ValueError(f"Inconsistencia de stock para producto {producto.nombre}")

    return created
