# ============================================================
# FUENTE DE DATOS
# ============================================================

ORIGEN_DATOS = "aleatorio"
PUERTO_SERIAL = "/dev/ttyACM0"
BAUDRATE = 9600

# ============================================================
# ESTRUCTURA DE TRAMA
# ============================================================

# Preambulo: 16 BITS que se ENSANCHAN con el mismo PN que los datos
# (16 bits x 63 chips = 1008 chips). Elegido por busqueda exhaustiva: pico de
# lobulo lateral de autocorrelacion = 2 (el minimo posible para 16 bits).
# Si se cambia el largo, N_MUESTRAS_*, NECESARIAS y los asserts se recalculan solos.
PREAMBULO = "1101011001100000"
GUARDA = "1" * 128

# ============================================================
# SDR (PARÁMETROS BASE)
# ============================================================

USAR_SDR = True
FREQ_CENTRAL = 919.5e6
SAMPLE_RATE = 2e6
MUESTRAS_RX = 200000      # minimo acumulado antes de analizar (debe ser > NECESARIAS de RX.py, ~93k con preambulo de 16 bits)
CANAL_SDR = 0
BLOQUE_LECTURA = 65536    # muestras pedidas por cada readStream

# ============================================================
# DSSS / FORMA DE ONDA
# ============================================================

MUESTRAS_POR_BIT = 8      # muestras por chip
AMPLITUD_TX = 0.9         # PICO maximo de la senal (<1.0 para no saturar el DAC)

# Conformado de pulso con filtro de raiz de coseno alzado (RRC).
# True : TX conforma con RRC y RX usa filtro adaptado (espectro mucho mas angosto).
# False: pulso rectangular + integrate & dump (comportamiento anterior).
# TX y RX DEBEN usar el mismo valor, el mismo BETA_RRC y el mismo SPAN_CHIPS_RRC.
# Con RRC la potencia media a igual pico es ~3.7 dB menor: si hace falta alcance,
# subir AMPLITUD_TX (hasta ~0.9) mirando el 'Pico de amplitud' del RX en --debug.
USAR_RRC = True
BETA_RRC = 0.35           # roll-off: ancho de banda = (1+BETA) x tasa de chips
SPAN_CHIPS_RRC = 8        # el filtro abarca 8 chips -> 8*MUESTRAS_POR_BIT+1 = 65 taps

# ============================================================
# RECEPTOR
# ============================================================

# Máximo desfase de frecuencia TX vs RX que se busca (Hz).
# HackRF: cristal de +-20..40 ppm -> a 919 MHz son +-18..37 kHz.
# (Antes el limite efectivo era +-20 kHz y la HackRF no enganchaba)
CFO_MAX_HZ = 60e3

UMBRAL_NIVEL = 0.005          # piso absoluto de deteccion (amplitud)
# Deteccion de rafaga por energia. Antes: SUAVIZADO 64 y FACTOR 3.0, que solo
# detectaba con ~10 dB de SNR por muestra y a SNR menores podia disparar tarde
# (en medio de la trama) cortando el preambulo. Con 1024 y 1.3 detecta desde ~0 dB,
# sin falsos disparos en ruido estacionario, y siempre ANTES del inicio real.
FACTOR_UMBRAL_RAFAGA = 1.3    # rafaga = nivel suavizado > 1.3 x piso de ruido
SUAVIZADO_RAFAGA = 1024       # muestras del promedio movil de la deteccion
MARGEN_PREVIO_RX = 500        # muestras antes del inicio de rafaga
# Correlacion normalizada minima del preambulo ENSANCHADO (1008 chips).
# Solo ruido: pico maximo medido 0.127 (150 ventanas). Senal en el limite de lo
# decodificable (~-13 dB SNR/muestra): ~0.5. El 0.65 viejo era para 32 simbolos
# sin ensanchar, cuyo pico de ruido ya llegaba a ~0.55.
UMBRAL_CORRELACION = 0.70

# ============================================================
# TRANSMISION CONTINUA (TX)
# ============================================================

TIEMPO_SILENCIO_TX = 0.5
