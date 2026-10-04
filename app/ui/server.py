import os
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

def create_app():
    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB max request size
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    
    from app.ui.routes import bp
    app.register_blueprint(bp)
    
    return app

def run(args):
    app = create_app()
    app.config['RF_SHAZAM_ARGS'] = args
    app.run(host=args.host, port=args.port, debug=False, use_reloader=False)
