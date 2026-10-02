import numpy as np
from datetime import datetime

from config import (
    FREQ_CENTRAL, SAMPLE_RATE, CANAL_SDR, 
    PREAMBULO, GUARDA, UMBRAL_NIVEL, 
    UMBRAL_CORRELACION, MUESTRAS_RX,
    FACTOR_RUIDO_ESTATICO, FACTOR_RUIDO_DINAMICO,
    FACTOR_PICO_SEÑAL, MARGEN_PREVIO_RX, 
    LONGITUD_VENTANA_RX, MIN_MUESTRAS_VENTANA
)
from paquete import TAMAÑO_PAQUETE_BYTES, describir_paquete
from dsp_core import buscar_preambulo, analizar_trama, CANTIDAD_BITS_DATOS
from sdr_utils import inicializar_sdr, cerrar_sdr

def run_rx(sdr_args, antena_rx, ganancia_rx, debug=False):
    if debug:
        print("\n============================================")
        print("RECEPTOR BPSK - MODO DEBUG")
        print("============================================")
        print(f"Frecuencia : {FREQ_CENTRAL / 1e6:.3f} MHz")
        print(f"Sample rate: {SAMPLE_RATE / 1e6:.3f} Msps")
        print(f"Ganancia   : {ganancia_rx}")
        print(f"Antena     : {antena_rx}")
        print(f"Driver     : {sdr_args}\n")
    else:
        print("\nESPERANDO TELEMETRIA...\n")

    buffer_rx = np.zeros(MUESTRAS_RX, dtype=np.complex64)
    sdr = None
    stream = None

    try:
        if debug: print("Inicializando SDR...")
        sdr, stream = inicializar_sdr(
            'RX', sdr_args, SAMPLE_RATE, FREQ_CENTRAL, ganancia_rx, antena_rx, CANAL_SDR
        )

        while True:
            resultado = sdr.readStream(stream, [buffer_rx], MUESTRAS_RX, timeoutUs=500000)

            if resultado.ret < 0:
                if debug: print(f"Error RX: {resultado.ret}")
                continue

            cantidad = resultado.ret
            if cantidad == 0:
                continue

            muestras = buffer_rx[:cantidad].copy()
            
            # Eliminación de DC Offset
            muestras = muestras - np.mean(muestras)

            magnitud = np.abs(muestras)
            nivel_medio = np.mean(magnitud)
            nivel_maximo = np.max(magnitud)

            # Validación de piso de ruido estático usando constantes del config
            if nivel_maximo < max(UMBRAL_NIVEL, nivel_medio * FACTOR_RUIDO_ESTATICO):
                if debug:
                    print(
                        f"Nivel RX | medio={nivel_medio:.5f} "
                        f"max={nivel_maximo:.5f} "
                        f"umbral={max(UMBRAL_NIVEL, nivel_medio * FACTOR_RUIDO_ESTATICO):.5f}"
                    )
                continue

            # Cálculo de umbral dinámico de disparo de ráfaga
            umbral_disparo = max(nivel_medio * FACTOR_RUIDO_DINAMICO, nivel_maximo * FACTOR_PICO_SEÑAL)
            
            indices_burst = np.where(magnitud > umbral_disparo)[0]
            if len(indices_burst) == 0:
                continue
                
            inicio_burst = indices_burst[0]

            # Recorte de ventana utilizando márgenes parametrizados
            idx_inicio = max(0, inicio_burst - MARGEN_PREVIO_RX)
            idx_fin = min(len(muestras), idx_inicio + LONGITUD_VENTANA_RX)
            
            muestras_ventana = muestras[idx_inicio:idx_fin]

            if len(muestras_ventana) < MIN_MUESTRAS_VENTANA:
                if debug: print("Ventana corta, descartando.")
                continue

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

            correlacion, inicio_relativo, f_shift_grueso = buscar_preambulo(muestras_ventana)

            if correlacion is None:
                continue

            if correlacion < UMBRAL_CORRELACION:
                if debug:
                    print(
                        f"[{timestamp}] "
                        f"Descarta correlacion: {correlacion:.3f} | "
                        f"Max: {nivel_maximo:.3f} | "
                        f"Ruido: {nivel_medio:.3f} | "
                        f"Fshift: {f_shift_grueso/1e3:+.2f} kHz"
                    )
                continue

            resultado_trama = analizar_trama(muestras_ventana, inicio_relativo, f_shift_grueso)

            if resultado_trama is None:
                continue

            bits = np.array([int(b) for b in resultado_trama["bits_datos"]], dtype=np.uint8)
            datos_rx = np.packbits(bits).tobytes()

            es_valido = (resultado_trama["errores_preambulo"] == 0 and len(datos_rx) == TAMAÑO_PAQUETE_BYTES)

            if not debug and not es_valido:
                continue

            if not debug:
                try:
                    valores = describir_paquete(datos_rx)
                    print(f"[{timestamp}] RX -> {valores}")
                except Exception:
                    pass
            else:
                print("\n============================================")
                print(f"RESULTADO [{timestamp}]")
                print("============================================")
                print(f"Preámbulo recibido: {resultado_trama['bits_preambulo']}")
                print(f"Errores preámbulo : {resultado_trama['errores_preambulo']}")
                print(f"Bytes recibidos   : {datos_rx.hex()}")
                
                try:
                    print(f"Valores interpretados: {describir_paquete(datos_rx)}")
                except Exception as e:
                    print(f"Error formato struct: {e}")

                print(f"Fase inicial: {np.degrees(resultado_trama['fase_inicial']):+.1f} grados")
                print(f"Var. fase   : {np.degrees(resultado_trama['pendiente_fase']):+.3f} grados/símbolo")
                print(f"Offset frec : {resultado_trama['frecuencia_offset']:+.1f} Hz")

                if es_valido:
                    print("ESTADO: OK (TRAMA VALIDA)\n")
                else:
                    print("ESTADO: FALLO (BASURA DESCARTADA)\n")

    except KeyboardInterrupt:
        print("\nRX detenido.")
    finally:
        cerrar_sdr(sdr, stream)