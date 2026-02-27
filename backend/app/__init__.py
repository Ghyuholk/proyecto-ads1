from flask import Flask
import click

from config import Config
from app.extensions import db, jwt, migrate


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    from app.routes.auth import auth_bp
    from app.routes.mesas import mesas_bp
    from app.routes.platillos import platillos_bp
    from app.routes.pedidos import pedidos_bp
    from app.routes.compras import compras_bp
    from app.routes.inventario import inventario_bp
    from app.routes.inventario_fisico import inventario_fisico_bp
    from app.routes.caja import caja_bp
    from app.routes.protected_examples import protected_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(mesas_bp)
    app.register_blueprint(platillos_bp)
    app.register_blueprint(pedidos_bp)
    app.register_blueprint(compras_bp)
    app.register_blueprint(inventario_bp)
    app.register_blueprint(inventario_fisico_bp)
    app.register_blueprint(caja_bp)
    app.register_blueprint(protected_bp)

    with app.app_context():
        from app import models  # noqa: F401

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "backend"}

    @app.cli.command("seed")
    def seed_command():
        from app.seed_data import seed_initial_data

        with app.app_context():
            with db.session.begin():
                db.create_all()
                summary = seed_initial_data()
        click.echo("Seed ejecutado correctamente")
        click.echo(str(summary))

    @app.cli.command("seed-admin")
    @click.option("--username", default=None, help="Usuario ADMIN a crear/actualizar.")
    @click.option("--password", default=None, help="Password ADMIN a crear/actualizar.")
    def seed_admin_command(username, password):
        from app.seed_data import seed_admin_user

        with app.app_context():
            with db.session.begin():
                db.create_all()
                summary = seed_admin_user(username=username, password=password)
        click.echo("Seed ADMIN ejecutado correctamente")
        click.echo(str(summary))

    return app
