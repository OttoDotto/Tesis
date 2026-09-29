import time
import numpy as np
from datetime import datetime

from config import (
    FREQ_CENTRAL, SAMPLE_RATE, CANAL_SDR, 
    PREAMBULO, GUARDA, ORIGEN_DATOS,
    TIEMPO_SILENCIO_TX
)
from datos_utils import cargar_datos
from paquete import describir_paquete
from dsp_core import generar_bpsk
from sdr_utils import inicializar_sdr, cerrar_sdr

def run_tx(sdr_args, antena_tx, ganancia_tx):
    # ============================================================
    # INFORMACIÓN ESTÁTICA
    # ============================================================
    print("\n============================================")
    print("TRANSMISOR BPSK - DATOS REALES (CONTINUO)")
    print("============================================")
    print(f"Frecuencia  : {FREQ_CENTRAL / 1e6:.3f} MHz")
    print(f"Sample rate : {SAMPLE_RATE / 1e6:.3f} Msps")
    print(f"Ganancia    : {ganancia_tx}")
    print(f"Antena      : {antena_tx}")
    print(f"Driver      : {sdr_args}")
    print(f"Origen datos: {ORIGEN_DATOS}\n")

    # ============================================================
    # TRANSMISIÓN CONTINUA
    # ============================================================
    sdr = None
    stream = None
    paquetes_enviados = 0

    # Generamos el buffer de "silencio" (amplitud cero)
    muestras_silencio = int(SAMPLE_RATE * TIEMPO_SILENCIO_TX) 
    silencio = np.zeros(muestras_silencio, dtype=np.complex64)

    try:
        print("Inicializando SDR...")
        sdr, stream = inicializar_sdr(
            'TX', sdr_args, SAMPLE_RATE, FREQ_CENTRAL, ganancia_tx, antena_tx, CANAL_SDR
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
            
            # Marca de tiempo de salida (TX)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

            print(f"[{timestamp}] --- Transmitiendo Paquete {paquetes_enviados} ---")
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

            timestamp_fin = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            print(f"[{timestamp_fin}] > Paquete enviado. Transmitiendo {TIEMPO_SILENCIO_TX}s de silencio para mantener link...\n")
            
            # 4. Transmitir el silencio (Híbrido HackRF / UHD)
            if 'hackrf' in sdr_args.lower():
                time.sleep(TIEMPO_SILENCIO_TX)
            else:
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