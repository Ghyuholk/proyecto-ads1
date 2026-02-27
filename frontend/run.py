import os

from dotenv import load_dotenv

from app import create_frontend_app


# Load local frontend/.env automatically for local runs.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

app = create_frontend_app()


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "5001")),
        debug=False,
    )
