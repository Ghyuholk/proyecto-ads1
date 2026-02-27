from app.extensions import db
from app.models import MovimientoInventario, MovimientoTipoEnum, Producto


class InventoryError(ValueError):
    pass


def _round(value):
    return round(float(value), 6)


def create_movement(producto, tipo, referencia_tipo, referencia_id, cantidad, costo_unitario, saldo, costo_promedio):
    movimiento = MovimientoInventario(
        producto_id=producto.id,
        tipo=tipo,
        referencia_tipo=referencia_tipo,
        referencia_id=referencia_id,
        cantidad=_round(cantidad),
        costo_unitario=_round(costo_unitario),
        saldo_cantidad=_round(saldo),
        costo_promedio_resultante=_round(costo_promedio),
    )
    db.session.add(movimiento)


def register_purchase(producto_id, cantidad, costo_compra, referencia_tipo, referencia_id):
    if cantidad <= 0 or costo_compra < 0:
        raise InventoryError("Cantidad y costo de compra inválidos")

    producto = db.session.get(Producto, producto_id)
    if not producto or not producto.activo:
        raise InventoryError("Producto no encontrado o inactivo")

    stock_actual = float(producto.stock_actual)
    costo_promedio_actual = float(producto.costo_promedio)

    nuevo_stock = stock_actual + float(cantidad)
    nuevo_promedio = ((stock_actual * costo_promedio_actual) + (float(cantidad) * float(costo_compra))) / nuevo_stock

    producto.stock_actual = _round(nuevo_stock)
    producto.costo_promedio = _round(nuevo_promedio)

    create_movement(
        producto=producto,
        tipo=MovimientoTipoEnum.COMPRA,
        referencia_tipo=referencia_tipo,
        referencia_id=referencia_id,
        cantidad=cantidad,
        costo_unitario=costo_compra,
        saldo=nuevo_stock,
        costo_promedio=nuevo_promedio,
    )

    return producto


def register_output(producto_id, cantidad, tipo, referencia_tipo, referencia_id):
    if cantidad <= 0:
        raise InventoryError("Cantidad inválida")
    if tipo not in (MovimientoTipoEnum.VENTA, MovimientoTipoEnum.MERMA, MovimientoTipoEnum.AJUSTE_NEG):
        raise InventoryError("Tipo de salida inválido")

    producto = db.session.get(Producto, producto_id)
    if not producto or not producto.activo:
        raise InventoryError("Producto no encontrado o inactivo")

    stock_actual = float(producto.stock_actual)
    if stock_actual - float(cantidad) < 0:
        raise InventoryError(f"Stock insuficiente para {producto.nombre}")

    nuevo_stock = stock_actual - float(cantidad)
    costo_unitario = float(producto.costo_promedio)

    producto.stock_actual = _round(nuevo_stock)

    create_movement(
        producto=producto,
        tipo=tipo,
        referencia_tipo=referencia_tipo,
        referencia_id=referencia_id,
        cantidad=-abs(float(cantidad)),
        costo_unitario=costo_unitario,
        saldo=nuevo_stock,
        costo_promedio=producto.costo_promedio,
    )

    return producto


def register_positive_adjustment(producto_id, cantidad, referencia_tipo, referencia_id):
    if cantidad <= 0:
        raise InventoryError("Cantidad inválida")

    producto = db.session.get(Producto, producto_id)
    if not producto or not producto.activo:
        raise InventoryError("Producto no encontrado o inactivo")

    stock_actual = float(producto.stock_actual)
    nuevo_stock = stock_actual + float(cantidad)
    costo_unitario = float(producto.costo_promedio)

    producto.stock_actual = _round(nuevo_stock)

    create_movement(
        producto=producto,
        tipo=MovimientoTipoEnum.AJUSTE_POS,
        referencia_tipo=referencia_tipo,
        referencia_id=referencia_id,
        cantidad=abs(float(cantidad)),
        costo_unitario=costo_unitario,
        saldo=nuevo_stock,
        costo_promedio=producto.costo_promedio,
    )

    return producto


def assert_stock_matches_last_movement(producto_id):
    producto = db.session.get(Producto, producto_id)
    if not producto:
        raise InventoryError("Producto no existe")

    ultimo = (
        db.session.query(MovimientoInventario)
        .filter(MovimientoInventario.producto_id == producto_id)
        .order_by(MovimientoInventario.created_at.desc(), MovimientoInventario.id.desc())
        .first()
    )

    if not ultimo:
        return True

    if _round(producto.stock_actual) != _round(ultimo.saldo_cantidad):
        raise InventoryError("Inconsistencia entre stock actual y último movimiento")
    return True
