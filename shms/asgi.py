"""ASGI entry point:  uvicorn shms.asgi:app --reload"""

from .main import create_app

app = create_app()
