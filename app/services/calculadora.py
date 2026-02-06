import math
from decimal import ROUND_HALF_UP, Decimal
from typing import List, Optional

from app.models.schemas import (
    EconomicScenario,
    SolarInput,
    SolarProjectResponse,
    SystemParameters,
    TechnicalSpecs,
    TipoTarifa,
)

# --- CONSTANTES ---
FACTOR_RENDIMIENTO_EXCEL = Decimal("0.963636364")
INFLACION_ENERGIA = Decimal("0.039")
INFLACION_IPP = Decimal("0.039")
FACTOR_DEGRADACION_PAGO = Decimal("1.004")
PORC_MANTENIMIENTO_CAPEX = Decimal("0.02")
FACTOR_AJUSTE_MANTENIMIENTO = Decimal("2.0")
FACTOR_PRECIO_T1 = Decimal("0.8")
PRECIO_T2_FIJO = Decimal("165.0")

# Costos Sistema
COSTO_RESIDENCIAL = Decimal("4500000")
COSTO_COMERCIAL = Decimal("3800000")
COSTO_INDUSTRIAL = Decimal("3500000")

# Costos Inversores (Reemplazo Año 12)
CAPACIDAD_INVERSOR_KW = Decimal("1.2")  # CALCULOS!F13 (divisor)
COSTO_UNITARIO_INVERSOR = Decimal("1100000")  # CALCULOS!F14
ANO_REEMPLAZO_INVERSOR = 12


# --- UTILIDADES ---
def to_decimal(val) -> Decimal:
    return Decimal(str(val))


def round_money(val: Decimal) -> Decimal:
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def round_decimal(val: Decimal, digits: int) -> Decimal:
    format_str = "0." + "0" * digits
    return val.quantize(Decimal(format_str), rounding=ROUND_HALF_UP)


def calcular_npv(rate: float, values: List[Decimal]) -> float:
    total = 0.0
    for i, val in enumerate(values):
        total += float(val) / ((1 + rate) ** i)
    return total


def calcular_irr(values: List[Decimal], guess: float = 0.1) -> float:
    values_float = [float(v) for v in values]
    max_iter = 100
    tol = 1e-7
    rate = guess
    for _ in range(max_iter):
        npv = 0.0
        for i, val in enumerate(values_float):
            npv += val / ((1 + rate) ** i)
        npv_derivative = 0.0
        for i, val in enumerate(values_float):
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


# --- MOTORES DE CÁLCULO ---


def calcular_fisico(
    inputs: SolarInput, params: SystemParameters
) -> (TechnicalSpecs, dict):
    """
    Calcula solo la parte física (módulos, producción, área) y precios base.
    """
    consumo_mes = to_decimal(inputs.consumo_energia_kwh_mes)
    precio_base = to_decimal(inputs.precio_energia_base)
    pct_contrib = to_decimal(inputs.contribucion_porcentaje) / 100
    pct_impuesto = to_decimal(inputs.impuesto_ap_porcentaje) / 100
    pct_cobertura = to_decimal(inputs.cobertura_objetivo_porcentaje) / 100

    # Precio Full y Pago Actual
    factor_tarifas = Decimal("1") + pct_contrib + pct_impuesto
    precio_kwh_full_calc = round_money(precio_base * factor_tarifas)
    pago_mensual_actual_calc = round_money(precio_kwh_full_calc * consumo_mes)

    # Producción
    consumo_diario = consumo_mes / Decimal("30")
    produccion_sfv_diaria_raw = (
        consumo_diario * pct_cobertura * FACTOR_RENDIMIENTO_EXCEL
    )
    produccion_sfv_diaria = round_decimal(produccion_sfv_diaria_raw, 2)

    # Capacidad Teórica
    horas_sol = to_decimal(params.horas_sol_pico)
    capacidad_teorica_kwp = produccion_sfv_diaria / horas_sol

    # Módulos y Capacidad Real
    potencia_mod_watts = to_decimal(params.potencia_modulo_watts)
    factor_potencia = Decimal("1000") / potencia_mod_watts
    num_modulos = math.ceil(float(capacidad_teorica_kwp * factor_potencia))
    capacidad_instalada_kwp = (Decimal(num_modulos) * potencia_mod_watts) / Decimal(
        "1000"
    )

    # Área
    factor_area = to_decimal(params.factor_area_modulo)
    factor_espacio = to_decimal(params.factor_espaciamiento)
    area_requerida = (Decimal(num_modulos) * factor_area * factor_espacio).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )

    # Reemplazo de Inversores (Cálculo Base)
    # CALCULOS!F13: REDONDEAR.MAS(CapacidadTeorica / 1.2)
    num_inversores = math.ceil(float(capacidad_teorica_kwp / CAPACIDAD_INVERSOR_KW))
    costo_reemplazo_inversores_base = Decimal(num_inversores) * COSTO_UNITARIO_INVERSOR

    specs = TechnicalSpecs(
        precio_kwh_full=float(precio_kwh_full_calc),
        pago_mensual_actual=float(pago_mensual_actual_calc),
        consumo_diario_kwh=float(round_decimal(consumo_diario, 2)),
        produccion_diaria_sfv=float(produccion_sfv_diaria),
        capacidad_sistema_kwp=float(round_decimal(capacidad_teorica_kwp, 2)),
        capacidad_instalada_kwp=float(round_decimal(capacidad_instalada_kwp, 2)),
        numero_modulos=num_modulos,
        area_requerida_m2=float(area_requerida),
    )

    # Contexto para cálculos económicos
    context = {
        "precio_base": precio_base,
        "precio_kwh_full_calc": precio_kwh_full_calc,
        "produccion_sfv_diaria": produccion_sfv_diaria,
        "pago_mensual_actual_calc": pago_mensual_actual_calc,
        "capacidad_instalada_kwp": capacidad_instalada_kwp,
        "costo_reemplazo_inversores_base": costo_reemplazo_inversores_base,
    }
    return specs, context


def calcular_economico(
    inputs: SolarInput,
    params: SystemParameters,
    context: dict,
    tarifa_forzada: Optional[TipoTarifa] = None,
    es_automatico: bool = True,
) -> EconomicScenario:
    """
    Calcula un escenario financiero completo.
    """
    capacidad_instalada_kwp = context["capacidad_instalada_kwp"]
    cap_float = float(capacidad_instalada_kwp)
    cap_mostrar = round(cap_float, 2)

    # 1. Determinación de Tarifa y Costo
    tipo_sistema = ""
    costo_por_kwp = Decimal("0")
    explicacion = ""
    nombre_escenario = ""

    if tarifa_forzada:
        nombre_escenario = f"Usuario: {tarifa_forzada.value.capitalize()}"
        if tarifa_forzada == TipoTarifa.RESIDENCIAL:
            tipo_sistema = "3-10 kWp (Residencial)"
            costo_por_kwp = COSTO_RESIDENCIAL
        elif tarifa_forzada == TipoTarifa.COMERCIAL:
            tipo_sistema = "10-40 kWp (Comercial)"
            costo_por_kwp = COSTO_COMERCIAL
        elif tarifa_forzada == TipoTarifa.INDUSTRIAL:
            tipo_sistema = "> 40 kWp (Industrial)"
            costo_por_kwp = COSTO_INDUSTRIAL
        explicacion = f"Forzado manualmente a tarifa {tarifa_forzada.value}."

    else:
        # Lógica Automática
        nombre_escenario = "Automático"
        if cap_float > 40:
            tipo_sistema = "> 40 kWp (Industrial)"
            costo_por_kwp = COSTO_INDUSTRIAL
            explicacion = f"Capacidad ({cap_mostrar} kWp) > 40."
        elif cap_float >= 10:
            tipo_sistema = "10-40 kWp (Comercial)"
            costo_por_kwp = COSTO_COMERCIAL
            explicacion = f"Capacidad ({cap_mostrar} kWp) entre 10 y 40."
        else:
            tipo_sistema = "3-10 kWp (Residencial)"
            costo_por_kwp = COSTO_RESIDENCIAL
            explicacion = f"Capacidad ({cap_mostrar} kWp) < 10."

    # Costo Total
    costo_base = capacidad_instalada_kwp * costo_por_kwp
    costo_sistema_total = Decimal(math.ceil(float(costo_base) / 1_000_000) * 1_000_000)

    # 2. Ahorros
    precio_base = context["precio_base"]
    precio_kwh_full_calc = context["precio_kwh_full_calc"]
    produccion_sfv_diaria = context["produccion_sfv_diaria"]

    precio_t1_calc = round_money(precio_base * FACTOR_PRECIO_T1)
    precio_t2_calc = PRECIO_T2_FIJO

    p_auto = to_decimal(params.porc_autoconsumo_directo)
    p_t1 = to_decimal(params.porc_excedentes_t1)
    p_t2 = to_decimal(params.porc_excedentes_t2)

    ahorro_diario = (
        (produccion_sfv_diaria * p_auto * precio_kwh_full_calc)
        + (produccion_sfv_diaria * p_t1 * precio_t1_calc)
        + (produccion_sfv_diaria * p_t2 * precio_t2_calc)
    )
    ahorro_mensual_calc = round_money(ahorro_diario * Decimal("30"))

    pago_mensual_actual_calc = context["pago_mensual_actual_calc"]
    pago_residual = pago_mensual_actual_calc - ahorro_mensual_calc
    if pago_residual < 0:
        pago_residual = Decimal("0")

    pct_ahorro = Decimal("0")
    if pago_mensual_actual_calc > 0:
        pct_ahorro = ahorro_mensual_calc / pago_mensual_actual_calc

    # 3. Flujo de Caja y VP Egresos
    tasa_desc = inputs.tasa_descuento_porcentaje / 100
    flujo_caja = [-costo_sistema_total]

    # VP Egresos comienza con la inversión inicial
    vp_egresos_totales = float(costo_sistema_total)
    vp_ingresos_totales = 0.0

    pago_sin_sfv_anual = pago_mensual_actual_calc * 12
    pago_con_sfv_anual = pago_residual * 12
    mant_anual_base = (
        costo_sistema_total * PORC_MANTENIMIENTO_CAPEX
    ) * FACTOR_AJUSTE_MANTENIMIENTO

    costo_reemplazo_base = context["costo_reemplazo_inversores_base"]

    for ano in range(1, params.anos_proyeccion + 1):
        inf_e = (Decimal("1") + INFLACION_ENERGIA) ** (ano - 1)
        inf_ipp = (Decimal("1") + INFLACION_IPP) ** ano
        deg = FACTOR_DEGRADACION_PAGO ** (ano - 1)

        c_sin = pago_sin_sfv_anual * inf_e  # Ahorro Bruto (Ingreso)
        c_con = pago_con_sfv_anual * inf_e * deg  # Costo residual

        ahorro_ano = c_sin - c_con  # Ingreso Neto

        # Egresos: Mantenimiento + Reemplazos
        egreso_total_ano = mant_anual_base * inf_ipp

        # Reemplazo Inversor (Año 12)
        if ano == ANO_REEMPLAZO_INVERSOR:
            # En el Excel, el reemplazo se infla con 3.9% anual desde el año 0
            # F14 * (1+0.039)^12
            factor_inf_reemplazo = (Decimal("1") + INFLACION_ENERGIA) ** ano
            egreso_reemplazo = costo_reemplazo_base * factor_inf_reemplazo
            egreso_total_ano += egreso_reemplazo

        flujo_neto = ahorro_ano - egreso_total_ano
        flujo_caja.append(flujo_neto)

        # Acumular VP para B/C Ratio
        # VP Egresos = Suma(Egreso_n / (1+i)^n)
        vp_egresos_totales += float(egreso_total_ano) / ((1 + tasa_desc) ** ano)
        # VP Ingresos = Suma(Ingreso_n / (1+i)^n)
        vp_ingresos_totales += float(ahorro_ano) / ((1 + tasa_desc) ** ano)

    # 4. Indicadores
    van = calcular_npv(tasa_desc, flujo_caja)
    try:
        tir = calcular_irr(flujo_caja)
    except:
        tir = 0.0

    # Payback
    acumulado = -float(costo_sistema_total)
    payback = float(params.anos_proyeccion)
    flujos_float = [float(f) for f in flujo_caja]
    for i, f in enumerate(flujos_float[1:], 1):
        acumulado += f
        if acumulado >= 0:
            previo = acumulado - f
            payback = (i - 1) + (abs(previo) / f)
            break

    # B/C Ratio Corregido: VP(Ingresos) / VP(Todos los Egresos)
    bc = vp_ingresos_totales / vp_egresos_totales if vp_egresos_totales > 0 else 0.0

    viabilidad = "VIABLE"
    if van < 0 or bc < 1:
        viabilidad = "VER AÑO RECUPERACION"

    return EconomicScenario(
        nombre_escenario=nombre_escenario,
        tipo_sistema_detectado=tipo_sistema,
        explicacion=explicacion,
        costo_sistema_total=float(costo_sistema_total),
        costo_kwp_aplicado=float(costo_por_kwp),
        ahorro_mensual_promedio=float(ahorro_mensual_calc),
        pago_mensual_con_sfv=float(pago_residual),
        porcentaje_ahorro_factura=float(round_decimal(pct_ahorro * 100, 2)),
        van=float(round_decimal(to_decimal(van), 2)),
        tir=float(round_decimal(to_decimal(tir * 100), 2)),
        relacion_beneficio_costo=float(round_decimal(to_decimal(bc), 2)),
        periodo_retorno_anos=float(round(payback, 1)),
        viabilidad=viabilidad,
    )


def calcular_proyecto(
    inputs: SolarInput, params: SystemParameters
) -> SolarProjectResponse:

    # 1. Calcular Física (Una sola vez)
    specs, context = calcular_fisico(inputs, params)

    # 2. Escenario Automático (La verdad)
    escenario_auto = calcular_economico(
        inputs, params, context, tarifa_forzada=None, es_automatico=True
    )

    # 3. Escenario Usuario (Si se pide)
    escenario_user = None
    if inputs.forzar_tipo_tarifa:
        escenario_user = calcular_economico(
            inputs,
            params,
            context,
            tarifa_forzada=inputs.forzar_tipo_tarifa,
            es_automatico=False,
        )

    return SolarProjectResponse(
        cliente=inputs.nombre_cliente,
        datos_entrada=inputs,
        especificaciones_tecnicas=specs,
        escenario_automatico=escenario_auto,
        escenario_usuario=escenario_user,
    )
