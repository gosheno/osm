from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.addresses import router as addresses_router
from app.api.routes.batches import router as batches_router
from app.api.routes.health import router as health_router
from app.api.routes.optimize import router as optimize_router
from app.api.routes.osrm import router as osrm_router
from app.api.routes.yandex_links import router as yandex_links_router
from app.api.routes.routes import router as routes_router
from app.core.error_handlers import register_error_handlers


app = FastAPI(
    title="OSM Route Optimizer API",
    version="0.1.0",
    description="Backend API для оптимизации маршрутов по списку адресов",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(addresses_router)
app.include_router(osrm_router)
app.include_router(optimize_router)
app.include_router(batches_router)
app.include_router(yandex_links_router)
app.include_router(routes_router)

register_error_handlers(app)


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "service": "backend",
        "message": "FastAPI backend is running",
    }
