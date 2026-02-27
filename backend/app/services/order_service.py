from app.extensions import db
from app.models import Pedido, PedidoDetalle, PedidoEstadoEnum, Platillo, PlatilloIngrediente, MovimientoTipoEnum
from app.services.inventory_service import InventoryError, register_output


class OrderError(ValueError):
    pass


def add_item_to_order(pedido_id, platillo_id, cantidad):
    if cantidad <= 0:
        raise OrderError("Cantidad inválida")

    pedido = db.session.get(Pedido, pedido_id)
    platillo = db.session.get(Platillo, platillo_id)

    if not pedido:
        raise OrderError("Pedido no encontrado")
    if pedido.estado in (PedidoEstadoEnum.COBRADO, PedidoEstadoEnum.CANCELADO):
        raise OrderError("No se puede modificar un pedido finalizado")
    if not platillo or not platillo.activo:
        raise OrderError("Platillo no encontrado o inactivo")

    subtotal = float(cantidad) * float(platillo.precio)

    detalle = PedidoDetalle(
        pedido_id=pedido.id,
        platillo_id=platillo.id,
        cantidad=float(cantidad),
        precio_unitario=float(platillo.precio),
        subtotal=subtotal,
    )
    db.session.add(detalle)

    pedido.total = float(pedido.total) + subtotal
    return detalle


def _consume_recipe_for_detail(detalle, pedido_id):
    ingredientes = (
        db.session.query(PlatilloIngrediente)
        .filter(PlatilloIngrediente.platillo_id == detalle.platillo_id)
        .all()
    )
    if not ingredientes:
        raise OrderError(f"El platillo ID {detalle.platillo_id} no tiene receta")

    for ingrediente in ingredientes:
        cantidad_salida = float(detalle.cantidad) * float(ingrediente.cantidad_por_unidad)
        register_output(
            producto_id=ingrediente.producto_id,
            cantidad=cantidad_salida,
            tipo=MovimientoTipoEnum.VENTA,
            referencia_tipo="PEDIDO",
            referencia_id=pedido_id,
        )


def consume_inventory_for_order(pedido_id):
    pedido = db.session.get(Pedido, pedido_id)
    if not pedido:
        raise OrderError("Pedido no encontrado")
    if pedido.estado == PedidoEstadoEnum.CANCELADO:
        raise OrderError("Pedido cancelado")

    if not pedido.detalles:
        raise OrderError("Pedido sin detalles")

    if pedido.estado == PedidoEstadoEnum.COBRADO:
        return pedido

    try:
        for detalle in pedido.detalles:
            _consume_recipe_for_detail(detalle, pedido.id)
    except InventoryError as exc:
        raise OrderError(str(exc)) from exc

    pedido.estado = PedidoEstadoEnum.COBRADO
    return pedido
