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

def run_tx(sdr_args, antena_tx, ganancia_tx, debug=False):
    print("\n============================================")
    print("TRANSMISOR BPSK - TELEMETRIA EN VIVO")
    print("============================================")
    print(f"Frecuencia  : {FREQ_CENTRAL / 1e6:.3f} MHz")
    print(f"Sample rate : {SAMPLE_RATE / 1e6:.3f} Msps")
    print(f"Ganancia    : {ganancia_tx}")
    print(f"Antena      : {antena_tx}")
    print(f"Driver      : {sdr_args}")
    print(f"Origen datos: {ORIGEN_DATOS}\n")

    sdr = None
    stream = None
    paquetes_enviados = 0

    muestras_silencio = int(SAMPLE_RATE * TIEMPO_SILENCIO_TX) 
    silencio = np.zeros(muestras_silencio, dtype=np.complex64)

    try:
        print("Inicializando SDR...")
        sdr, stream = inicializar_sdr(
            'TX', sdr_args, SAMPLE_RATE, FREQ_CENTRAL, ganancia_tx, antena_tx, CANAL_SDR
        )
        
        print("Iniciando transmisión continua. Presioná Ctrl+C para salir.\n")

        while True:
            datos = cargar_datos(origen=ORIGEN_DATOS)
            bits_datos = np.unpackbits(np.frombuffer(datos, dtype=np.uint8)).astype(int)
            bits_datos_str = "".join(str(bit) for bit in bits_datos)

            BITS_TX = PREAMBULO + bits_datos_str + GUARDA
            senal = generar_bpsk(BITS_TX).astype(np.complex64)
            
            # HackRF Fix: Evitar saturar DAC de 8 bits
            if 'hackrf' in sdr_args.lower():
                senal = senal * 0.7
            
            paquetes_enviados += 1
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

            print("============================================")
            print(f"TELEMETRIA ENVIADA [{timestamp}]")
            print("============================================")
            print(f"  Paquete Numero    : {paquetes_enviados}")
            print(f"  Datos de Sensores : {describir_paquete(datos)}")
            
            if debug:
                print(f"  Bytes Hexadecimal : {datos.hex()}")
                print(f"  Muestras totales  : {len(senal)}")
            
            offset = 0
            while offset < len(senal):
                resultado = sdr.writeStream(stream, [senal[offset:]], len(senal) - offset)
                if resultado.ret < 0:
                    if debug:
                        print(f"Error TX: {resultado.ret}")
                    break
                offset += resultado.ret

            print(f"  ESTADO: PAQUETE ENVIADO (Transmitiendo {TIEMPO_SILENCIO_TX}s de portadora en blanco)\n")

            # Mantener PLL encendido enviando ceros a través de hardware
            offset_silencio = 0
            while offset_silencio < len(silencio):
                resultado = sdr.writeStream(stream, [silencio[offset_silencio:]], len(silencio) - offset_silencio)
                if resultado.ret < 0:
                    break
                offset_silencio += resultado.ret

            # Si es HackRF, hay que dormir Python un instante para no ahogar la RAM
            if 'hackrf' in sdr_args.lower():
                time.sleep(max(0.0, TIEMPO_SILENCIO_TX - 0.1))

    except KeyboardInterrupt:
        print(f"\nTX detenido. Se transmitieron {paquetes_enviados} paquetes en total.")
    finally:
        cerrar_sdr(sdr, stream)