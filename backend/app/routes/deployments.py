import re

import requests
from sqlalchemy import text
from flask import Blueprint, current_app, jsonify, request

from app.extensions import db
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


def _tenant_db_exists(slug):
    tenant_db_name = f"db_{slug}"
    query = text(
        "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = :schema_name LIMIT 1"
    )
    result = db.session.execute(query, {"schema_name": tenant_db_name}).first()
    return result is not None


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


def _to_api_json_url(url):
    normalized = (url or "").strip().rstrip("/")
    if not normalized:
        return ""
    if normalized.endswith("/api/json"):
        return normalized
    return f"{normalized}/api/json"


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

    try:
        if _tenant_db_exists(payload["slug"]):
            return error_response("El identificador ya existe. Usa uno diferente.", 409)
    except Exception as exc:
        return error_response(f"No se pudo validar el identificador: {exc}", 500)

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


@deployments_bp.get("/tenant/status")
def get_tenant_deployment_status():
    authorized, key_required = _require_deploy_key(request)
    if not authorized:
        if key_required:
            return error_response("No autorizado: X-Deploy-Key inválido o ausente", 403)
        return error_response("No autorizado", 403)

    cfg = _jenkins_base_config()
    if not cfg["url"] or not cfg["user"] or not cfg["token"] or not cfg["job"]:
        return error_response("Configuración Jenkins incompleta en backend", 500)

    queue_item_url = (request.args.get("queue_item_url") or "").strip()
    if not queue_item_url:
        return error_response("queue_item_url es requerido", 400)

    queue_api_url = _to_api_json_url(queue_item_url)
    try:
        queue_response = requests.get(
            queue_api_url,
            auth=(cfg["user"], cfg["token"]),
            timeout=8,
            verify=cfg["verify_ssl"],
        )
    except requests.RequestException as exc:
        return error_response(f"Error consultando estado en Jenkins: {exc}", 502)

    if queue_response.status_code >= 400:
        return error_response(
            f"Jenkins devolvió {queue_response.status_code} consultando cola",
            502,
        )

    queue_data = queue_response.json()
    if queue_data.get("cancelled"):
        return jsonify(
            {
                "state": "failed",
                "message": "El despliegue fue cancelado en Jenkins",
                "queue_item_url": queue_item_url,
            }
        )

    executable = queue_data.get("executable") or {}
    build_url = (executable.get("url") or "").strip()

    if not build_url:
        return jsonify(
            {
                "state": "queued",
                "message": "Tu solicitud está en cola o en preparación",
                "queue_item_url": queue_item_url,
            }
        )

    build_api_url = _to_api_json_url(build_url)
    try:
        build_response = requests.get(
            build_api_url,
            auth=(cfg["user"], cfg["token"]),
            timeout=8,
            verify=cfg["verify_ssl"],
        )
    except requests.RequestException as exc:
        return error_response(f"Error consultando build en Jenkins: {exc}", 502)

    if build_response.status_code >= 400:
        return error_response(
            f"Jenkins devolvió {build_response.status_code} consultando build",
            502,
        )

    build_data = build_response.json()
    result = (build_data.get("result") or "").upper()
    building = bool(build_data.get("building"))

    if building:
        state = "running"
        message = "Despliegue en progreso"
    elif result == "SUCCESS":
        state = "success"
        message = "Despliegue completado exitosamente"
    elif result in {"FAILURE", "ABORTED", "UNSTABLE", "NOT_BUILT"}:
        state = "failed"
        message = f"Despliegue finalizó con estado {result}"
    else:
        state = "running"
        message = "Jenkins aún está procesando el despliegue"

    return jsonify(
        {
            "state": state,
            "message": message,
            "result": result,
            "queue_item_url": queue_item_url,
            "build_url": build_url,
            "build_number": build_data.get("number"),
        }
    )
