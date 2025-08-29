from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, ForeignKey
from src.utils.utils import db

class UsuarioModelo(db.Model):
    __tablename__ = "user"

    id_user: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(45), nullable=False)
    username: Mapped[str] = mapped_column(String(45), nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)  # texto plano en pruebas
    role_id_role: Mapped[int] = mapped_column(ForeignKey("role.id_role"), nullable=False)

    rol = relationship("RolModelo", back_populates="usuarios")
