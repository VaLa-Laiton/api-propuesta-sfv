from fastapi import APIRouter, HTTPException

from app.models.schemas import SolarInput, SolarProjectResponse, SolarRequest
from app.services.calculadora import calcular_proyecto

router = APIRouter()


@router.post("/calcular-viabilidad", response_model=SolarProjectResponse)
async def calculate_solar_viability(request: SolarRequest):
    """
    Endpoint que acepta JSON plano (campos de SolarInput en la raíz).
    Opcionalmente acepta 'params' anidado si se necesita calibrar.
    """
    try:
        # Extraemos los datos base
        data = SolarInput(**request.dict())
        # Extraemos los parámetros (o usamos los default si no vienen)
        params = request.params

        resultado = calcular_proyecto(data, params)
        return resultado
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
