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
    print("\n============================================")
    print("RECEPTOR BPSK - TELEMETRÍA EN VIVO")
    print("============================================")
    print(f"Frecuencia : {FREQ_CENTRAL / 1e6:.3f} MHz")
    print(f"Sample rate: {SAMPLE_RATE / 1e6:.3f} Msps")
    print(f"Ganancia   : {ganancia_rx}")
    print(f"Antena     : {antena_rx}")
    print(f"Driver     : {sdr_args}\n")

    buffer_rx = np.zeros(MUESTRAS_RX, dtype=np.complex64)
    sdr = None
    stream = None

    try:
        print("Inicializando SDR...")
        sdr, stream = inicializar_sdr(
            'RX', sdr_args, SAMPLE_RATE, FREQ_CENTRAL, ganancia_rx, antena_rx, CANAL_SDR
        )
        
        print("Esperando paquetes de telemetría...\n")

        while True:
            resultado = sdr.readStream(stream, [buffer_rx], MUESTRAS_RX, timeoutUs=500000)

            if resultado.ret < 0:
                if debug:
                    print(f"Error RX: {resultado.ret}")
                continue

            cantidad = resultado.ret
            if cantidad == 0:
                continue

            muestras = buffer_rx[:cantidad].copy()
            
            magnitud = np.abs(muestras)
            nivel_medio = np.mean(magnitud)
            nivel_maximo = np.max(magnitud)

            if debug:
                print(f"DEBUG SDR - Max: {nivel_maximo:.4f} | Ruido: {nivel_medio:.4f}")

            # Filtro base: ignorar si el pico no es significativamente mayor a la media pura
            if nivel_maximo < max(UMBRAL_NIVEL, nivel_medio * FACTOR_RUIDO_ESTATICO):
                continue

            umbral_disparo = max(nivel_medio * FACTOR_RUIDO_DINAMICO, nivel_maximo * FACTOR_PICO_SEÑAL)
            
            indices_burst = np.where(magnitud > umbral_disparo)[0]
            if len(indices_burst) == 0:
                continue
                
            inicio_burst = indices_burst[0]

            idx_inicio = max(0, inicio_burst - MARGEN_PREVIO_RX)
            idx_fin = min(len(muestras), idx_inicio + LONGITUD_VENTANA_RX)
            
            muestras_ventana = muestras[idx_inicio:idx_fin]

            if len(muestras_ventana) < MIN_MUESTRAS_VENTANA:
                if debug:
                    print("Trama incompleta en la ventana de muestras.")
                continue

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

            correlacion, inicio_relativo, f_shift_grueso = buscar_preambulo(muestras_ventana)

            if correlacion is None:
                continue

            if correlacion < UMBRAL_CORRELACION:
                if debug:
                    print(f"[{timestamp}] Correlación descartada: {correlacion:.3f} (Inferior al umbral)")
                continue

            if debug:
                print(f"Correlación: {correlacion:.3f} | Inicio: {inicio_relativo} | Shift FFT: {f_shift_grueso:.1f} Hz")

            resultado_trama = analizar_trama(muestras_ventana, inicio_relativo, f_shift_grueso)

            if resultado_trama is None:
                continue

            bits = np.array([int(b) for b in resultado_trama["bits_datos"]], dtype=np.uint8)
            datos_rx = np.packbits(bits).tobytes()

            # ============================================================
            # SALIDA LIMPIA Y PROFESIONAL DE TELEMETRÍA
            # ============================================================
            print("============================================")
            print(f" TELEMETRÍA RECIBIDA [{timestamp}]")
            print("============================================")
            
            try:
                print(f"+ Datos de Sensores : {describir_paquete(datos_rx)}")
            except ValueError as e:
                print(f"  X - Error interpretando paquete: {e}")

            print(f"+ Calidad de Enlace & DSP:")
            print(f"     • Correlación       : {correlacion:.3f}")
            print(f"     • Offset Frecuencia : {resultado_trama['frecuencia_offset']:+.1f} Hz")
            print(f"     • Errores Preámbulo : {resultado_trama['errores_preambulo']}")
            
            if debug:
                print(f"     • Fase inicial      : {np.degrees(resultado_trama['fase_inicial']):+.1f}°")
                print(f"     • Var. fase         : {np.degrees(resultado_trama['pendiente_fase']):+.3f}°/símbolo")
                print(f"     • Bytes hex         : {datos_rx.hex()}")

            if resultado_trama["errores_preambulo"] == 0 and len(datos_rx) == TAMAÑO_PAQUETE_BYTES:
                print("  OK: PRUEBA SUPERADA: PREÁMBULO Y PAQUETE RECIBIDOS\n")
            else:
                print("  ALERTA: PRUEBA FALLIDA\n")

    except KeyboardInterrupt:
        print("\nRX detenido.")
    finally:
        cerrar_sdr(sdr, stream)