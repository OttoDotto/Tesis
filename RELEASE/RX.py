import numpy as np
from datetime import datetime
from SoapySDR import SOAPY_SDR_OVERFLOW

from config import (
    FREQ_CENTRAL, SAMPLE_RATE, CANAL_SDR, UMBRAL_CORRELACION,
    MUESTRAS_RX, MARGEN_PREVIO_RX, BLOQUE_LECTURA
)
from paquete import describir_paquete, verificar_crc
from dsp_core import (
    detectar_rafaga, buscar_preambulo, analizar_trama,
    N_MUESTRAS_UTILES, N_MUESTRAS_TRAMA
)
from sdr_utils import inicializar_sdr, cerrar_sdr

# Muestras que hay que tener desde el inicio de rafaga para poder decodificar
# (trama + margen previo + holgura por deriva de reloj / busqueda de fase)
NECESARIAS = MARGEN_PREVIO_RX + N_MUESTRAS_UTILES + 2000


def run_rx(sdr_args, antena_rx, ganancia_rx, debug=False):
    if debug:
        print("\n============================================")
        print("RECEPTOR DSSS - MODO DEBUG")
        print("============================================")
        print(f"Frecuencia : {FREQ_CENTRAL / 1e6:.3f} MHz")
        print(f"Sample rate: {SAMPLE_RATE / 1e6:.3f} Msps")
        print(f"Ganancia   : {ganancia_rx}")
        print(f"Antena     : {antena_rx}")
        print(f"Driver     : {sdr_args}\n")
    else:
        print("\nESPERANDO TELEMETRIA DSSS...\n")

    assert MUESTRAS_RX > NECESARIAS, "MUESTRAS_RX debe ser mayor que el largo de la trama"

    bloque = np.zeros(BLOQUE_LECTURA, dtype=np.complex64)
    historial = np.zeros(0, dtype=np.complex64)
    sdr = stream = None

    try:
        sdr, stream = inicializar_sdr(
            'RX', sdr_args, SAMPLE_RATE, FREQ_CENTRAL, ganancia_rx, antena_rx, CANAL_SDR)

        while True:
            r = sdr.readStream(stream, [bloque], BLOQUE_LECTURA, timeoutUs=500000)

            if r.ret == SOAPY_SDR_OVERFLOW:
                # Se perdieron muestras: unir lo viejo con lo nuevo crea una
                # discontinuidad que corrompe cualquier trama que la cruce.
                historial = historial[:0]
                if debug: print("Overflow: se descarta el historial")
                continue
            if r.ret <= 0:
                continue

            historial = np.concatenate((historial, bloque[:r.ret]))
            if len(historial) < MUESTRAS_RX:
                continue

            ventana = historial - np.mean(historial)
            ini_rafaga, ruido = detectar_rafaga(ventana)

            if ini_rafaga is None:
                # nada: conservar solo el final por si una trama empieza ahi
                historial = historial[-(NECESARIAS):]
                continue

            ini = max(0, ini_rafaga - MARGEN_PREVIO_RX)
            if len(ventana) - ini < NECESARIAS:
                # trama incompleta: esperar mas muestras (antes se descartaba)
                historial = historial[ini:]
                continue

            muestras = ventana[ini:ini + NECESARIAS]
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

            corr, inicio, f_cfo = buscar_preambulo(muestras)
            # La rafaga se consume haya o no decodificado, para no reprocesarla
            historial = historial[ini + N_MUESTRAS_TRAMA:]

            if corr is None or corr < UMBRAL_CORRELACION:
                if debug:
                    c = -1 if corr is None else corr
                    print(f"[{ts}] Descarta correlacion: {c:.3f} | ruido: {ruido:.4f}")
                continue

            res = analizar_trama(muestras, inicio, f_cfo)
            if res is None:
                continue

            trama = np.packbits(res["bits"]).tobytes()
            payload = verificar_crc(trama)

            if debug:
                print("\n============================================")
                print(f"RESULTADO [{ts}]")
                print("============================================")
                print(f"Correlacion preambulo: {corr:.3f}")
                print(f"Errores preambulo    : {res['errores_preambulo']}")
                print(f"Offset frecuencia    : {res['frecuencia_offset']:+.1f} Hz")
                print(f"Calidad despreading  : {res['calidad']:.2f}")
                print(f"Bytes recibidos      : {trama.hex()}")
                if payload is not None:
                    print(f"Valores: {describir_paquete(payload)}")
                    print("ESTADO: OK (CRC valido)\n")
                else:
                    print("ESTADO: FALLO (CRC invalido, descartado)\n")
            elif payload is not None:
                print(f"[{ts}] RX -> {describir_paquete(payload)}")
            # sin CRC valido en modo limpio: no se imprime nada (basura descartada)

    except KeyboardInterrupt:
        print("\nRX detenido.")
    finally:
        cerrar_sdr(sdr, stream)
