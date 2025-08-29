from flask import Flask, render_template
from src.utils.utils import db

def create_app():
    app = Flask(__name__)

     
    app.config["SQLALCHEMY_DATABASE_URI"] ='mysql://root:root@127.0.0.1:3307/garrobito'
    db.init_app(app)
    return app

app=create_app()

    
@app.get("/")
def home():
    return "<h3>PROYECTO-ANDS1  Flask is running</h3>"


if __name__ == "__main__":
    # Dev server with auto-reload and debugger
    app.run(debug=True)
