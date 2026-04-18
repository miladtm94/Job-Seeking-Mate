from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.api.v1.endpoints.apply_ws import router as apply_ws_router
from app.api.v1.endpoints.agent_ws import router as agent_ws_router
from app.core.config import apply_user_overrides, get_settings
from app.core.logging import configure_logging

# Apply saved user overrides (data/user_settings.json → os.environ) BEFORE
# get_settings() is called so that user-configured provider/model survive restarts.
apply_user_overrides()
settings = get_settings()
configure_logging()

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)
# WebSocket routes registered directly on app (not under api_router prefix)
app.include_router(apply_ws_router)
app.include_router(agent_ws_router)
