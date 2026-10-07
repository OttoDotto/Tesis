import time
import numpy as np
from datetime import datetime

from config import (
    FREQ_CENTRAL, SAMPLE_RATE, CANAL_SDR, 
    ORIGEN_DATOS, TIEMPO_SILENCIO_TX
)
from datos_utils import cargar_datos
from paquete import describir_paquete, agregar_crc
from dsp_core import generar_trama_dsss
from sdr_utils import inicializar_sdr, cerrar_sdr

def run_tx(sdr_args, antena_tx, ganancia_tx, debug=False):
    if debug:
        print("\n============================================")
        print("TRANSMISOR DSSS - MODO DEBUG")
        print("============================================")
        print(f"Frecuencia  : {FREQ_CENTRAL / 1e6:.3f} MHz")
        print(f"Sample rate : {SAMPLE_RATE / 1e6:.3f} Msps")
        print(f"Ganancia    : {ganancia_tx}")
        print(f"Antena      : {antena_tx}")
        print(f"Origen datos: {ORIGEN_DATOS}\n")
    else:
        print("\nTRANSMITIENDO DSSS...\n")

    sdr = None
    stream = None
    paquetes_enviados = 0

    muestras_silencio = int(SAMPLE_RATE * TIEMPO_SILENCIO_TX) 
    silencio = np.zeros(muestras_silencio, dtype=np.complex64)

    try:
        if debug: print("Inicializando SDR...")
        sdr, stream = inicializar_sdr(
            'TX', sdr_args, SAMPLE_RATE, FREQ_CENTRAL, ganancia_tx, antena_tx, CANAL_SDR
        )
        
        print("En el aire. Presiona Ctrl+C para salir.\n")

        while True:
            datos = cargar_datos(origen=ORIGEN_DATOS)
            bits_datos = np.unpackbits(np.frombuffer(agregar_crc(datos), dtype=np.uint8)).astype(int)  # payload + CRC16

            # Generar trama ensanchada DSSS
            senal_dsss = generar_trama_dsss(bits_datos).astype(np.complex64)
            
            # Padding de seguridad para el búfer del SDR
            padding_seguridad = np.zeros(int(SAMPLE_RATE * 0.05), dtype=np.complex64)
            senal = np.concatenate((senal_dsss, padding_seguridad))
            
            paquetes_enviados += 1
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

            if debug:
                print(f"[{timestamp}] --- Transmitiendo Paquete DSSS {paquetes_enviados} ---")
                print(f"Valores : {describir_paquete(datos)}")
                print(f"Bytes   : {datos.hex()}")
            else:
                print(f"[{timestamp}] TX Paquete DSSS #{paquetes_enviados} -> {describir_paquete(datos)}")
            
            offset = 0
            while offset < len(senal):
                resultado = sdr.writeStream(stream, [senal[offset:]], len(senal) - offset)
                if resultado.ret < 0:
                    if debug: print(f"Error TX: {resultado.ret}")
                    break
                offset += resultado.ret

            if debug:
                timestamp_fin = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                print(f"[{timestamp_fin}] > Silencio de {TIEMPO_SILENCIO_TX}s...\n")
            
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
        print(f"\nTX detenido. Paquetes enviados: {paquetes_enviados}")
    finally:
        cerrar_sdr(sdr, stream)