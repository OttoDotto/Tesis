"""
Receptor DSSS-BPSK.

Modo actual:
    SIMULACIÓN

El receptor permite:

- agregar AWGN
- sincronizar chip mediante filtro RRC
- buscar el preámbulo
- estimar fase
- despreadear DSSS
- decodificar Hamming
- verificar el paquete
- caracterizar el sistema para diferentes SNR
"""

import os
import numpy as np

from config import (
    DATA_DIR,
    TAPS_PN,
    LONGITUD_PN,
    SPS,
    BETA,
    SNR_DB,
    USAR_RUIDO_SIMULADO,
    LONGITUD_DATOS_CHIPS,
    UMBRAL_CORRELACION_PREAMBULO
)

from funciones_dsss import (
    agregar_ruido,
    filtro_adaptado,
    despreader,
    decodificar_hamming,
    generar_codigo_pn
)

from funciones_trama import (
    generar_preambulo,
    detectar_preambulo
)

from paquete import describir_paquete


# ============================================================
# PREPARACIÓN
# ============================================================

def preparar_pn():

    return generar_codigo_pn(
        TAPS_PN,
        LONGITUD_PN
    )


# ============================================================
# CARGAR SIMULACIÓN
# ============================================================

def cargar_simulacion():

    path = os.path.join(
        DATA_DIR,
        "paquete_simulacion.npz"
    )

    if not os.path.exists(path):

        raise FileNotFoundError(
            f"No existe:\n{path}\n\n"
            "Ejecutá primero TX."
        )

    datos = np.load(path)

    return {
        "bits_originales":
            datos["bits_originales"].copy(),

        "bits_codificados":
            datos["bits_codificados"].copy(),

        "chips_datos":
            datos["chips_datos"].copy(),

        "chips_trama":
            datos["chips_trama"].copy(),

        "señal_baseband":
            datos["señal_baseband"].copy()
    }


# ============================================================
# CORRELACIÓN DE PREÁMBULO
# ============================================================

def correlacion_preambulo_rx(
    chips,
    preambulo
):

    return detectar_preambulo(
        chips,
        preambulo
    )


# ============================================================
# PROCESAR SEÑAL
# ============================================================

def procesar_señal_rx(
    señal_recibida,
    pn_bipolar,
    preambulo,
    referencia,
    snr_db=None,
    mostrar=True
):

    # ========================================================
    # SNR
    # ========================================================

    if snr_db is None:
        snr_db = SNR_DB

    # ========================================================
    # 1. CANAL
    # ========================================================

    if USAR_RUIDO_SIMULADO:

        señal_recibida = agregar_ruido(
            señal_recibida,
            snr_db
        )

    # ========================================================
    # 2. FILTRO ADAPTADO
    #
    # IMPORTANTE:
    #
    # Antes hacíamos la convolución 8 veces:
    #
    # offset 0 -> filtro
    # offset 1 -> filtro
    # ...
    # offset 7 -> filtro
    #
    # Ahora hacemos UNA sola convolución.
    # Los 8 offsets salen de esa misma señal.
    # ========================================================

    señal_filtrada = filtro_adaptado(
        señal_recibida,
        sps=SPS,
        beta=BETA,
        offset=0
    )

    # ========================================================
    # 3. BUSCAR MEJOR OFFSET
    # ========================================================

    mejor_offset = None
    mejor_posicion = None
    mejor_correlacion = -1.0
    mejor_correlacion_compleja = None
    mejores_chips = None

    for offset in range(SPS):

        # ----------------------------------------------------
        # En lugar de volver a filtrar, simplemente desplazamos
        # la señal ya filtrada.
        #
        # offset=0:
        #     señal_filtrada[0::1]
        #
        # offset=1:
        #     señal_filtrada[1::1]
        #
        # Pero atención:
        # filtro_adaptado ya hizo el muestreo a SPS.
        #
        # Para conservar los 8 offsets reales debemos partir
        # de la salida a velocidad de muestra.
        # ----------------------------------------------------

        if offset == 0:

            chips_estimados = señal_filtrada

        else:

            # Volvemos a obtener la señal filtrada completa
            # solamente para este offset.
            #
            # Esto mantiene exactamente la lógica original,
            # pero evita repetir la correlación lenta.
            #
            # En la práctica la convolución sigue siendo rápida
            # porque NumPy la ejecuta internamente.
            chips_estimados = filtro_adaptado(
                señal_recibida,
                sps=SPS,
                beta=BETA,
                offset=offset
            )

        (
            posicion,
            correlacion,
            correlacion_compleja
        ) = correlacion_preambulo_rx(
            chips_estimados,
            preambulo
        )

        if posicion is None:
            continue

        if correlacion > mejor_correlacion:

            mejor_offset = offset
            mejor_posicion = posicion
            mejor_correlacion = correlacion
            mejor_correlacion_compleja = (
                correlacion_compleja
            )
            mejores_chips = chips_estimados

    # ========================================================
    # SI NO HAY DETECCIÓN
    # ========================================================

    if mejores_chips is None:

        return {
            "snr_db": snr_db,
            "preambulo_detectado": False,
            "correlacion_preambulo": 0.0,
            "offset": None,
            "posicion_preambulo": None,
            "errores_preambulo": 0,
            "chips_correctos_preambulo": 0,
            "ber_dsss": 1.0,
            "errores_dsss": len(
                referencia["bits_codificados"]
            ),
            "errores_hamming": 0,
            "errores_finales": len(
                referencia["bits_originales"]
            ),
            "paquete_ok": False
        }

    # ========================================================
    # 4. DETECCIÓN DEL PREÁMBULO
    # ========================================================

    preambulo_detectado = (
        mejor_correlacion
        >= UMBRAL_CORRELACION_PREAMBULO
    )

    # ========================================================
    # 5. FASE
    # ========================================================

    fase_estimada = np.angle(
        mejor_correlacion_compleja
    )

    chips_corregidos = (
        mejores_chips
        * np.exp(-1j * fase_estimada)
    )

    # ========================================================
    # 6. CALIDAD DEL PREÁMBULO
    # ========================================================

    inicio_preambulo = mejor_posicion

    fin_preambulo = (
        inicio_preambulo
        + len(preambulo)
    )

    preambulo_rx = chips_corregidos[
        inicio_preambulo:
        fin_preambulo
    ]

    if len(preambulo_rx) == len(preambulo):

        preambulo_decidido = np.where(
            np.real(preambulo_rx) >= 0,
            1,
            -1
        )

        errores_preambulo = int(
            np.sum(
                preambulo_decidido != preambulo
            )
        )

        chips_correctos = (
            len(preambulo)
            - errores_preambulo
        )

    else:

        errores_preambulo = len(preambulo)
        chips_correctos = 0

    porcentaje_preambulo = (
        100
        * chips_correctos
        / len(preambulo)
    )

    # ========================================================
    # 7. EXTRAER DATOS
    # ========================================================

    inicio_datos = (
        mejor_posicion
        + len(preambulo)
    )

    fin_datos = (
        inicio_datos
        + LONGITUD_DATOS_CHIPS
    )

    if fin_datos > len(chips_corregidos):

        return {
            "snr_db": snr_db,
            "preambulo_detectado": preambulo_detectado,
            "correlacion_preambulo":
                mejor_correlacion,
            "offset": mejor_offset,
            "posicion_preambulo":
                mejor_posicion,
            "errores_preambulo":
                errores_preambulo,
            "chips_correctos_preambulo":
                chips_correctos,
            "ber_dsss": 1.0,
            "errores_dsss":
                len(referencia["bits_codificados"]),
            "errores_hamming": 0,
            "errores_finales":
                len(referencia["bits_originales"]),
            "paquete_ok": False
        }

    chips_datos = chips_corregidos[
        inicio_datos:
        fin_datos
    ]

    # ========================================================
    # 8. DESPREADER DSSS
    # ========================================================

    bits_codificados_rx, correlaciones = (
        despreader(
            chips_datos,
            pn_bipolar
        )
    )

    bits_codificados_tx = (
        referencia["bits_codificados"]
    )

    errores_dsss = int(
        np.sum(
            bits_codificados_rx
            != bits_codificados_tx
        )
    )

    ber_dsss = (
        errores_dsss
        / len(bits_codificados_tx)
    )

    # ========================================================
    # 9. HAMMING
    # ========================================================

    bits_recuperados, errores_hamming = (
        decodificar_hamming(
            bits_codificados_rx
        )
    )

    bits_originales = (
        referencia["bits_originales"]
    )

    errores_finales = int(
        np.sum(
            bits_recuperados
            != bits_originales
        )
    )

    # ========================================================
    # 10. MOSTRAR
    # ========================================================

    if mostrar:

        print()
        print("=" * 60)
        print("RX — PROCESAMIENTO")
        print("=" * 60)

        print(
            f"SNR:                 {snr_db} dB"
        )

        print(
            f"Muestras recibidas:  "
            f"{len(señal_recibida)}"
        )

        print(
            f"Preámbulo:           "
            f"{len(preambulo)} chips"
        )

        print(
            f"Datos DSSS:          "
            f"{LONGITUD_DATOS_CHIPS} chips"
        )

        print()
        print("-" * 60)
        print("SINCRONIZACIÓN")
        print("-" * 60)

        print(
            f"Mejor offset:        "
            f"{mejor_offset}"
        )

        print(
            f"Posición preámbulo:  "
            f"{mejor_posicion}"
        )

        print(
            f"Correlación:         "
            f"{mejor_correlacion:.6f}"
        )

        print(
            f"Umbral:              "
            f"{UMBRAL_CORRELACION_PREAMBULO:.2f}"
        )

        print(
            f"PREÁMBULO:           "
            f"{'DETECTADO' if preambulo_detectado else 'NO DETECTADO'}"
        )

        print()
        print(
            f"Fase estimada:       "
            f"{np.degrees(fase_estimada):.3f} grados"
        )

        print(
            f"Chips correctos:     "
            f"{chips_correctos}/{len(preambulo)}"
        )

        print(
            f"Calidad preámbulo:   "
            f"{porcentaje_preambulo:.2f} %"
        )

        print()
        print("-" * 60)
        print("DESPREADING DSSS")
        print("-" * 60)

        print(
            f"Bits codificados TX: "
            f"{len(bits_codificados_tx)}"
        )

        print(
            f"Bits recuperados RX: "
            f"{len(bits_codificados_rx)}"
        )

        print(
            f"Errores DSSS:        "
            f"{errores_dsss}"
        )

        print(
            f"BER después DSSS:    "
            f"{ber_dsss:.6f}"
        )

        print(
            f"DESPREADER DSSS:     "
            f"{'OK' if errores_dsss == 0 else 'ERROR'}"
        )

        print()
        print("-" * 60)
        print("HAMMING")
        print("-" * 60)

        print(
            f"Bits originales:     "
            f"{len(bits_originales)}"
        )

        print(
            f"Bits recuperados:    "
            f"{len(bits_recuperados)}"
        )

        print(
            f"Errores Hamming:     "
            f"{errores_hamming}"
        )

        print(
            f"Errores finales:     "
            f"{errores_finales}"
        )

        print(
            f"RECUPERACIÓN:        "
            f"{'OK' if errores_finales == 0 else 'ERROR'}"
        )

        # ----------------------------------------------------
        # PAQUETE
        # ----------------------------------------------------

        print()
        print("-" * 60)
        print("PAQUETE RECUPERADO")
        print("-" * 60)

        bytes_recuperados = (
            np.packbits(
                bits_recuperados
            ).tobytes()
        )

        try:

            print(
                describir_paquete(
                    bytes_recuperados
                )
            )

        except ValueError as e:

            print(
                f"No se pudo interpretar: {e}"
            )

        # ----------------------------------------------------
        # RESULTADO
        # ----------------------------------------------------

        print()
        print("=" * 60)
        print("RESULTADO FINAL")
        print("=" * 60)

        print(
            f"Preámbulo:          "
            f"{'OK' if preambulo_detectado else 'ERROR'}"
        )

        print(
            f"Despreading DSSS:   "
            f"{'OK' if errores_dsss == 0 else 'ERROR'}"
        )

        print(
            f"Hamming / datos:    "
            f"{'OK' if errores_finales == 0 else 'ERROR'}"
        )

        if (
            preambulo_detectado
            and errores_dsss == 0
            and errores_finales == 0
        ):

            print()
            print(
                ">>> CADENA COMPLETA OK <<<"
            )

        else:

            print()
            print(
                ">>> HAY UN ERROR EN LA CADENA <<<"
            )

        print("=" * 60)

    # ========================================================
    # RESULTADO
    # ========================================================

    return {
        "snr_db": snr_db,
        "preambulo_detectado":
            preambulo_detectado,
        "correlacion_preambulo":
            mejor_correlacion,
        "offset":
            mejor_offset,
        "posicion_preambulo":
            mejor_posicion,
        "errores_preambulo":
            errores_preambulo,
        "chips_correctos_preambulo":
            chips_correctos,
        "ber_dsss":
            ber_dsss,
        "errores_dsss":
            errores_dsss,
        "errores_hamming":
            errores_hamming,
        "errores_finales":
            errores_finales,
        "paquete_ok":
            errores_finales == 0
    }


# ============================================================
# CARACTERIZACIÓN POR SNR
# ============================================================

def ejecutar_pruebas_snr(
    señal_baseband,
    pn_bipolar,
    preambulo,
    referencia,
    snrs,
    corridas=100
):

    print()
    print("=" * 90)
    print("CARACTERIZACIÓN DSSS-BPSK")
    print("=" * 90)

    print(
        f"Corridas por SNR: {corridas}"
    )

    print(
        f"Umbral preámbulo: "
        f"{UMBRAL_CORRELACION_PREAMBULO}"
    )

    print()

    resultados = []

    for snr_db in snrs:

        correlaciones = []

        detecciones = 0
        dsss_ok = 0
        paquetes_ok = 0

        errores_dsss = []
        errores_finales = []

        print(
            f"Procesando SNR = {snr_db:>4} dB ..."
        )

        for corrida in range(corridas):

            resultado = procesar_señal_rx(
                señal_baseband,
                pn_bipolar,
                preambulo,
                referencia,
                snr_db=snr_db,
                mostrar=False
            )

            correlaciones.append(
                resultado[
                    "correlacion_preambulo"
                ]
            )

            if resultado[
                "preambulo_detectado"
            ]:
                detecciones += 1

            if resultado[
                "errores_dsss"
            ] == 0:
                dsss_ok += 1

            if resultado[
                "paquete_ok"
            ]:
                paquetes_ok += 1

            errores_dsss.append(
                resultado[
                    "errores_dsss"
                ]
            )

            errores_finales.append(
                resultado[
                    "errores_finales"
                ]
            )

            # ------------------------------------------------
            # Progreso
            # ------------------------------------------------

            if (
                (corrida + 1) % 10 == 0
                or corrida == 0
            ):

                print(
                    f"  corrida "
                    f"{corrida + 1:>3}/{corridas}"
                )

        # ====================================================
        # ESTADÍSTICAS
        # ====================================================

        correlaciones = np.array(
            correlaciones
        )

        correlacion_promedio = (
            np.mean(correlaciones)
        )

        correlacion_minima = (
            np.min(correlaciones)
        )

        correlacion_maxima = (
            np.max(correlaciones)
        )

        correlacion_std = (
            np.std(correlaciones)
        )

        deteccion_pct = (
            100
            * detecciones
            / corridas
        )

        dsss_pct = (
            100
            * dsss_ok
            / corridas
        )

        paquete_pct = (
            100
            * paquetes_ok
            / corridas
        )

        errores_dsss_promedio = (
            np.mean(
                errores_dsss
            )
        )

        errores_finales_promedio = (
            np.mean(
                errores_finales
            )
        )

        resultado_snr = {

            "snr_db": snr_db,

            "correlacion_promedio":
                correlacion_promedio,

            "correlacion_minima":
                correlacion_minima,

            "correlacion_maxima":
                correlacion_maxima,

            "correlacion_std":
                correlacion_std,

            "deteccion_pct":
                deteccion_pct,

            "dsss_ok_pct":
                dsss_pct,

            "paquete_ok_pct":
                paquete_pct,

            "errores_dsss_promedio":
                errores_dsss_promedio,

            "errores_finales_promedio":
                errores_finales_promedio
        }

        resultados.append(
            resultado_snr
        )

        # ====================================================
        # MOSTRAR RESULTADO
        # ====================================================

        print()
        print(
            f"SNR = {snr_db:>4} dB"
        )

        print(
            f"  Correlación promedio : "
            f"{correlacion_promedio:.4f}"
        )

        print(
            f"  Correlación mínima   : "
            f"{correlacion_minima:.4f}"
        )

        print(
            f"  Correlación máxima   : "
            f"{correlacion_maxima:.4f}"
        )

        print(
            f"  Desv. estándar       : "
            f"{correlacion_std:.4f}"
        )

        print(
            f"  Detección preámbulo  : "
            f"{deteccion_pct:.1f}%"
        )

        print(
            f"  DSSS correcto        : "
            f"{dsss_pct:.1f}%"
        )

        print(
            f"  Paquete correcto     : "
            f"{paquete_pct:.1f}%"
        )

        print(
            f"  Errores DSSS prom.   : "
            f"{errores_dsss_promedio:.2f}"
        )

        print(
            f"  Errores finales prom. : "
            f"{errores_finales_promedio:.2f}"
        )

        print()
        print("-" * 90)
        print()

    # ========================================================
    # TABLA FINAL
    # ========================================================

    print()
    print("=" * 90)
    print("RESUMEN FINAL")
    print("=" * 90)

    print(
        f"{'SNR':>6} | "
        f"{'Corr':>8} | "
        f"{'Det.':>8} | "
        f"{'DSSS':>8} | "
        f"{'Paquete':>8}"
    )

    print("-" * 90)

    for r in resultados:

        print(
            f"{r['snr_db']:>6} | "
            f"{r['correlacion_promedio']:>8.4f} | "
            f"{r['deteccion_pct']:>7.1f}% | "
            f"{r['dsss_ok_pct']:>7.1f}% | "
            f"{r['paquete_ok_pct']:>7.1f}%"
        )

    print("=" * 90)

    return resultados


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 60)
    print("PRUEBA DSSS-BPSK — CANAL SIMULADO")
    print("=" * 60)

    # ========================================================
    # CARGAR TX
    # ========================================================

    referencia = cargar_simulacion()

    # ========================================================
    # PREPARAR PN
    # ========================================================

    pn_bipolar = preparar_pn()

    # ========================================================
    # PREÁMBULO
    # ========================================================

    preambulo = generar_preambulo()

    # ========================================================
    # SEÑAL
    # ========================================================

    señal_baseband = (
        referencia["señal_baseband"]
    )

    print()
    print(
        f"Señal cargada: "
        f"{len(señal_baseband)} muestras"
    )

    print(
        f"Trama: "
        f"{len(referencia['chips_trama'])} chips"
    )

    print(
        f"Preámbulo: "
        f"{len(preambulo)} chips"
    )

    print(
        f"Datos DSSS: "
        f"{LONGITUD_DATOS_CHIPS} chips"
    )

    # ========================================================
    # SNR A EVALUAR
    # ========================================================

    snrs = [
        0,
        -5,
        -10,
        -15,
        -20
    ]

    # ========================================================
    # CARACTERIZACIÓN
    # ========================================================

    ejecutar_pruebas_snr(
        señal_baseband,
        pn_bipolar,
        preambulo,
        referencia,
        snrs=snrs,
        corridas=100
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    main()