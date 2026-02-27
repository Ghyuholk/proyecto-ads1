from datetime import datetime

from sqlalchemy import func

from app.extensions import db
from app.models import (
    AperturaCaja,
    CajaEstadoEnum,
    CierreCaja,
    Cobro,
    CobroMetodoEnum,
    MesaEstadoEnum,
    Pedido,
    PedidoEstadoEnum,
)
from app.services.order_service import OrderError, consume_inventory_for_order


class CashError(ValueError):
    pass


def get_open_cashbox():
    return (
        db.session.query(AperturaCaja)
        .filter(AperturaCaja.estado == CajaEstadoEnum.ABIERTA)
        .order_by(AperturaCaja.opened_at.desc())
        .first()
    )


def open_cashbox(user_id, monto_inicial):
    if monto_inicial < 0:
        raise CashError("Monto inicial inválido")
    if get_open_cashbox():
        raise CashError("Ya existe una caja abierta")

    apertura = AperturaCaja(user_id=user_id, monto_inicial=float(monto_inicial))
    db.session.add(apertura)
    return apertura


def register_payment(pedido_id, metodo):
    apertura = get_open_cashbox()
    if not apertura:
        raise CashError("No hay caja abierta")

    pedido = db.session.get(Pedido, pedido_id)
    if not pedido:
        raise CashError("Pedido no encontrado")
    if pedido.estado == PedidoEstadoEnum.CANCELADO:
        raise CashError("Pedido cancelado")
    if pedido.estado != PedidoEstadoEnum.SERVIDO:
        raise CashError("Solo se puede cobrar un pedido SERVIDO")
    if db.session.query(Cobro).filter(Cobro.pedido_id == pedido_id).first():
        raise CashError("El pedido ya fue cobrado")

    if metodo not in (CobroMetodoEnum.EFECTIVO, CobroMetodoEnum.TARJETA, CobroMetodoEnum.TRANSFERENCIA):
        raise CashError("Método de cobro inválido")

    try:
        consume_inventory_for_order(pedido.id)
    except OrderError as exc:
        raise CashError(str(exc)) from exc

    cobro = Cobro(
        pedido_id=pedido.id,
        apertura_caja_id=apertura.id,
        metodo=metodo,
        monto=float(pedido.total),
    )
    if pedido.mesa:
        pedido.mesa.estado = MesaEstadoEnum.LIBRE
    db.session.add(cobro)
    return cobro


def close_cashbox(apertura_id):
    apertura = db.session.get(AperturaCaja, apertura_id)
    if not apertura:
        raise CashError("Apertura no encontrada")
    if apertura.estado != CajaEstadoEnum.ABIERTA:
        raise CashError("La caja ya está cerrada")

    pendientes = (
        db.session.query(Pedido)
        .filter(
            Pedido.created_at >= apertura.opened_at,
            Pedido.estado.notin_([PedidoEstadoEnum.COBRADO, PedidoEstadoEnum.CANCELADO]),
        )
        .count()
    )

    if pendientes > 0:
        raise CashError("No se puede cerrar caja con pedidos no cobrados en el período")

    total_efectivo = (
        db.session.query(func.coalesce(func.sum(Cobro.monto), 0.0))
        .filter(Cobro.apertura_caja_id == apertura.id, Cobro.metodo == CobroMetodoEnum.EFECTIVO)
        .scalar()
    )
    total_tarjeta = (
        db.session.query(func.coalesce(func.sum(Cobro.monto), 0.0))
        .filter(Cobro.apertura_caja_id == apertura.id, Cobro.metodo == CobroMetodoEnum.TARJETA)
        .scalar()
    )
    total_transferencia = (
        db.session.query(func.coalesce(func.sum(Cobro.monto), 0.0))
        .filter(Cobro.apertura_caja_id == apertura.id, Cobro.metodo == CobroMetodoEnum.TRANSFERENCIA)
        .scalar()
    )

    total_ventas = float(total_efectivo) + float(total_tarjeta) + float(total_transferencia)

    cierre = CierreCaja(
        apertura_caja_id=apertura.id,
        total_ventas=float(total_ventas),
        total_efectivo=float(total_efectivo),
        total_tarjeta=float(total_tarjeta),
        total_transferencia=float(total_transferencia),
        closed_at=datetime.utcnow(),
    )
    apertura.estado = CajaEstadoEnum.CERRADA
    db.session.add(cierre)
    return cierre
