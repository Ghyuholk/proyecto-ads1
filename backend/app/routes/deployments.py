import re

import requests
from flask import Blueprint, current_app, jsonify, request

from app.routes.utils import error_response


deployments_bp = Blueprint("deployments", __name__, url_prefix="/deployments")
SLUG_RE = re.compile(r"^[a-z0-9_-]{3,50}$")


def _require_deploy_key(req):
    expected = (current_app.config.get("DEPLOY_API_KEY") or "").strip()
    if not expected:
        return True, False
    provided = (req.headers.get("X-Deploy-Key") or "").strip()
    return provided == expected, True


def _jenkins_base_config():
    return {
        "url": (current_app.config.get("JENKINS_URL") or "").strip().rstrip("/"),
        "user": (current_app.config.get("JENKINS_USER") or "").strip(),
        "token": (current_app.config.get("JENKINS_API_TOKEN") or "").strip(),
        "job": (current_app.config.get("JENKINS_JOB_NAME") or "").strip(),
        "verify_ssl": bool(current_app.config.get("JENKINS_VERIFY_SSL", True)),
    }


def _validate_payload(data):
    client_name = (data.get("client_name") or "").strip()
    slug = (data.get("slug") or "").strip().lower()
    admin_username = "admin"
    admin_password = (data.get("admin_password") or "").strip()

    if not client_name:
        raise ValueError("client_name es requerido")
    if not slug:
        raise ValueError("slug es requerido")
    if not SLUG_RE.match(slug):
        raise ValueError("slug inválido. Use letras minúsculas, números, guion o guion bajo (3-50)")
    if not admin_password:
        raise ValueError("admin_password es requerido")

    return {
        "client_name": client_name,
        "slug": slug,
        "admin_username": admin_username,
        "admin_password": admin_password,
    }


def _jenkins_get_crumb(cfg):
    crumb_url = f"{cfg['url']}/crumbIssuer/api/json"
    try:
        response = requests.get(
            crumb_url,
            auth=(cfg["user"], cfg["token"]),
            timeout=8,
            verify=cfg["verify_ssl"],
        )
        if response.status_code >= 400:
            return {}
        data = response.json()
        field = data.get("crumbRequestField")
        crumb = data.get("crumb")
        if field and crumb:
            return {field: crumb}
    except Exception:
        return {}
    return {}


@deployments_bp.post("/tenant")
def trigger_tenant_deployment():
    authorized, key_required = _require_deploy_key(request)
    if not authorized:
        if key_required:
            return error_response("No autorizado: X-Deploy-Key inválido o ausente", 403)
        return error_response("No autorizado", 403)

    cfg = _jenkins_base_config()
    if not cfg["url"] or not cfg["user"] or not cfg["token"] or not cfg["job"]:
        return error_response("Configuración Jenkins incompleta en backend", 500)

    data = request.get_json(silent=True) or {}
    try:
        payload = _validate_payload(data)
    except ValueError as exc:
        return error_response(str(exc), 400)

    build_url = f"{cfg['url']}/job/{cfg['job']}/buildWithParameters"
    params = {
        "CLIENT_NAME": payload["client_name"],
        "SLUG": payload["slug"],
        "ADMIN_USERNAME": payload["admin_username"],
        "ADMIN_PASSWORD": payload["admin_password"],
    }

    headers = _jenkins_get_crumb(cfg)
    try:
        response = requests.post(
            build_url,
            params=params,
            headers=headers,
            auth=(cfg["user"], cfg["token"]),
            timeout=12,
            verify=cfg["verify_ssl"],
        )
    except requests.RequestException as exc:
        return error_response(f"Error conectando con Jenkins: {exc}", 502)

    if response.status_code not in (200, 201, 202):
        return error_response(
            f"Jenkins devolvió {response.status_code}: {response.text[:250]}",
            502,
        )

    queue_item_url = response.headers.get("Location", "")
    return jsonify(
        {
            "message": "Despliegue solicitado correctamente",
            "queue_item_url": queue_item_url,
            "jenkins_job": cfg["job"],
            "slug": payload["slug"],
        }
    ), 202
