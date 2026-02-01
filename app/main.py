from fastapi import FastAPI

from app.api.v1_endpoints import router as api_router
from app.core.config import settings

# 1. Crear la instancia de FastAPI con la configuración
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description=settings.DESCRIPTION,
)

# 2. Incluir las rutas (endpoints)
# El prefijo "/api/v1" es buena práctica para versiones futuras
app.include_router(api_router, prefix="/api/v1", tags=["Calculadora Solar"])


# 3. Endpoint de salud (Health check)
@app.get("/")
def read_root():
    return {"status": "ok", "message": "API Solar funcionando correctamente"}


# Bloque para correr localmente con: python app/main.py
if __name__ == "__main__":
    import uvicorn

    # Se asume que el archivo se llama main.py y está dentro del paquete app
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
