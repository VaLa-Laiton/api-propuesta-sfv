from typing import Optional

from pydantic import BaseModel, Field

# --- INPUTS (Lo que recibimos) ---


class SolarInput(BaseModel):
    """
    Datos base del usuario.
    """

    nombre_cliente: str = Field(..., example="SUNCITY")
    consumo_energia_kwh_mes: float = Field(..., gt=0, example=999.90)
    precio_energia_base: float = Field(..., gt=0, example=803.25)
    contribucion_porcentaje: float = Field(..., ge=0, le=100, example=20.0)
    impuesto_ap_porcentaje: float = Field(..., ge=0, le=100, example=14.0)
    cobertura_objetivo_porcentaje: float = Field(..., gt=0, le=100, example=100.0)
    tasa_descuento_porcentaje: float = Field(..., gt=0, example=12.0)


class SystemParameters(BaseModel):
    """
    Parámetros técnicos calibrados.
    """

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
    """
    MODELO HÍBRIDO: Hereda todos los campos de SolarInput para que estén
    en el nivel superior del JSON, y agrega 'params' como opcional.
    Esto arregla el error 422 de Postman.
    """

    params: Optional[SystemParameters] = Field(default_factory=SystemParameters)


# --- OUTPUTS (Lo que entregamos) ---


class TechnicalResults(BaseModel):
    precio_kwh_full: float
    pago_mensual_actual: float
    consumo_diario_kwh: float
    produccion_diaria_sfv: float
    capacidad_sistema_kwp: float
    numero_modulos: int
    area_requerida_m2: float
    tipo_sistema: str


class FinancialResults(BaseModel):
    ahorro_mensual_promedio: float
    pago_mensual_con_sfv: float
    porcentaje_ahorro_factura: float
    costo_sistema_total: float
    costo_kwp_aplicado: float
    van: float
    tir: float
    relacion_beneficio_costo: float
    periodo_retorno_anos: float
    viabilidad: str


class SolarProjectResponse(BaseModel):
    cliente: str
    datos_entrada: SolarInput
    resultados_tecnicos: TechnicalResults
    resultados_financieros: FinancialResults
