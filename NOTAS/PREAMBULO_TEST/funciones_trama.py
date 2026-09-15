"""
Funciones para la estructura de trama del sistema DSSS-BPSK.

El preámbulo se utiliza para que el receptor pueda detectar
el comienzo de una trama antes de procesar los datos.
"""

import numpy as np

from config import (
    LONGITUD_PREAMBULO,
    POLINOMIOS_PRIMITIVOS
)


# ============================================================
# PREÁMBULO
# ============================================================

def generar_preambulo():
    """
    Genera una secuencia bipolar conocida para sincronización.

    El preámbulo es independiente del código PN utilizado
    para ensanchar los datos DSSS.
    """

    n = int(np.log2(LONGITUD_PREAMBULO + 1))

    if 2**n - 1 != LONGITUD_PREAMBULO:
        raise ValueError(
            f"LONGITUD_PREAMBULO={LONGITUD_PREAMBULO} "
            f"no es válida para una m-sequence. "
            f"Debe ser 2^n - 1."
        )

    if n not in POLINOMIOS_PRIMITIVOS:
        raise ValueError(
            f"No hay un polinomio primitivo configurado "
            f"para un LFSR de {n} etapas."
        )

    taps = POLINOMIOS_PRIMITIVOS[n]

    registro = [1] * n
    secuencia = []

    for _ in range(LONGITUD_PREAMBULO):

        salida = registro[-1]
        secuencia.append(salida)

        nuevo_bit = 0

        for t in taps:
            nuevo_bit ^= registro[n - t]

        registro = [nuevo_bit] + registro[:-1]

    preambulo = 2 * np.array(secuencia) - 1

    assert len(preambulo) == LONGITUD_PREAMBULO

    return preambulo.astype(float)

# ============================================================
# AGREGAR PREÁMBULO
# ============================================================

def agregar_preambulo(señal_datos):
    """
    Agrega el preámbulo al comienzo de la señal DSSS.
    """

    preambulo = generar_preambulo()

    return np.concatenate([
        preambulo,
        señal_datos
    ])


# ============================================================
# DETECCIÓN DE PREÁMBULO
# ============================================================

def detectar_preambulo(señal, preambulo):
    """
    Busca el preámbulo mediante correlación normalizada.

    Esta implementación está vectorizada para evitar recorrer
    manualmente cada posición de la señal.

    Devuelve:

        mejor_posicion
        mejor_correlacion
        mejor_correlacion_compleja
    """

    N = len(preambulo)

    if len(señal) < N:
        return None, 0.0, 0.0

    señal = np.asarray(señal)
    preambulo = np.asarray(preambulo)

    correlaciones = np.convolve(
        señal,
        np.conj(preambulo[::-1]),
        mode="valid"
    )

    # --------------------------------------------------------
    # Energía de cada ventana
    # --------------------------------------------------------

    energia_señal = np.abs(señal) ** 2

    energia_ventanas = np.convolve(
        energia_señal,
        np.ones(N),
        mode="valid"
    )

    # --------------------------------------------------------
    # Correlación normalizada por energía teórica del preámbulo
    # --------------------------------------------------------
    energia_preambulo = np.sum(np.abs(preambulo) ** 2) # Es igual a N

    # Potencia promedio global o de la ventana para remover escala
    potencia_media = np.mean(np.abs(señal) ** 2)

    # Evitar divisiones por cero
    energia_ventanas = np.maximum(
        energia_ventanas,
        1e-12
    )

    '''
    # Correlación normalizada
    correlaciones_normalizadas = (
        np.abs(correlaciones)
        /
        np.sqrt(
            energia_ventanas
            * energia_preambulo
        )
    )
    '''
    correlaciones_normalizadas = np.abs(correlaciones) / (energia_preambulo * np.sqrt(potencia_media))

    # --------------------------------------------------------
    # Mejor posición
    # --------------------------------------------------------

    mejor_posicion = int(
        np.argmax(correlaciones_normalizadas)
    )

    mejor_correlacion = float(
        correlaciones_normalizadas[mejor_posicion]
    )

    mejor_correlacion_compleja = (
        correlaciones[mejor_posicion]
    )

    return (
        mejor_posicion,
        mejor_correlacion,
        mejor_correlacion_compleja
    )