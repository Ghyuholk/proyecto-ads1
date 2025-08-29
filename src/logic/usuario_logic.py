from typing import Optional
from src.utils.utils import db
from src.models.usuario_modelo import UsuarioModelo

class UsuarioLogic:
    @staticmethod
    def obtener_por_username_y_password(username: str, password: str) -> Optional[UsuarioModelo]:
        
        return UsuarioModelo.query.filter_by(username=username, password=password).first()

    @staticmethod
    def contar_todos() -> int:
        return db.session.query(UsuarioModelo).count()
