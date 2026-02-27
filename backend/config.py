import os
from datetime import timedelta


def _as_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///garrobito.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=int(os.getenv("JWT_ACCESS_HOURS", "8")))
    ENV = os.getenv("FLASK_ENV", "production")
    DEBUG = _as_bool(os.getenv("FLASK_DEBUG"), default=False)
    JENKINS_URL = os.getenv("JENKINS_URL", "").strip().rstrip("/")
    JENKINS_USER = os.getenv("JENKINS_USER", "").strip()
    JENKINS_API_TOKEN = os.getenv("JENKINS_API_TOKEN", "").strip()
    JENKINS_JOB_NAME = os.getenv("JENKINS_JOB_NAME", "garrobito-deploy").strip()
    JENKINS_VERIFY_SSL = _as_bool(os.getenv("JENKINS_VERIFY_SSL"), default=True)
    DEPLOY_API_KEY = os.getenv("DEPLOY_API_KEY", "").strip()
