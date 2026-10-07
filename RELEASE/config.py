# ============================================================
# FUENTE DE DATOS
# ============================================================

ORIGEN_DATOS = "aleatorio"
PUERTO_SERIAL = "/dev/ttyACM0"
BAUDRATE = 9600

# ============================================================
# ESTRUCTURA DE TRAMA
# ============================================================

PREAMBULO = "11010011100101101101000110111010"
GUARDA = "1" * 128

# ============================================================
# SDR (PARÁMETROS BASE)
# ============================================================

USAR_SDR = True
FREQ_CENTRAL = 919.5e6
SAMPLE_RATE = 2e6
MUESTRAS_RX = 200000      # mínimo acumulado antes de analizar (debe ser > largo de trama)
CANAL_SDR = 0
BLOQUE_LECTURA = 65536    # muestras pedidas por cada readStream

# ============================================================
# DSSS / FORMA DE ONDA
# ============================================================

MUESTRAS_POR_BIT = 8      # muestras por chip
AMPLITUD_TX = 0.7         # <1.0 para no saturar el DAC

# ============================================================
# RECEPTOR
# ============================================================

# Máximo desfase de frecuencia TX vs RX que se busca (Hz).
# HackRF: cristal de +-20..40 ppm -> a 919 MHz son +-18..37 kHz.
# (Antes el limite efectivo era +-20 kHz y la HackRF no enganchaba)
CFO_MAX_HZ = 60e3

UMBRAL_NIVEL = 0.005          # piso absoluto de deteccion (amplitud)
FACTOR_UMBRAL_RAFAGA = 3.0    # rafaga = nivel suavizado > 3 x piso de ruido
SUAVIZADO_RAFAGA = 64         # muestras del promedio movil de la deteccion
MARGEN_PREVIO_RX = 500        # muestras antes del inicio de rafaga
UMBRAL_CORRELACION = 0.65     # correlacion normalizada minima del preambulo

# ============================================================
# TRANSMISION CONTINUA (TX)
# ============================================================

TIEMPO_SILENCIO_TX = 0.5
