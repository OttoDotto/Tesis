import os
import time
import numpy as np

from config import (
    DATA_DIR,
    TAPS_PN,
    LONGITUD_PN,
    SPS,
    BETA,
    LONGITUD_DATOS_CHIPS,
    UMBRAL_CORRELACION_PREAMBULO,
    USAR_SDR,
    SDR_ARGS,
    CANAL_SDR,
    FREQ_CENTRAL,
    SAMPLE_RATE,
    GANANCIA_RX,
    ANTENA_RX,
    MUESTRAS_RX_POR_TRAMA,
    SAMPLES_OVERLAP
)

from funciones_dsss import (
    filtro_rrc,
    despreader,
    decodificar_hamming,
    generar_codigo_pn
)

from funciones_trama import (
    generar_preambulo,
    detectar_preambulo
)

from sdr_utils import abrir_sdr_rx, recibir_muestras, cerrar_sdr_rx
from paquete import describir_paquete


def preparar_pn():
    return generar_codigo_pn(TAPS_PN, LONGITUD_PN)


def procesar_bloque_rx(señal_recibida, pn_bipolar, preambulo, h_rrc):
    # 1. FILTRO ADAPTADO: Una sola convolución para todo el bloque
    filtrada_completa = np.convolve(señal_recibida, h_rrc, mode='same')

    mejor_offset = None
    mejor_posicion = None
    mejor_correlacion = -1.0
    mejor_correlacion_compleja = None
    mejores_chips = None

    # 2. SUBMUESTREO RÁPIDO: Simples slices sobre la señal filtrada
    for offset in range(SPS):
        chips_estimados = filtrada_completa[offset::SPS]

        posicion, correlacion, correlacion_compleja = detectar_preambulo(
            chips_estimados,
            preambulo
        )

        if posicion is None:
            continue

        if correlacion > mejor_correlacion:
            mejor_offset = offset
            mejor_posicion = posicion
            mejor_correlacion = correlacion
            mejor_correlacion_compleja = correlacion_compleja
            mejores_chips = chips_estimados

    # Validar Detección
    if mejores_chips is None or mejor_correlacion < UMBRAL_CORRELACION_PREAMBULO:
        return False, None

    # 3. Corrección de Fase BPSK
    fase_estimada = np.angle(mejor_correlacion_compleja)
    chips_corregidos = mejores_chips * np.exp(-1j * fase_estimada)

    # 4. Extracción de Chips de Datos
    inicio_datos = mejor_posicion + len(preambulo)
    fin_datos = inicio_datos + LONGITUD_DATOS_CHIPS

    if fin_datos > len(chips_corregidos):
        return False, None

    chips_datos = chips_corregidos[inicio_datos:fin_datos]

    # 5. Despreading DSSS y Hamming
    bits_codificados_rx, _ = despreader(chips_datos, pn_bipolar)
    bits_recuperados, errores_hamming = decodificar_hamming(bits_codificados_rx)
    bytes_recuperados = np.packbits(bits_recuperados).tobytes()

    return True, {
        "correlacion": mejor_correlacion,
        "offset": mejor_offset,
        "fase_deg": np.degrees(fase_estimada),
        "errores_hamming": errores_hamming,
        "bytes": bytes_recuperados
    }


def ejecutar_rx_sdr():
    pn_bipolar = preparar_pn()
    preambulo = generar_preambulo()
    
    # Precalculamos el filtro RRC una única vez en memoria
    h_rrc = filtro_rrc(BETA, SPS, 65)

    print("\n" + "=" * 60)
    print("RX SDR — TIEMPO REAL (OPTIMIZADO)")
    print("=" * 60)

    sdr, rx_stream = abrir_sdr_rx(
        args=SDR_ARGS,
        canal=CANAL_SDR,
        freq_hz=FREQ_CENTRAL,
        sample_rate=SAMPLE_RATE,
        ganancia_db=GANANCIA_RX,
        antena=ANTENA_RX
    )

    buffer_overlap = np.array([], dtype=np.complex64)
    paquetes_recibidos = 0

    try:
        print("\nEsperando tramas en la frecuencia configurada (Ctrl+C para salir)...\n")

        while True:
            muestras_nuevas = recibir_muestras(sdr, rx_stream, MUESTRAS_RX_POR_TRAMA)

            if len(muestras_nuevas) == 0:
                continue

            señal_total = np.concatenate([buffer_overlap, muestras_nuevas])

            detectado, info = procesar_bloque_rx(señal_total, pn_bipolar, preambulo, h_rrc)

            if detectado:
                paquetes_recibidos += 1
                print("-" * 60)
                print(f"¡TRAMA #{paquetes_recibidos} DETECTADA!")
                print(f"  Correlación : {info['correlacion']:.4f}")
                print(f"  Offset      : {info['offset']}")
                print(f"  Fase Est.   : {info['fase_deg']:.2f}°")
                print(f"  Err. Hamming: {info['errores_hamming']}")
                try:
                    print(f"  Contenido   : {describir_paquete(info['bytes'])}")
                except Exception:
                    print(f"  Contenido Hex: {info['bytes'].hex()}")
                print("-" * 60 + "\n")

            buffer_overlap = señal_total[-SAMPLES_OVERLAP:]

    except KeyboardInterrupt:
        print("\nRX SDR detenido por el usuario.")
    finally:
        if sdr is not None:
            cerrar_sdr_rx(sdr, rx_stream)


if __name__ == "__main__":
    ejecutar_rx_sdr()