import os
from functools import wraps

import requests
from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for


REQUEST_TIMEOUT = 8
ALLOWED_PRODUCT_UNITS = ("kg", "g", "lt", "ml", "unidad")
ROLE_DASHBOARD = {
    "ADMIN": "dashboard_admin",
    "CAJERO": "dashboard_caja",
    "MESERO": "dashboard_mesas",
    "COCINA": "dashboard_cocina",
}


def _api_call(base_url, method, path, payload=None, token=None, params=None):
    url = f"{base_url.rstrip('/')}{path}"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    response = requests.request(method=method, url=url, json=payload, headers=headers, params=params, timeout=REQUEST_TIMEOUT)

    try:
        data = response.json()
    except ValueError:
        data = {"raw": response.text}

    if response.status_code >= 400:
        message = data.get("error") if isinstance(data, dict) else str(data)
        raise ValueError(f"{response.status_code} - {message}")

    return data


def _safe_get(base_url, path, default, token, params=None):
    try:
        return _api_call(base_url, "GET", path, token=token, params=params)
    except Exception:
        return default


def _dashboard_endpoint_for_role(role):
    return ROLE_DASHBOARD.get(role, "login")


def _is_pedido_activo(pedido):
    return pedido.get("estado") not in ("COBRADO", "CANCELADO")


def _is_pedido_cobrable(pedido):
    return pedido.get("estado") == "SERVIDO"


def _extract_ingredientes_from_form(form, prefix):
    ingredientes = []
    for key in form.keys():
        if not key.startswith(prefix):
            continue

        raw_qty = (form.get(key) or "").strip()
        if not raw_qty:
            continue

        try:
            qty = float(raw_qty)
        except ValueError:
            continue

        if qty <= 0:
            continue

        try:
            producto_id = int(key.replace(prefix, "", 1))
        except ValueError:
            continue

        ingredientes.append({"producto_id": producto_id, "cantidad_por_unidad": qty})
    return ingredientes


def login_required(view_fn):
    @wraps(view_fn)
    def wrapper(*args, **kwargs):
        if not session.get("access_token"):
            return redirect(url_for("login"))
        return view_fn(*args, **kwargs)

    return wrapper


def roles_required(*roles):
    allowed = set(roles)

    def decorator(view_fn):
        @wraps(view_fn)
        def wrapper(*args, **kwargs):
            if not session.get("access_token"):
                return redirect(url_for("login"))

            current_role = session.get("role")
            if current_role not in allowed:
                target = _dashboard_endpoint_for_role(current_role)
                if target == "login":
                    abort(403)
                flash("No autorizado para esta sección", "error")
                return redirect(url_for(target))

            return view_fn(*args, **kwargs)

        return wrapper

    return decorator


def create_frontend_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["BACKEND_API_URL"] = os.getenv("BACKEND_API_URL", "http://127.0.0.1:5000")
    app.config["SECRET_KEY"] = os.getenv("FRONTEND_SECRET_KEY", "frontend-dev-secret")

    def auth_token():
        return session.get("access_token")

    def current_role():
        return session.get("role")

    def redirect_to_role_dashboard():
        endpoint = _dashboard_endpoint_for_role(current_role())
        return redirect(url_for(endpoint if endpoint != "login" else "login"))

    @app.get("/")
    def root():
        if session.get("access_token"):
            return redirect_to_role_dashboard()
        return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "GET":
            if session.get("access_token"):
                return redirect_to_role_dashboard()
            return render_template("login.html", backend_api_url=app.config["BACKEND_API_URL"])

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not password:
            flash("Usuario y contraseña son requeridos", "error")
            return redirect(url_for("login"))

        try:
            data = _api_call(
                app.config["BACKEND_API_URL"],
                "POST",
                "/auth/login",
                payload={"username": username, "password": password},
            )
            user = data["user"]
            session["access_token"] = data["access_token"]
            session["role"] = user["role"]
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            flash(f"Bienvenido {user['username']}", "success")
            return redirect_to_role_dashboard()
        except Exception as exc:
            flash(f"Login inválido: {exc}", "error")
            return redirect(url_for("login"))

    @app.get("/logout")
    def logout():
        session.clear()
        flash("Sesión cerrada", "success")
        return redirect(url_for("login"))

    @app.get("/dashboard/admin")
    @login_required
    @roles_required("ADMIN")
    def dashboard_admin():
        api = app.config["BACKEND_API_URL"]
        token = auth_token()
        pedidos_filters = {
            "estado": request.args.get("pedido_estado", "").strip(),
            "date_from": request.args.get("pedido_date_from", "").strip(),
            "date_to": request.args.get("pedido_date_to", "").strip(),
        }
        compras_filters = {
            "proveedor": request.args.get("compra_proveedor", "").strip(),
            "date_from": request.args.get("compra_date_from", "").strip(),
            "date_to": request.args.get("compra_date_to", "").strip(),
        }
        inventario_filters = {
            "estado": request.args.get("inv_estado", "").strip(),
            "tipo": request.args.get("inv_tipo", "").strip(),
            "date_from": request.args.get("inv_date_from", "").strip(),
            "date_to": request.args.get("inv_date_to", "").strip(),
        }
        pedidos = _safe_get(api, "/pedidos", [], token, pedidos_filters)
        mesas = _safe_get(api, "/mesas", [], token)
        productos = _safe_get(api, "/productos", [], token)
        platillos = _safe_get(api, "/platillos", [], token)
        compras = _safe_get(api, "/compras", [], token, compras_filters)
        inventarios_fisicos = _safe_get(api, "/inventarios-fisicos", [], token, inventario_filters)
        kardex_producto_id = request.args.get("kardex_producto_id", "").strip()
        kardex_data = None
        if kardex_producto_id:
            kardex_data = _safe_get(api, f"/kardex/{kardex_producto_id}", None, token)
        context = {
            "backend_api_url": api,
            "users": _safe_get(api, "/auth/users", [], token),
            "mesas": mesas,
            "productos": productos,
            "platillos": platillos,
            "compras": compras,
            "inventarios_fisicos": inventarios_fisicos,
            "pedidos": pedidos,
            "pedidos_activos": [p for p in pedidos if _is_pedido_activo(p)],
            "kardex_data": kardex_data,
            "kardex_producto_id": kardex_producto_id,
            "pedido_filters": pedidos_filters,
            "compra_filters": compras_filters,
            "inventario_filters": inventario_filters,
            "caja_estado": _safe_get(api, "/caja/estado", {"abierta": False, "apertura": None}, token),
            "me": _safe_get(api, "/auth/me", {"user": None}, token),
            "allowed_product_units": ALLOWED_PRODUCT_UNITS,
        }
        return render_template("dashboard_admin.html", **context)

    @app.get("/dashboard/caja")
    @login_required
    @roles_required("CAJERO")
    def dashboard_caja():
        api = app.config["BACKEND_API_URL"]
        token = auth_token()
        pedidos = _safe_get(api, "/pedidos", [], token)
        context = {
            "backend_api_url": api,
            "caja_estado": _safe_get(api, "/caja/estado", {"abierta": False, "apertura": None}, token),
            "pedidos_pendientes": [p for p in pedidos if _is_pedido_cobrable(p)],
            "me": _safe_get(api, "/auth/me", {"user": None}, token),
        }
        return render_template("dashboard_caja.html", **context)

    @app.get("/dashboard/mesas")
    @login_required
    @roles_required("MESERO")
    def dashboard_mesas():
        api = app.config["BACKEND_API_URL"]
        token = auth_token()
        mesas = _safe_get(api, "/mesas", [], token)
        platillos = _safe_get(api, "/platillos", [], token)
        pedidos = _safe_get(api, "/pedidos", [], token)
        users = _safe_get(api, "/auth/users", [], token)
        pedidos_abiertos = [p for p in pedidos if p.get("estado") == "ABIERTO"]
        pedidos_preparacion = [p for p in pedidos if p.get("estado") == "PREPARACION"]
        pedidos_servidos = [p for p in pedidos if p.get("estado") == "SERVIDO"]
        platillos_disponibles = [p for p in platillos if p.get("activo")]
        context = {
            "backend_api_url": api,
            "mesas": mesas,
            "platillos": platillos_disponibles,
            "pedidos": pedidos,
            "pedidos_activos": [p for p in pedidos if _is_pedido_activo(p)],
            "pedidos_abiertos": pedidos_abiertos,
            "pedidos_preparacion": pedidos_preparacion,
            "pedidos_servidos": pedidos_servidos,
            "pedidos_servidos_ids": [p.get("id") for p in pedidos_servidos],
            "mesas_libres": [m for m in mesas if m.get("estado") == "LIBRE"],
            "meseros": [u for u in users if u.get("role") == "MESERO"],
            "me": _safe_get(api, "/auth/me", {"user": None}, token),
        }
        return render_template("dashboard_mesas.html", **context)

    @app.get("/api/mesero/pedidos-status")
    @login_required
    @roles_required("MESERO")
    def mesero_pedidos_status():
        api = app.config["BACKEND_API_URL"]
        token = auth_token()
        pedidos = _safe_get(api, "/pedidos", [], token)
        return jsonify(
            {
                "abiertos": [p["id"] for p in pedidos if p.get("estado") == "ABIERTO"],
                "preparacion": [p["id"] for p in pedidos if p.get("estado") == "PREPARACION"],
                "servidos": [p["id"] for p in pedidos if p.get("estado") == "SERVIDO"],
                "servidos_detalle": [
                    {"id": p.get("id"), "mesa_id": p.get("mesa_id"), "total": p.get("total")}
                    for p in pedidos
                    if p.get("estado") == "SERVIDO"
                ],
            }
        )

    @app.get("/dashboard/cocina")
    @login_required
    @roles_required("COCINA")
    def dashboard_cocina():
        api = app.config["BACKEND_API_URL"]
        token = auth_token()
        pedidos = _safe_get(api, "/pedidos", [], token)
        context = {
            "backend_api_url": api,
            "pedidos": pedidos,
            "pedidos_activos": [p for p in pedidos if _is_pedido_activo(p)],
            "pedidos_preparacion": [p for p in pedidos if p.get("estado") == "PREPARACION"],
            "me": _safe_get(api, "/auth/me", {"user": None}, token),
        }
        return render_template("dashboard_cocina.html", **context)

    @app.post("/actions/register")
    @login_required
    @roles_required("ADMIN")
    def register_user():
        payload = {
            "username": request.form.get("username", "").strip(),
            "password": request.form.get("password", "").strip(),
            "role": request.form.get("role", "MESERO").strip(),
        }
        try:
            data = _api_call(app.config["BACKEND_API_URL"], "POST", "/auth/register", payload, auth_token())
            flash(f"Usuario creado: {data.get('id')} - {data.get('username')}", "success")
        except Exception as exc:
            flash(f"Error creando usuario: {exc}", "error")
        return redirect(url_for("dashboard_admin"))

    @app.post("/actions/mesa")
    @login_required
    @roles_required("ADMIN", "MESERO")
    def create_mesa():
        payload = {
            "numero": int(request.form.get("numero", "0")),
            "estado": request.form.get("estado", "LIBRE").strip(),
        }
        try:
            data = _api_call(app.config["BACKEND_API_URL"], "POST", "/mesas", payload, auth_token())
            flash(f"Mesa creada: ID {data.get('id')}", "success")
        except Exception as exc:
            flash(f"Error creando mesa: {exc}", "error")
        return redirect(url_for("dashboard_mesas"))

    @app.post("/actions/mesa-estado")
    @login_required
    @roles_required("ADMIN", "MESERO")
    def update_mesa_estado():
        mesa_id = int(request.form.get("mesa_id", "0") or 0)
        payload = {"estado": request.form.get("estado", "LIBRE")}
        try:
            _api_call(app.config["BACKEND_API_URL"], "PATCH", f"/mesas/{mesa_id}", payload, auth_token())
            flash("Mesa actualizada", "success")
        except Exception as exc:
            flash(f"Error actualizando mesa: {exc}", "error")
        return redirect(url_for("dashboard_mesas"))

    @app.post("/actions/producto")
    @login_required
    @roles_required("ADMIN")
    def create_producto():
        unidad = request.form.get("unidad", "").strip().lower()
        if unidad not in ALLOWED_PRODUCT_UNITS:
            flash(f"Unidad inválida. Usa: {', '.join(ALLOWED_PRODUCT_UNITS)}", "error")
            return redirect(url_for("dashboard_admin"))

        payload = {
            "nombre": request.form.get("nombre", "").strip(),
            "unidad": unidad,
            "stock_actual": float(request.form.get("stock_actual", "0") or 0),
            "costo_promedio": float(request.form.get("costo_promedio", "0") or 0),
        }
        try:
            data = _api_call(app.config["BACKEND_API_URL"], "POST", "/productos", payload, auth_token())
            flash(f"Producto creado: ID {data.get('id')}", "success")
        except Exception as exc:
            flash(f"Error creando producto: {exc}", "error")
        return redirect(url_for("dashboard_admin"))

    @app.post("/actions/producto-estado")
    @login_required
    @roles_required("ADMIN")
    def update_producto_estado():
        producto_id = int(request.form.get("producto_id", "0") or 0)
        activo = request.form.get("activo", "true").lower() == "true"
        try:
            _api_call(
                app.config["BACKEND_API_URL"],
                "PATCH",
                f"/productos/{producto_id}",
                {"activo": activo},
                auth_token(),
            )
            flash("Producto actualizado", "success")
        except Exception as exc:
            flash(f"Error actualizando producto: {exc}", "error")
        return redirect(url_for("dashboard_admin"))

    @app.post("/actions/platillo")
    @login_required
    @roles_required("ADMIN")
    def create_platillo():
        ingredientes = _extract_ingredientes_from_form(request.form, "ing_")
        if not ingredientes:
            flash("Debes indicar al menos un producto con cantidad mayor a 0", "error")
            return redirect(url_for("dashboard_admin"))

        payload = {
            "nombre": request.form.get("nombre", "").strip(),
            "precio": float(request.form.get("precio", "0") or 0),
            "activo": True,
            "ingredientes": ingredientes,
        }
        try:
            data = _api_call(app.config["BACKEND_API_URL"], "POST", "/platillos", payload, auth_token())
            flash(f"Platillo creado: ID {data.get('id')}", "success")
        except Exception as exc:
            flash(f"Error creando platillo: {exc}", "error")
        return redirect(url_for("dashboard_admin"))

    @app.post("/actions/platillo-editar")
    @login_required
    @roles_required("ADMIN")
    def update_platillo_full():
        platillo_id = int(request.form.get("platillo_id", "0") or 0)
        ingredientes = _extract_ingredientes_from_form(request.form, "edit_ing_")
        if not ingredientes:
            flash("Debes indicar al menos un producto con cantidad mayor a 0 para la receta", "error")
            return redirect(url_for("dashboard_admin"))

        payload = {
            "nombre": request.form.get("nombre", "").strip(),
            "precio": float(request.form.get("precio", "0") or 0),
            "ingredientes": ingredientes,
        }
        try:
            _api_call(
                app.config["BACKEND_API_URL"],
                "PATCH",
                f"/platillos/{platillo_id}",
                payload,
                auth_token(),
            )
            flash("Platillo y receta actualizados", "success")
        except Exception as exc:
            flash(f"Error actualizando platillo: {exc}", "error")
        return redirect(url_for("dashboard_admin"))

    @app.post("/actions/platillo-estado")
    @login_required
    @roles_required("ADMIN")
    def update_platillo_estado():
        platillo_id = int(request.form.get("platillo_id", "0") or 0)
        activo = request.form.get("activo", "true").lower() == "true"
        try:
            _api_call(
                app.config["BACKEND_API_URL"],
                "PATCH",
                f"/platillos/{platillo_id}",
                {"activo": activo},
                auth_token(),
            )
            flash("Platillo actualizado", "success")
        except Exception as exc:
            flash(f"Error actualizando platillo: {exc}", "error")
        return redirect(url_for("dashboard_admin"))

    @app.post("/actions/platillo-ingrediente")
    @login_required
    @roles_required("ADMIN")
    def add_ingrediente():
        platillo_id = int(request.form.get("platillo_id", "0") or 0)
        payload = {
            "ingredientes": [
                {
                    "producto_id": int(request.form.get("producto_id", "0") or 0),
                    "cantidad_por_unidad": float(request.form.get("cantidad_por_unidad", "0") or 0),
                }
            ]
        }
        try:
            _api_call(app.config["BACKEND_API_URL"], "POST", f"/platillos/{platillo_id}/ingredientes", payload, auth_token())
            flash("Receta actualizada", "success")
        except Exception as exc:
            flash(f"Error actualizando receta: {exc}", "error")
        return redirect(url_for("dashboard_admin"))

    @app.post("/actions/compra")
    @login_required
    @roles_required("ADMIN")
    def create_compra():
        payload = {
            "proveedor": request.form.get("proveedor", "").strip(),
            "detalles": [
                {
                    "producto_id": int(request.form.get("producto_id", "0") or 0),
                    "cantidad": float(request.form.get("cantidad", "0") or 0),
                    "costo_unitario": float(request.form.get("costo_unitario", "0") or 0),
                }
            ],
        }
        try:
            data = _api_call(app.config["BACKEND_API_URL"], "POST", "/compras", payload, auth_token())
            flash(f"Compra registrada: ID {data.get('id')}", "success")
        except Exception as exc:
            flash(f"Error registrando compra: {exc}", "error")
        return redirect(url_for("dashboard_admin"))

    @app.post("/actions/inventario-fisico")
    @login_required
    @roles_required("ADMIN")
    def create_inventario_fisico():
        payload = {
            "tipo": request.form.get("tipo", "MENSUAL"),
            "detalles": [
                {
                    "producto_id": int(request.form.get("producto_id", "0") or 0),
                    "conteo": float(request.form.get("conteo", "0") or 0),
                }
            ],
        }
        try:
            data = _api_call(app.config["BACKEND_API_URL"], "POST", "/inventarios-fisicos", payload, auth_token())
            flash(f"Inventario físico creado: ID {data.get('id')}", "success")
        except Exception as exc:
            flash(f"Error creando inventario físico: {exc}", "error")
        return redirect(url_for("dashboard_admin"))

    @app.post("/actions/inventario-fisico-aplicar")
    @login_required
    @roles_required("ADMIN")
    def apply_inventario_fisico():
        inventario_id = int(request.form.get("inventario_id", "0") or 0)
        try:
            _api_call(
                app.config["BACKEND_API_URL"],
                "POST",
                f"/inventarios-fisicos/{inventario_id}/aplicar",
                {},
                auth_token(),
            )
            flash("Inventario físico aplicado", "success")
        except Exception as exc:
            flash(f"Error aplicando inventario físico: {exc}", "error")
        return redirect(url_for("dashboard_admin"))

    @app.post("/actions/pedido")
    @login_required
    @roles_required("ADMIN", "MESERO")
    def create_pedido():
        payload = {
            "mesa_id": int(request.form.get("mesa_id", "0") or 0),
            "user_id": int(request.form.get("user_id", "0") or 0),
        }
        try:
            data = _api_call(app.config["BACKEND_API_URL"], "POST", "/pedidos", payload, auth_token())
            flash(f"Pedido creado: ID {data.get('id')}", "success")
        except Exception as exc:
            flash(f"Error creando pedido: {exc}", "error")
        return redirect(url_for("dashboard_mesas"))

    @app.post("/actions/pedido-item")
    @login_required
    @roles_required("ADMIN", "MESERO")
    def add_item_pedido():
        pedido_id = int(request.form.get("pedido_id", "0") or 0)
        payload = {
            "platillo_id": int(request.form.get("platillo_id", "0") or 0),
            "cantidad": float(request.form.get("cantidad", "0") or 0),
        }
        try:
            _api_call(app.config["BACKEND_API_URL"], "POST", f"/pedidos/{pedido_id}/items", payload, auth_token())
            flash("Item agregado al pedido", "success")
        except Exception as exc:
            flash(f"Error agregando item: {exc}", "error")
        return redirect(url_for("dashboard_mesas"))

    @app.post("/actions/pedido-item-editar")
    @login_required
    @roles_required("ADMIN", "MESERO")
    def update_item_pedido():
        pedido_id = int(request.form.get("pedido_id", "0") or 0)
        detalle_id = int(request.form.get("detalle_id", "0") or 0)
        payload = {"cantidad": float(request.form.get("cantidad", "0") or 0)}
        try:
            _api_call(
                app.config["BACKEND_API_URL"],
                "PATCH",
                f"/pedidos/{pedido_id}/items/{detalle_id}",
                payload,
                auth_token(),
            )
            flash("Item actualizado", "success")
        except Exception as exc:
            flash(f"Error actualizando item: {exc}", "error")
        return redirect(url_for("dashboard_mesas"))

    @app.post("/actions/pedido-item-eliminar")
    @login_required
    @roles_required("ADMIN", "MESERO")
    def delete_item_pedido():
        pedido_id = int(request.form.get("pedido_id", "0") or 0)
        detalle_id = int(request.form.get("detalle_id", "0") or 0)
        try:
            _api_call(
                app.config["BACKEND_API_URL"],
                "DELETE",
                f"/pedidos/{pedido_id}/items/{detalle_id}",
                {},
                auth_token(),
            )
            flash("Item eliminado", "success")
        except Exception as exc:
            flash(f"Error eliminando item: {exc}", "error")
        return redirect(url_for("dashboard_mesas"))

    @app.post("/actions/pedido-estado")
    @login_required
    @roles_required("ADMIN", "MESERO", "COCINA")
    def update_pedido_estado():
        pedido_id = int(request.form.get("pedido_id", "0") or 0)
        payload = {"estado": request.form.get("estado", "PREPARACION")}
        try:
            _api_call(app.config["BACKEND_API_URL"], "PATCH", f"/pedidos/{pedido_id}/estado", payload, auth_token())
            flash("Estado de pedido actualizado", "success")
        except Exception as exc:
            flash(f"Error actualizando pedido: {exc}", "error")

        if current_role() == "COCINA":
            return redirect(url_for("dashboard_cocina"))
        return redirect(url_for("dashboard_mesas"))

    @app.post("/actions/caja-apertura")
    @login_required
    @roles_required("ADMIN", "CAJERO")
    def apertura_caja():
        payload = {
            "user_id": int(request.form.get("user_id", "0") or 0),
            "monto_inicial": float(request.form.get("monto_inicial", "0") or 0),
        }
        try:
            data = _api_call(app.config["BACKEND_API_URL"], "POST", "/caja/apertura", payload, auth_token())
            flash(f"Caja abierta: ID {data.get('id')}", "success")
        except Exception as exc:
            flash(f"Error abriendo caja: {exc}", "error")
        return redirect(url_for("dashboard_caja"))

    @app.post("/actions/caja-cobro")
    @login_required
    @roles_required("ADMIN", "CAJERO")
    def cobro_caja():
        payload = {
            "pedido_id": int(request.form.get("pedido_id", "0") or 0),
            "metodo": request.form.get("metodo", "EFECTIVO").strip(),
        }
        try:
            data = _api_call(app.config["BACKEND_API_URL"], "POST", "/caja/cobro", payload, auth_token())
            flash(f"Cobro registrado: ID {data.get('id')}", "success")
        except Exception as exc:
            flash(f"Error en cobro: {exc}", "error")
        return redirect(url_for("dashboard_caja"))

    @app.post("/actions/caja-cierre")
    @login_required
    @roles_required("ADMIN", "CAJERO")
    def cierre_caja():
        payload = {
            "apertura_caja_id": int(request.form.get("apertura_caja_id", "0") or 0),
        }
        try:
            data = _api_call(app.config["BACKEND_API_URL"], "POST", "/caja/cierre", payload, auth_token())
            flash(f"Caja cerrada: cierre ID {data.get('id')}", "success")
        except Exception as exc:
            flash(f"Error cerrando caja: {exc}", "error")
        return redirect(url_for("dashboard_caja"))

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "frontend"}

    return app
