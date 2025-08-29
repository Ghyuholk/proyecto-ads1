import os
from functools import wraps
from urllib.parse import urlparse
from flask import Flask, render_template, request, redirect, url_for, session, g, flash
from src.utils.utils import db
from src.models.usuario_modelo import UsuarioModelo
from src.models.rol_modelo import RolModelo
from src.logic.usuario_logic import UsuarioLogic

def create_app():
    app = Flask(__name__)

    
    app.config["SQLALCHEMY_DATABASE_URI"] = 'mysql://root:root@127.0.0.1:3307/garrobito'
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev")  

    db.init_app(app)

    @app.before_request
    def cargar_usuario():
        uid = session.get("user_id")
        g.user = UsuarioModelo.query.get(uid) if uid else None

    def login_required_view(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not g.user:
                nxt = request.path if request.method == "GET" else None
                return redirect(url_for("login", next=nxt))
            return fn(*args, **kwargs)
        return wrapper

    def role_required(*roles):
        def deco(fn):
            @wraps(fn)
            def wrapper(*args, **kwargs):
                if not g.user:
                    nxt = request.path if request.method == "GET" else None
                    return redirect(url_for("login", next=nxt))
                if g.user.rol.name not in roles:  # importante: g.user.rol.name
                    flash("No tienes permiso para esta sección.", "warning")
                    return redirect(url_for("login"))
                return fn(*args, **kwargs)
            return wrapper
        return deco

   
    @app.get("/login")
    def login():
        return render_template("login.html")

    @app.post("/login")
    def login_post():
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = UsuarioLogic.obtener_por_username_y_password(username, password)
        if not user:
            flash("Credenciales inválidas", "danger")
            return redirect(url_for("login"))

         
        session["user_id"] = user.id_user

       
        nxt = request.args.get("next")
        if nxt:
            parts = urlparse(nxt)
            if not parts.netloc and nxt.startswith("/"):
                return redirect(nxt)
 
        destino = {
            "admin": "admin_dashboard",
            "cocinero": "cocinero_home",
            "mesero": "mesero_home",
        }.get(user.rol.name, "login")
        return redirect(url_for(destino))

    @app.get("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    def index():
        if not g.user:
            return redirect(url_for("login"))
        ruta = {
            "admin": "admin_dashboard",
            "cocinero": "cocinero_home",
            "mesero": "mesero_home",
        }.get(g.user.rol.name, "login")
        return redirect(url_for(ruta))

    #protegr rutas
    @app.get("/admin/dashboard")
    @login_required_view
    @role_required("admin")
    def admin_dashboard():
        total_usuarios = db.session.query(UsuarioModelo).count()
        total_roles = db.session.query(RolModelo).count()
        admins = db.session.query(UsuarioModelo).join(RolModelo).filter(RolModelo.name == "admin").count()
        cocineros = db.session.query(UsuarioModelo).join(RolModelo).filter(RolModelo.name == "cocinero").count()
        meseros = db.session.query(UsuarioModelo).join(RolModelo).filter(RolModelo.name == "mesero").count()
        datos = dict(usuarios=total_usuarios, roles=total_roles,
                     admins=admins, cocineros=cocineros, meseros=meseros)
        return render_template("admin/dashboard.html", datos=datos)

    @app.get("/cocinero/home")
    @login_required_view
    @role_required("cocinero")
    def cocinero_home():
        return render_template("cocinero/home.html")

    @app.get("/mesero/home")
    @login_required_view
    @role_required("mesero")
    def mesero_home():
        return render_template("mesero/home.html")

    return app
