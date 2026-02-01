import math
from typing import List

from app.models.schemas import (
    FinancialResults,
    SolarInput,
    SolarProjectResponse,
    SystemParameters,
    TechnicalResults,
)


# --- Funciones Financieras ---
def calcular_npv(rate: float, values: List[float]) -> float:
    total = 0.0
    for i, val in enumerate(values):
        total += val / ((1 + rate) ** i)
    return total


def calcular_irr(values: List[float], guess: float = 0.1) -> float:
    max_iter = 100
    tol = 1e-7
    rate = guess
    for _ in range(max_iter):
        npv = calcular_npv(rate, values)
        npv_derivative = 0.0
        for i, val in enumerate(values):
            if i == 0:
                continue
            npv_derivative -= i * val / ((1 + rate) ** (i + 1))
        if abs(npv_derivative) < tol:
            return rate
        new_rate = rate - npv / npv_derivative
        if abs(new_rate - rate) < tol:
            return new_rate
        rate = new_rate
    return rate


# --- Lógica Principal ---
def calcular_proyecto(
    inputs: SolarInput, params: SystemParameters
) -> SolarProjectResponse:

    pct_contrib = inputs.contribucion_porcentaje / 100
    pct_impuesto = inputs.impuesto_ap_porcentaje / 100
    pct_cobertura = inputs.cobertura_objetivo_porcentaje / 100
    pct_tasa_desc = inputs.tasa_descuento_porcentaje / 100

    # Cálculos Técnicos
    precio_kwh_full = inputs.precio_energia_base * (1 + pct_contrib + pct_impuesto)
    pago_mensual_actual = precio_kwh_full * inputs.consumo_energia_kwh_mes
    consumo_diario = inputs.consumo_energia_kwh_mes / 30
    produccion_sfv_diaria = consumo_diario * pct_cobertura * params.factor_rendimiento
    capacidad_kwp_teorica = produccion_sfv_diaria / params.horas_sol_pico

    factor_potencia = 1000 / params.potencia_modulo_watts
    num_modulos = math.ceil(capacidad_kwp_teorica * factor_potencia)
    capacidad_real_kwp = (num_modulos * params.potencia_modulo_watts) / 1000
    area_requerida = (
        num_modulos * params.factor_area_modulo * params.factor_espaciamiento
    )

    # Selección de Costo (Escalonado)
    if capacidad_real_kwp > 40:
        tipo_sistema = "> 40 kWp (Industrial)"
        costo_por_kwp = 3500000.0
    elif capacidad_real_kwp >= 10:
        tipo_sistema = "10-40 kWp (Comercial)"
        costo_por_kwp = 3800000.0
    else:
        tipo_sistema = "3-10 kWp (Residencial)"
        costo_por_kwp = 4500000.0

    # Redondeo al millón superior (-6 en Excel)
    costo_base = capacidad_real_kwp * costo_por_kwp
    costo_sistema_total = math.ceil(costo_base / 1_000_000) * 1_000_000

    # Ahorros
    # CORRECCIÓN DE PRECIO T1:
    # Según CSV 'CALCULOS', T1 usa 'RESULTADOS!H8' que es el Precio Full.
    # Antes usábamos el base, por eso daba menos ahorro.
    precio_t1 = precio_kwh_full * params.factor_precio_t1

    # Precio T2 (Bolsa/Exportación)
    precio_t2 = params.precio_excedente_t2_fijo

    ahorro_diario_ponderado = (
        (produccion_sfv_diaria * params.porc_autoconsumo_directo * precio_kwh_full)
        + (produccion_sfv_diaria * params.porc_excedentes_t1 * precio_t1)
        + (produccion_sfv_diaria * params.porc_excedentes_t2 * precio_t2)
    )

    ahorro_mensual = ahorro_diario_ponderado * 30
    pago_residual = pago_mensual_actual - ahorro_mensual
    if pago_residual < 0:
        pago_residual = 0
    porcentaje_ahorro = (
        ahorro_mensual / pago_mensual_actual if pago_mensual_actual > 0 else 0
    )

    # Flujo de Caja
    flujo_caja = [-costo_sistema_total]
    ahorro_anual_base = ahorro_mensual * 12
    costo_om_base = capacidad_real_kwp * params.costo_mantenimiento_anual_kwp

    for ano in range(1, params.anos_proyeccion + 1):
        factor_inflacion_energia = (1 + params.inflacion_energia_anual) ** (ano - 1)
        factor_degradacion = (1 - params.degradacion_anual_paneles) ** (ano - 1)
        ingreso_ano = ahorro_anual_base * factor_inflacion_energia * factor_degradacion

        factor_ipc = (1 + params.inflacion_ipp_anual) ** (ano - 1)
        egreso_ano = costo_om_base * factor_ipc

        flujo_caja.append(ingreso_ano - egreso_ano)

    van = calcular_npv(pct_tasa_desc, flujo_caja)
    try:
        tir = calcular_irr(flujo_caja)
    except:
        tir = 0.0

    # Payback
    acumulado = -costo_sistema_total
    payback = params.anos_proyeccion
    for i, flujo in enumerate(flujo_caja[1:], 1):
        acumulado += flujo
        if acumulado >= 0:
            previo = acumulado - flujo
            payback = (i - 1) + (abs(previo) / flujo)
            break

    # B/C
    vp_ingresos = sum(
        [
            f / ((1 + pct_tasa_desc) ** i)
            for i, f in enumerate(flujo_caja[1:], 1)
            if f > 0
        ]
    )
    relacion_bc = vp_ingresos / costo_sistema_total if costo_sistema_total > 0 else 0

    viabilidad_msg = "VIABLE"
    if van < 0 or relacion_bc < 1:
        viabilidad_msg = "VER AÑO RECUPERACION"

    return SolarProjectResponse(
        cliente=inputs.nombre_cliente,
        datos_entrada=inputs,
        resultados_tecnicos=TechnicalResults(
            precio_kwh_full=round(precio_kwh_full, 2),
            pago_mensual_actual=round(pago_mensual_actual, 2),
            consumo_diario_kwh=round(consumo_diario, 2),
            produccion_diaria_sfv=round(produccion_sfv_diaria, 2),
            capacidad_sistema_kwp=round(capacidad_real_kwp, 2),
            numero_modulos=num_modulos,
            area_requerida_m2=round(area_requerida, 2),
            tipo_sistema=tipo_sistema,
        ),
        resultados_financieros=FinancialResults(
            ahorro_mensual_promedio=round(ahorro_mensual, 2),
            pago_mensual_con_sfv=round(pago_residual, 2),
            porcentaje_ahorro_factura=round(porcentaje_ahorro * 100, 2),
            costo_sistema_total=round(costo_sistema_total, 2),
            costo_kwp_aplicado=round(costo_por_kwp, 2),
            van=round(van, 2),
            tir=round(tir * 100, 2),
            relacion_beneficio_costo=round(relacion_bc, 2),
            periodo_retorno_anos=round(payback, 1),
            viabilidad=viabilidad_msg,
        ),
    )
