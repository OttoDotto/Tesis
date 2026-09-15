# ============================================================
# DIRECTORIOS
# ============================================================

import os
import numpy as np

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

DATA_DIR = os.path.join(
    BASE_DIR,
    "datos"
)

os.makedirs(
    DATA_DIR,
    exist_ok=True
)


# ============================================================
# CÓDIGO PN
# ============================================================

LONGITUD_PREAMBULO = 1023

LONGITUD_PN = 63  # 2^6 - 1

# Longitudes válidas de m-sequences:
# 2^n - 1
POLINOMIOS_PRIMITIVOS = {
    4: [4, 3],
    5: [5, 3],
    6: [6, 1],
    7: [7, 3],
    8: [8, 6, 5, 4],
    9: [9, 4],
    10: [10, 1, 2, 5],
    11: [11, 3],
    12: [12, 3],
}

N_PN = int(np.log2(LONGITUD_PN + 1))
TAPS_PN = POLINOMIOS_PRIMITIVOS[N_PN]


# ============================================================
# FUENTE DE DATOS
# ============================================================

ORIGEN_DATOS = "aleatorio"

PUERTO_SERIAL = "/dev/ttyACM0"

BAUDRATE = 9600


# ============================================================
# TAMAÑO DE LOS DATOS
# ============================================================

from paquete import TAMAÑO_PAQUETE_BYTES

N_BITS = (
    TAMAÑO_PAQUETE_BYTES * 8
)


# ============================================================
# LONGITUDES DE LA TRAMA
# ============================================================

LONGITUD_DATOS_BITS_CODIFICADOS = (
    N_BITS // 4
) * 7

LONGITUD_DATOS_CHIPS = (
    LONGITUD_DATOS_BITS_CODIFICADOS
    * LONGITUD_PN
)


# ============================================================
# MODULACIÓN / PULSE SHAPING
# ============================================================

SPS = 8

BETA = 0.35


# ============================================================
# CANAL SIMULADO
# ============================================================

USAR_RUIDO_SIMULADO = True

SNR_DB = -10

UMBRAL_CORRELACION_PREAMBULO = 0.70


# ============================================================
# SDR
# ============================================================

USAR_SDR = 0

FREQ_CENTRAL = 920e6

SAMPLE_RATE = 1e6

MUESTRAS_RX_POR_TRAMA = 200000

GANANCIA_TX = 40

GANANCIA_RX = 60


# ============================================================
# SoapySDR / UHD
# ============================================================

SDR_ARGS = "driver=uhd"

CANAL_SDR = 0

ANTENA_TX = "TX/RX"

ANTENA_RX = "RX2"


# ============================================================
# TEMPORIZACIÓN
# ============================================================

INTERVALO_SEGUNDOS = 2.0


# ============================================================
# SIMULACIÓN
# ============================================================

SIMULACION_UN_PAQUETE = True