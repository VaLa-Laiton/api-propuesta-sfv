from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --- ENUMS ---
class TipoTarifa(str, Enum):
    RESIDENCIAL = "residencial"  # 3-10 kWp
    COMERCIAL = "comercial"  # 10-40 kWp
    INDUSTRIAL = "industrial"  # >40 kWp


# --- INPUTS ---
class SolarInput(BaseModel):
    nombre_cliente: str = Field(..., example="SUNCITY")
    consumo_energia_kwh_mes: float = Field(..., gt=0, example=999.90)
    precio_energia_base: float = Field(..., gt=0, example=803.25)
    contribucion_porcentaje: float = Field(..., ge=0, le=100, example=20.0)
    impuesto_ap_porcentaje: float = Field(..., ge=0, le=100, example=14.0)
    cobertura_objetivo_porcentaje: float = Field(..., gt=0, le=100, example=100.0)
    tasa_descuento_porcentaje: float = Field(..., gt=0, example=12.0)

    # Opcional: El usuario puede pedir un escenario "a la carta"
    forzar_tipo_tarifa: Optional[TipoTarifa] = Field(
        None,
        description="Si se envía, genera un segundo escenario financiero usando esta tarifa obligatoriamente.",
    )


class SystemParameters(BaseModel):
    horas_sol_pico: float = Field(3.77)
    factor_rendimiento: float = Field(1.0)
    potencia_modulo_watts: float = Field(585.0)
    factor_area_modulo: float = Field(2.6)
    factor_espaciamiento: float = Field(1.25)
    porc_autoconsumo_directo: float = Field(0.60)
    porc_excedentes_t1: float = Field(0.30)
    porc_excedentes_t2: float = Field(0.10)
    factor_precio_t1: float = Field(1.0)
    precio_excedente_t2_fijo: float = Field(300.0)
    inflacion_energia_anual: float = Field(0.039)
    inflacion_ipp_anual: float = Field(0.039)
    degradacion_anual_paneles: float = Field(0.005)
    anos_proyeccion: int = Field(25)
    costo_mantenimiento_anual_kwp: float = Field(25000.0)


class SolarRequest(SolarInput):
    params: Optional[SystemParameters] = Field(default_factory=SystemParameters)


# --- OUTPUTS ---


class TechnicalSpecs(BaseModel):
    """
    Datos Físicos invariables (No dependen del dinero).
    """

    precio_kwh_full: float
    pago_mensual_actual: float
    consumo_diario_kwh: float
    produccion_diaria_sfv: float
    capacidad_sistema_kwp: float  # Teórica
    capacidad_instalada_kwp: float  # Real
    numero_modulos: int
    area_requerida_m2: float


class EconomicScenario(BaseModel):
    """
    Un escenario financiero completo.
    Puede ser el 'Automático' (Real) o el 'Usuario' (Forzado).
    """

    nombre_escenario: str  # Ej: "Automático (Residencial)" o "Usuario (Comercial)"
    tipo_sistema_detectado: str
    explicacion: str
    costo_sistema_total: float
    costo_kwp_aplicado: float
    ahorro_mensual_promedio: float
    pago_mensual_con_sfv: float
    porcentaje_ahorro_factura: float
    van: float
    tir: float
    relacion_beneficio_costo: float
    periodo_retorno_anos: float
    viabilidad: str


class SolarProjectResponse(BaseModel):
    cliente: str
    datos_entrada: SolarInput
    especificaciones_tecnicas: TechnicalSpecs  # Datos Comunes
    escenario_automatico: EconomicScenario  # La verdad matemática
    escenario_usuario: Optional[EconomicScenario] = (
        None  # El escenario "simulado" (si se pidió)
    )
