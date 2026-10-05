import numpy as np
from config import (
    PREAMBULO,
    GUARDA,
    MUESTRAS_POR_BIT,
    SAMPLE_RATE
)
from paquete import TAMAÑO_PAQUETE_BYTES

# Constantes derivadas
CANTIDAD_BITS_DATOS = TAMAÑO_PAQUETE_BYTES * 8

PREAMBULO_SIMBOLOS = np.array(
    [1.0 if bit == "1" else -1.0 for bit in PREAMBULO],
    dtype=np.float32
)

# ============================================================
# FUNCIONES TX
# ============================================================

def generar_bpsk(bits):
    simbolos = np.array(
        [1.0 if bit == "1" else -1.0 for bit in bits],
        dtype=np.float32
    )
    return np.repeat(simbolos, MUESTRAS_POR_BIT)


# ============================================================
# FUNCIONES RX
# ============================================================

def buscar_preambulo(muestras):
    mejor_correlacion = -1.0
    mejor_inicio = None
    referencia = PREAMBULO_SIMBOLOS.astype(np.complex64)
    longitud = len(PREAMBULO)

    for offset in range(MUESTRAS_POR_BIT):
        muestras_offset = muestras[offset:]
        cantidad_simbolos = len(muestras_offset) // MUESTRAS_POR_BIT

        if cantidad_simbolos < longitud:
            continue

        muestras_offset = muestras_offset[:cantidad_simbolos * MUESTRAS_POR_BIT]
        bloques = muestras_offset.reshape(cantidad_simbolos, MUESTRAS_POR_BIT)
        simbolos = np.mean(bloques, axis=1)

        correlaciones = np.correlate(simbolos, referencia, mode="valid")
        energia_rx = np.convolve(
            np.abs(simbolos) ** 2,
            np.ones(longitud, dtype=np.float32),
            mode="valid"
        )
        energia_ref = np.sum(np.abs(referencia) ** 2)
        denominador = np.sqrt(energia_rx * energia_ref)

        correlaciones_normalizadas = np.abs(correlaciones) / np.maximum(denominador, 1e-12)
        indice = np.argmax(correlaciones_normalizadas)
        correlacion = correlaciones_normalizadas[indice]

        if correlacion > mejor_correlacion:
            mejor_correlacion = correlacion
            mejor_inicio = offset + indice * MUESTRAS_POR_BIT

    if mejor_inicio is None:
        return None, None

    return mejor_correlacion, mejor_inicio


def estimar_offset_frecuencia(simbolos_preambulo):
    corregidos = simbolos_preambulo * PREAMBULO_SIMBOLOS
    fases = np.unwrap(np.angle(corregidos))
    indices = np.arange(len(fases), dtype=np.float64)
    pesos = np.maximum(np.abs(corregidos) ** 2, 1e-12)

    pendiente, fase_inicial = np.polyfit(indices, fases, 1, w=pesos)
    tasa_simbolos = SAMPLE_RATE / MUESTRAS_POR_BIT
    frecuencia_offset = pendiente * tasa_simbolos / (2.0 * np.pi)

    return pendiente, fase_inicial, frecuencia_offset


def analizar_trama(muestras, inicio):
    cantidad_bits = len(PREAMBULO) + CANTIDAD_BITS_DATOS + len(GUARDA)
    cantidad_muestras = cantidad_bits * MUESTRAS_POR_BIT
    fin = inicio + cantidad_muestras

    if inicio < 0 or fin > len(muestras):
        return None

    trama = muestras[inicio:fin]
    bloques = trama.reshape(cantidad_bits, MUESTRAS_POR_BIT)
    simbolos = np.mean(bloques, axis=1)
    
    n_preambulo = len(PREAMBULO)
    simbolos_preambulo = simbolos[:n_preambulo]

    pendiente_fase, fase_inicial, frecuencia_offset = estimar_offset_frecuencia(simbolos_preambulo)
    pendiente_por_muestra = pendiente_fase / MUESTRAS_POR_BIT
    indices = np.arange(len(trama), dtype=np.float64)
    
    fase = fase_inicial + pendiente_por_muestra * indices
    trama_corregida = trama * np.exp(-1j * fase)
    bloques_corregidos = trama_corregida.reshape(cantidad_bits, MUESTRAS_POR_BIT)
    simbolos_corregidos = np.mean(bloques_corregidos, axis=1)

    simbolos_preambulo = simbolos_corregidos[:n_preambulo]
    simbolos_datos = simbolos_corregidos[n_preambulo : n_preambulo + CANTIDAD_BITS_DATOS]
    simbolos_guarda = simbolos_corregidos[n_preambulo + CANTIDAD_BITS_DATOS:]

    bits_preambulo = "".join("1" if np.real(s) >= 0 else "0" for s in simbolos_preambulo)
    bits_datos = "".join("1" if np.real(s) >= 0 else "0" for s in simbolos_datos)
    bits_guarda = "".join("1" if np.real(s) >= 0 else "0" for s in simbolos_guarda)

    errores_preambulo = sum(a != b for a, b in zip(bits_preambulo, PREAMBULO))

    return {
        "bits_preambulo": bits_preambulo,
        "bits_datos": bits_datos,
        "bits_guarda": bits_guarda,
        "errores_preambulo": errores_preambulo,
        "pendiente_fase": pendiente_fase,
        "fase_inicial": fase_inicial,
        "frecuencia_offset": frecuencia_offset
    }