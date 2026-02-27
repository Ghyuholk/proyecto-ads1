from datetime import datetime
from enum import Enum

from app.extensions import db


class RoleEnum(str, Enum):
    ADMIN = "ADMIN"
    CAJERO = "CAJERO"
    MESERO = "MESERO"
    COCINA = "COCINA"


class MesaEstadoEnum(str, Enum):
    LIBRE = "LIBRE"
    OCUPADA = "OCUPADA"


class PedidoEstadoEnum(str, Enum):
    ABIERTO = "ABIERTO"
    PREPARACION = "PREPARACION"
    SERVIDO = "SERVIDO"
    COBRADO = "COBRADO"
    CANCELADO = "CANCELADO"


class MovimientoTipoEnum(str, Enum):
    COMPRA = "COMPRA"
    VENTA = "VENTA"
    MERMA = "MERMA"
    AJUSTE_POS = "AJUSTE_POS"
    AJUSTE_NEG = "AJUSTE_NEG"


class InventarioFisicoTipoEnum(str, Enum):
    INICIAL = "INICIAL"
    MENSUAL = "MENSUAL"
    ANUAL = "ANUAL"


class InventarioFisicoEstadoEnum(str, Enum):
    BORRADOR = "BORRADOR"
    APLICADO = "APLICADO"


class CajaEstadoEnum(str, Enum):
    ABIERTA = "ABIERTA"
    CERRADA = "CERRADA"


class CobroMetodoEnum(str, Enum):
    EFECTIVO = "EFECTIVO"
    TARJETA = "TARJETA"
    TRANSFERENCIA = "TRANSFERENCIA"


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class User(db.Model, TimestampMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum(RoleEnum), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)


class Mesa(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.Integer, unique=True, nullable=False)
    estado = db.Column(db.Enum(MesaEstadoEnum), default=MesaEstadoEnum.LIBRE, nullable=False)


class Pedido(db.Model, TimestampMixin):
    id = db.Column(db.Integer, primary_key=True)
    mesa_id = db.Column(db.Integer, db.ForeignKey("mesa.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    estado = db.Column(db.Enum(PedidoEstadoEnum), default=PedidoEstadoEnum.ABIERTO, nullable=False)
    total = db.Column(db.Float, default=0.0, nullable=False)

    mesa = db.relationship("Mesa")
    user = db.relationship("User")
    detalles = db.relationship("PedidoDetalle", back_populates="pedido", cascade="all, delete-orphan")


class PedidoDetalle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey("pedido.id"), nullable=False)
    platillo_id = db.Column(db.Integer, db.ForeignKey("platillo.id"), nullable=False)
    cantidad = db.Column(db.Float, nullable=False)
    precio_unitario = db.Column(db.Float, nullable=False)
    subtotal = db.Column(db.Float, nullable=False)

    pedido = db.relationship("Pedido", back_populates="detalles")
    platillo = db.relationship("Platillo")


class Platillo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), unique=True, nullable=False)
    precio = db.Column(db.Float, nullable=False)
    activo = db.Column(db.Boolean, default=True, nullable=False)

    ingredientes = db.relationship("PlatilloIngrediente", back_populates="platillo", cascade="all, delete-orphan")


class PlatilloIngrediente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    platillo_id = db.Column(db.Integer, db.ForeignKey("platillo.id"), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey("producto.id"), nullable=False)
    cantidad_por_unidad = db.Column(db.Float, nullable=False)

    platillo = db.relationship("Platillo", back_populates="ingredientes")
    producto = db.relationship("Producto")


class Producto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), unique=True, nullable=False)
    unidad = db.Column(db.String(32), nullable=False)
    stock_actual = db.Column(db.Float, default=0.0, nullable=False)
    costo_promedio = db.Column(db.Float, default=0.0, nullable=False)
    activo = db.Column(db.Boolean, default=True, nullable=False)


class MovimientoInventario(db.Model, TimestampMixin):
    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey("producto.id"), nullable=False)
    tipo = db.Column(db.Enum(MovimientoTipoEnum), nullable=False)
    referencia_tipo = db.Column(db.String(50), nullable=False)
    referencia_id = db.Column(db.Integer, nullable=False)
    cantidad = db.Column(db.Float, nullable=False)
    costo_unitario = db.Column(db.Float, nullable=False)
    saldo_cantidad = db.Column(db.Float, nullable=False)
    costo_promedio_resultante = db.Column(db.Float, nullable=False)

    producto = db.relationship("Producto")


class Compra(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    proveedor = db.Column(db.String(120), nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    total = db.Column(db.Float, default=0.0, nullable=False)

    detalles = db.relationship("DetalleCompra", back_populates="compra", cascade="all, delete-orphan")


class DetalleCompra(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    compra_id = db.Column(db.Integer, db.ForeignKey("compra.id"), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey("producto.id"), nullable=False)
    cantidad = db.Column(db.Float, nullable=False)
    costo_unitario = db.Column(db.Float, nullable=False)
    subtotal = db.Column(db.Float, nullable=False)

    compra = db.relationship("Compra", back_populates="detalles")
    producto = db.relationship("Producto")


class InventarioFisico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.Enum(InventarioFisicoTipoEnum), nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    estado = db.Column(
        db.Enum(InventarioFisicoEstadoEnum),
        default=InventarioFisicoEstadoEnum.BORRADOR,
        nullable=False,
    )

    detalles = db.relationship("InventarioFisicoDet", back_populates="inventario_fisico", cascade="all, delete-orphan")


class InventarioFisicoDet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    inventario_fisico_id = db.Column(db.Integer, db.ForeignKey("inventario_fisico.id"), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey("producto.id"), nullable=False)
    conteo = db.Column(db.Float, nullable=False)
    stock_sistema = db.Column(db.Float, nullable=False)
    diferencia = db.Column(db.Float, nullable=False)

    inventario_fisico = db.relationship("InventarioFisico", back_populates="detalles")
    producto = db.relationship("Producto")


class AperturaCaja(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    monto_inicial = db.Column(db.Float, nullable=False)
    opened_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    estado = db.Column(db.Enum(CajaEstadoEnum), default=CajaEstadoEnum.ABIERTA, nullable=False)

    user = db.relationship("User")


class Cobro(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey("pedido.id"), nullable=False, unique=True)
    apertura_caja_id = db.Column(db.Integer, db.ForeignKey("apertura_caja.id"), nullable=False)
    metodo = db.Column(db.Enum(CobroMetodoEnum), nullable=False)
    monto = db.Column(db.Float, nullable=False)
    paid_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    pedido = db.relationship("Pedido")
    apertura_caja = db.relationship("AperturaCaja")


class CierreCaja(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    apertura_caja_id = db.Column(db.Integer, db.ForeignKey("apertura_caja.id"), nullable=False, unique=True)
    total_ventas = db.Column(db.Float, nullable=False)
    total_efectivo = db.Column(db.Float, nullable=False)
    total_tarjeta = db.Column(db.Float, nullable=False)
    total_transferencia = db.Column(db.Float, nullable=False)
    closed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    apertura_caja = db.relationship("AperturaCaja")
