from app import create_app
from app.extensions import db
from app.seed_data import seed_initial_data


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        try:
            with db.session.begin():
                db.create_all()
                summary = seed_initial_data()
            print("Seed ejecutado correctamente")
            print(summary)
            print("Usuarios de prueba: admin/admin123, cajero/cajero123, mesero/mesero123, cocina/cocina123")
        except Exception as exc:
            db.session.rollback()
            print(f"Error ejecutando seed: {exc}")
            raise
