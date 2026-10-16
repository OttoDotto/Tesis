import queue
import threading
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

NECESARIAS = MARGEN_PREVIO_RX + N_MUESTRAS_UTILES + 2000

# Bloques de BLOQUE_LECTURA muestras que pueden esperar en cola (~13 s a 2 Msps)
COLA_MAX_BLOQUES = 400
_OVERFLOW = None   # marca "aca se perdieron muestras" dentro de la cola


def _lector(sdr, stream, cola, parar, stats):
    """
    Hilo productor: SOLO lee del SDR y encola. Nunca procesa, para que el
    buffer de UHD se vacie siempre a tiempo (el procesamiento tarda ~50 ms
    por paquete y antes frenaba la lectura -> overflow).
    """
    while not parar.is_set():
        buf = np.empty(BLOQUE_LECTURA, dtype=np.complex64)
        r = sdr.readStream(stream, [buf], BLOQUE_LECTURA, timeoutUs=100000)
        if r.ret == SOAPY_SDR_OVERFLOW:
            stats["overflows"] += 1
            _encolar(cola, _OVERFLOW, stats)
            continue
        if r.ret <= 0:
            continue
        _encolar(cola, buf[:r.ret], stats)


def _encolar(cola, item, stats):
    try:
        cola.put_nowait(item)
    except queue.Full:
        stats["cola_llena"] += 1


def run_rx(sdr_args, antena_rx, ganancia_rx, debug=False):
    assert MUESTRAS_RX > NECESARIAS, "MUESTRAS_RX debe ser mayor que el largo de la trama"

    historial = np.zeros(0, dtype=np.complex64)
    sdr = stream = None
    cola = queue.Queue(maxsize=COLA_MAX_BLOQUES)
    parar = threading.Event()
    stats = {"overflows": 0, "cola_llena": 0}
    hilo = None
    validos = descartados = 0

    try:
        print("INICIANDO SDRS...", flush=True)
        sdr, stream = inicializar_sdr(
            'RX', sdr_args, SAMPLE_RATE, FREQ_CENTRAL, ganancia_rx, antena_rx,
            CANAL_SDR, debug=debug)
        print("SDR LISTO.")

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
            print("\nESPERANDO TELEMETRIA DSSS...\n", flush=True)

        hilo = threading.Thread(target=_lector, args=(sdr, stream, cola, parar, stats),
                                daemon=True)
        hilo.start()

        while True:
            try:
                bloque = cola.get(timeout=0.5)
            except queue.Empty:
                continue

            if bloque is _OVERFLOW:
                # Discontinuidad: unir lo viejo con lo nuevo corrompe la trama
                historial = historial[:0]
                if debug: print("Overflow: se descarta el historial")
                continue

            historial = np.concatenate((historial, bloque))
            if len(historial) < MUESTRAS_RX:
                continue

            ventana = historial - np.mean(historial)
            ini_rafaga, ruido = detectar_rafaga(ventana)

            if ini_rafaga is None:
                historial = historial[-(NECESARIAS):]
                continue

            ini = max(0, ini_rafaga - MARGEN_PREVIO_RX)
            if len(ventana) - ini < NECESARIAS:
                historial = historial[ini:]
                continue

            muestras = ventana[ini:ini + NECESARIAS]
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            pico = float(np.max(np.abs(historial[ini:ini + NECESARIAS])))

            corr, inicio, f_cfo = buscar_preambulo(muestras)
            historial = historial[ini + N_MUESTRAS_TRAMA:]

            if corr is None or corr < UMBRAL_CORRELACION:
                descartados += 1
                if debug:
                    c = -1 if corr is None else corr
                    print(f"[{ts}] Descarta correlacion: {c:.3f} | ruido: {ruido:.4f} | pico: {pico:.2f}")
                continue

            res = analizar_trama(muestras, inicio, f_cfo)
            if res is None:
                continue

            trama = np.packbits(res["bits"]).tobytes()
            payload = verificar_crc(trama)
            if payload is not None:
                validos += 1
            else:
                descartados += 1

            if debug:
                print("\n============================================")
                print(f"RESULTADO [{ts}]")
                print("============================================")
                print(f"Correlacion preambulo: {corr:.3f}")
                print(f"Errores preambulo    : {res['errores_preambulo']}")
                print(f"Offset frecuencia    : {res['frecuencia_offset']:+.1f} Hz")
                print(f"Calidad despreading  : {res['calidad']:.2f}")
                print(f"Pico de amplitud     : {pico:.2f}  (cerca de 1.0 = saturando)")
                print(f"Overflows acumulados : {stats['overflows']}")
                print(f"Bytes recibidos      : {trama.hex()}")
                if payload is not None:
                    print(f"Valores: {describir_paquete(payload)}")
                    print("ESTADO: OK (CRC valido)\n")
                else:
                    print("ESTADO: FALLO (CRC invalido, descartado)\n")
            elif payload is not None:
                print(f"[{ts}] RX -> {describir_paquete(payload)}")

    except KeyboardInterrupt:
        print("\nRX detenido.")
    finally:
        parar.set()
        if hilo is not None:
            hilo.join(timeout=2.0)
        cerrar_sdr(sdr, stream, debug=debug)
        print(f"Paquetes validos: {validos} | descartados: {descartados} | "
              f"overflows: {stats['overflows']} | cola llena: {stats['cola_llena']}")