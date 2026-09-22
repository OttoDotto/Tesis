import os
import numpy as np

# ============================================================
# DIRECTORIOS
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "datos")
os.makedirs(DATA_DIR, exist_ok=True)

# ============================================================
# CÓDIGO PN Y PREÁMBULO
# ============================================================
LONGITUD_PREAMBULO = 1023
LONGITUD_PN = 63  # 2^6 - 1

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
# FUENTE DE DATOS Y TAMAÑO
# ============================================================
ORIGEN_DATOS = "aleatorio"
PUERTO_SERIAL = "/dev/ttyACM0"
BAUDRATE = 9600

from paquete import TAMAÑO_PAQUETE_BYTES
N_BITS = TAMAÑO_PAQUETE_BYTES * 8

# ============================================================
# LONGITUDES DE LA TRAMA
# ============================================================
LONGITUD_DATOS_BITS_CODIFICADOS = (N_BITS // 4) * 7
LONGITUD_DATOS_CHIPS = LONGITUD_DATOS_BITS_CODIFICADOS * LONGITUD_PN
TOTAL_CHIPS_TRAMA = LONGITUD_PREAMBULO + LONGITUD_DATOS_CHIPS

# ============================================================
# MODULACIÓN / PULSE SHAPING
# ============================================================
SPS = 8
BETA = 0.35

# ============================================================
# CANAL Y SINCRONIZACIÓN REAL
# ============================================================
USAR_RUIDO_SIMULADO = False
SNR_DB = -10
# Umbral ajustado para RF real (captura picos amortiguados por el canal)
UMBRAL_CORRELACION_PREAMBULO = 0.30 

# ============================================================
# SDR CONFIGURACIÓN HARDWARE
# ============================================================
USAR_SDR = True                  # 1 para usar USRP/SDR, 0 para simulación local
FREQ_CENTRAL = 920e6             # 920 MHz
SAMPLE_RATE = 0.3e6                # 1 Msps
GANANCIA_TX = 40                 # dB
GANANCIA_RX = 55                 # dB

# Muestras por lectura en RX (buffer de ~100ms a 1Msps)
MUESTRAS_RX_POR_TRAMA = 100000 

# Solapamiento (Muestras mantenidas entre lecturas para no cortar el preámbulo)
SAMPLES_OVERLAP = TOTAL_CHIPS_TRAMA * SPS 

SDR_ARGS = "driver=uhd"
CANAL_SDR = 0
ANTENA_TX = "TX/RX"
ANTENA_RX = "TX/RX"

# ============================================================
# TEMPORIZACIÓN / MODO
# ============================================================
INTERVALO_SEGUNDOS = 0.5         # Pausas entre transmisiones en transmisión continua
SIMULACION_UN_PAQUETE = False   # False = Transmite ráfagas continuas