import numpy as np
from config import (
    PREAMBULO,
    GUARDA,
    MUESTRAS_POR_BIT,
    SAMPLE_RATE
)
from paquete import TAMAÑO_PAQUETE_BYTES
from funciones_dsss import generar_codigo_pn, ensanchar, despreader

# Constantes derivadas
CANTIDAD_BITS_DATOS = TAMAÑO_PAQUETE_BYTES * 8

# Parámetros del código PN clásico (LFSR)
TAPS_PN = [6, 1]
LONGITUD_PN = 63
PN_BIPOLAR = generar_codigo_pn(TAPS_PN, LONGITUD_PN)

# Cantidad total de chips de datos ensanchados
CANTIDAD_CHIPS_DATOS = CANTIDAD_BITS_DATOS * LONGITUD_PN

PREAMBULO_SIMBOLOS = np.array(
    [1.0 if bit == "1" else -1.0 for bit in PREAMBULO],
    dtype=np.float32
)

GUARDA_SIMBOLOS = np.array(
    [1.0 if bit == "1" else -1.0 for bit in GUARDA],
    dtype=np.float32
)

# ============================================================
# FUNCIONES TX (DSSS)
# ============================================================

def generar_trama_dsss(bits_datos):
    # 1. Ensanchar los bits de datos utilizando el código PN clásico
    chips_datos = ensanchar(bits_datos, PN_BIPOLAR)
    
    # 2. Construir la trama: Preámbulo (puro) + Chips de Datos + Guarda (puro)
    trama_bipolar = np.concatenate((PREAMBULO_SIMBOLOS, chips_datos.astype(np.float32), GUARDA_SIMBOLOS))
    
    # 3. Aplicar sobremuestreo (MUESTRAS_POR_BIT) a toda la forma de onda
    return np.repeat(trama_bipolar, MUESTRAS_POR_BIT)


# ============================================================
# FUNCIONES RX
# ============================================================

def buscar_preambulo(muestras):
    muestras = muestras - np.mean(muestras)
    
    mejor_correlacion = -1.0
    mejor_inicio = None
    referencia = PREAMBULO_SIMBOLOS.astype(np.complex64)
    longitud = len(PREAMBULO)

    # Evita el Overrun (OOOO) procesando solo el inicio de la ráfaga
    N_fft = 1024
    muestras_fft = muestras[:N_fft]
    cuadrada = muestras_fft ** 2
    cuadrada = cuadrada - np.mean(cuadrada)
    
    ventana = np.blackman(len(cuadrada))
    espectro = np.fft.fft(cuadrada * ventana)
    freqs = np.fft.fftfreq(len(cuadrada), d=1.0/SAMPLE_RATE)
    
    espectro_abs = np.abs(espectro)
    frecuencia_limite = 40000 
    espectro_abs[np.abs(freqs) > frecuencia_limite] = 0
    espectro_abs[0] = 0 
    
    f_shift_grueso = freqs[np.argmax(espectro_abs)] / 2.0

    t = np.arange(len(muestras)) / SAMPLE_RATE
    muestras_corregidas = muestras * np.exp(-1j * 2 * np.pi * f_shift_grueso * t)


    for offset in range(MUESTRAS_POR_BIT):
        muestras_offset = muestras_corregidas[offset:]
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
        return None, None, None

    return mejor_correlacion, mejor_inicio, f_shift_grueso


def estimar_offset_frecuencia(simbolos_preambulo):
    corregidos = simbolos_preambulo * PREAMBULO_SIMBOLOS
    fases = np.unwrap(np.angle(corregidos))
    indices = np.arange(len(fases), dtype=np.float64)
    pesos = np.maximum(np.abs(corregidos) ** 2, 1e-12)

    pendiente, fase_inicial = np.polyfit(indices, fases, 1, w=pesos)
    tasa_simbolos = SAMPLE_RATE / MUESTRAS_POR_BIT
    frecuencia_offset = pendiente * tasa_simbolos / (2.0 * np.pi)

    return pendiente, fase_inicial, frecuencia_offset


def analizar_trama(muestras, inicio, f_shift_grueso):
    cantidad_simbolos_totales = len(PREAMBULO) + CANTIDAD_CHIPS_DATOS + len(GUARDA)
    cantidad_muestras = cantidad_simbolos_totales * MUESTRAS_POR_BIT
    fin = inicio + cantidad_muestras

    if inicio < 0 or fin > len(muestras):
        return None

    trama = muestras[inicio:fin]
    
    t = np.arange(len(trama)) / SAMPLE_RATE
    trama = trama * np.exp(-1j * 2 * np.pi * f_shift_grueso * t)
    
    bloques = trama.reshape(cantidad_simbolos_totales, MUESTRAS_POR_BIT)
    simbolos = np.mean(bloques, axis=1)
    
    n_preambulo = len(PREAMBULO)
    simbolos_preambulo = simbolos[:n_preambulo]

    pendiente_fase, fase_inicial, frecuencia_offset_fina = estimar_offset_frecuencia(simbolos_preambulo)
    pendiente_por_muestra = pendiente_fase / MUESTRAS_POR_BIT
    indices = np.arange(len(trama), dtype=np.float64)
    
    fase = fase_inicial + pendiente_por_muestra * indices
    trama_corregida = trama * np.exp(-1j * fase)
    bloques_corregidos = trama_corregida.reshape(cantidad_simbolos_totales, MUESTRAS_POR_BIT)
    simbolos_corregidos = np.mean(bloques_corregidos, axis=1)

    simbolos_preambulo = simbolos_corregidos[:n_preambulo]
    simbolos_chips_datos = simbolos_corregidos[n_preambulo : n_preambulo + CANTIDAD_CHIPS_DATOS]

    # --- TRUCO DSP PARA PLANCHAR EL DRIFT DE FASE ---
    # Al elevar al cuadrado se destruye la modulación de datos y el código PN.
    # Lo único que sobrevive es el ruido y la rotación de fase residual.
    chips_cuadrado = simbolos_chips_datos ** 2
    fase_error_doble = np.unwrap(np.angle(chips_cuadrado))
    
    # Ajustar una recta para extraer la pendiente de error e ignorar el ruido
    idx_chips = np.arange(len(fase_error_doble))
    pendiente_doble, _ = np.polyfit(idx_chips, fase_error_doble, 1)
    
    # Se divide por 2.0 (por el cuadrado previo). 
    # Forzamos origen 0 para no introducir ambigüedad (inversión de bits)
    drift_residual = (pendiente_doble / 2.0) * idx_chips
    
    # Corregir los chips
    simbolos_chips_datos = simbolos_chips_datos * np.exp(-1j * drift_residual)
    # ------------------------------------------------

    # Desensanchado (Despreading) DSSS para recuperar los bits originales
    bits_recuperados, _ = despreader(simbolos_chips_datos, PN_BIPOLAR)
    bits_datos = "".join(str(b) for b in bits_recuperados)
    bits_preambulo = "".join("1" if np.real(s) >= 0 else "0" for s in simbolos_preambulo)

    errores_preambulo = sum(a != b for a, b in zip(bits_preambulo, PREAMBULO))

    return {
        "bits_preambulo": bits_preambulo,
        "bits_datos": bits_datos,
        "errores_preambulo": errores_preambulo,
        "pendiente_fase": pendiente_fase,
        "fase_inicial": fase_inicial,
        "frecuencia_offset": frecuencia_offset_fina + f_shift_grueso
    }