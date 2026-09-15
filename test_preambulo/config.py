# ============================================================
# CONFIGURACIÓN SDR
# ============================================================

SDR_ARGS = "driver=uhd"

FREQ_CENTRAL = 920e6
SAMPLE_RATE = 1e6

CANAL = 0
ANTENA = "TX/RX"

GANANCIA_TX = 40
GANANCIA_RX = 40


# ============================================================
# CONFIGURACIÓN BPSK
# ============================================================

MUESTRAS_POR_BIT = 8

PREAMBULO = "11010011100101101101000110111010"

DATOS = "1010101010101010"

# Margen de guarda.
# No forma parte de los datos útiles.
GUARDA = "1" * 128


# ============================================================
# CONFIGURACIÓN RX
# ============================================================

UMBRAL_NIVEL = 0.01

UMBRAL_CORRELACION = 0.70

MUESTRAS_RX = 200000