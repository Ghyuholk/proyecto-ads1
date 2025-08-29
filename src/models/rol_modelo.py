from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, String
from src.utils.utils import db

class RolModelo(db.Model):
    __tablename__ = "role"

    id_role: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(45), nullable=False)

    usuarios = relationship("UsuarioModelo", back_populates="rol")
