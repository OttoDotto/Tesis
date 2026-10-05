import numpy as np

from config import (
    FREQ_CENTRAL, SAMPLE_RATE, CANAL_SDR, ANTENA_TX, 
    GANANCIA_TX, PREAMBULO, GUARDA, ORIGEN_DATOS, SDR_ARGS
)
from datos_utils import cargar_datos
from paquete import describir_paquete
from dsp_core import generar_bpsk
from sdr_utils import inicializar_sdr, cerrar_sdr

# ============================================================
# INFORMACIÓN ESTÁTICA
# ============================================================

print("\n============================================")
print("TRANSMISOR BPSK - DATOS REALES (CONTINUO)")
print("============================================")
print(f"Frecuencia  : {FREQ_CENTRAL / 1e6:.3f} MHz")
print(f"Sample rate : {SAMPLE_RATE / 1e6:.3f} Msps")
print(f"Ganancia    : {GANANCIA_TX}")
print(f"Antena      : {ANTENA_TX}")
print(f"Origen datos: {ORIGEN_DATOS}\n")

# ============================================================
# TRANSMISIÓN CONTINUA
# ============================================================

sdr = None
stream = None
paquetes_enviados = 0

# Generamos 1 segundo exacto de "silencio" (amplitud cero)
muestras_silencio = int(SAMPLE_RATE * 1.0) # 1 segundo
silencio = np.zeros(muestras_silencio, dtype=np.complex64)

try:
    print("Inicializando SDR...")
    sdr, stream = inicializar_sdr(
        'TX', SDR_ARGS, SAMPLE_RATE, FREQ_CENTRAL, GANANCIA_TX, ANTENA_TX, CANAL_SDR
    )
    
    print("Iniciando transmisión continua. Presioná Ctrl+C para salir.\n")

    while True:
        # 1. Generar datos frescos
        datos = cargar_datos(origen=ORIGEN_DATOS)
        bits_datos = np.unpackbits(np.frombuffer(datos, dtype=np.uint8)).astype(int)
        bits_datos_str = "".join(str(bit) for bit in bits_datos)

        # 2. Armar la señal BPSK
        BITS_TX = PREAMBULO + bits_datos_str + GUARDA
        senal = generar_bpsk(BITS_TX).astype(np.complex64)
        
        paquetes_enviados += 1
        
        print(f"--- Transmitiendo Paquete {paquetes_enviados} ---")
        print(f"Valores : {describir_paquete(datos)}")
        print(f"Bytes   : {datos.hex()}")
        
        # 3. Transmitir el paquete
        offset = 0
        while offset < len(senal):
            resultado = sdr.writeStream(stream, [senal[offset:]], len(senal) - offset)
            if resultado.ret < 0:
                print(f"Error TX: {resultado.ret}")
                break
            offset += resultado.ret

        print(f"> Paquete enviado. Transmitiendo silencio para mantener link...\n")
        
        # 4. Transmitir el silencio (reemplaza a time.sleep)
        # Esto toma exactamente 1 segundo de tiempo real dictado por el reloj del SDR.
        offset_silencio = 0
        while offset_silencio < len(silencio):
            resultado = sdr.writeStream(stream, [silencio[offset_silencio:]], len(silencio) - offset_silencio)
            if resultado.ret < 0:
                break
            offset_silencio += resultado.ret

except KeyboardInterrupt:
    print(f"\nTX detenido. Se transmitieron {paquetes_enviados} paquetes en total.")
finally:
    cerrar_sdr(sdr, stream)