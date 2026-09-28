import numpy as np

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

def run_rx(sdr_args, antena_rx, ganancia_rx):
    # ============================================================
    # INFORMACIÓN
    # ============================================================
    print("\n============================================")
    print("RECEPTOR BPSK - DATOS REALES (OPTIMIZADO)")
    print("============================================")
    print(f"Frecuencia : {FREQ_CENTRAL / 1e6:.3f} MHz")
    print(f"Sample rate: {SAMPLE_RATE / 1e6:.3f} Msps")
    print(f"Ganancia   : {ganancia_rx}")
    print(f"Antena     : {antena_rx}")
    print(f"Driver     : {sdr_args}\n")
    print(f"Preámbulo: {len(PREAMBULO)} bits")
    print(f"Datos    : {CANTIDAD_BITS_DATOS} bits")
    print(f"Guarda   : {len(GUARDA)} bits\n")

    buffer_rx = np.zeros(MUESTRAS_RX, dtype=np.complex64)
    sdr = None
    stream = None

    # ============================================================
    # RECEPCIÓN
    # ============================================================
    try:
        print("Inicializando SDR...")
        sdr, stream = inicializar_sdr(
            'RX', sdr_args, SAMPLE_RATE, FREQ_CENTRAL, ganancia_rx, antena_rx, CANAL_SDR
        )
        
        print("Esperando señal...\n")

        while True:
            resultado = sdr.readStream(stream, [buffer_rx], MUESTRAS_RX, timeoutUs=500000)

            if resultado.ret < 0:
                print(f"Error RX: {resultado.ret}")
                continue

            cantidad = resultado.ret
            if cantidad == 0:
                continue

            muestras = buffer_rx[:cantidad].copy()
            
            # --- OPTIMIZACIÓN: Detección de Energía Dinámica ---
            magnitud = np.abs(muestras)
            nivel_medio = np.mean(magnitud)
            nivel_maximo = np.max(magnitud)

            # DEBUG: Imprime el nivel máximo cada vez que lee el buffer para calibrar
            # print(f"DEBUG SDR - Max: {nivel_maximo:.4f} | Ruido: {nivel_medio:.4f}")

            # 1. Filtro estático y de piso de ruido
            if nivel_maximo < max(UMBRAL_NIVEL, nivel_medio * FACTOR_RUIDO_ESTATICO):
                continue

            # 2. Umbral referenciado al pico de la señal
            umbral_disparo = max(nivel_medio * FACTOR_RUIDO_DINAMICO, nivel_maximo * FACTOR_PICO_SEÑAL)
            
            indices_burst = np.where(magnitud > umbral_disparo)[0]
            if len(indices_burst) == 0:
                continue
                
            inicio_burst = indices_burst[0]

            # 3. Enventanado
            idx_inicio = max(0, inicio_burst - MARGEN_PREVIO_RX)
            idx_fin = min(len(muestras), idx_inicio + LONGITUD_VENTANA_RX)
            
            muestras_ventana = muestras[idx_inicio:idx_fin]

            # Validación extra: si el paquete cayó justo al final del buffer y se cortó
            if len(muestras_ventana) < MIN_MUESTRAS_VENTANA:
                print("Paquete descartado: cayó en el borde del buffer.")
                continue

            # SOLUCIÓN HACKRF: Eliminar el DC offset para centrar la señal en (0,0) antes de correlacionar
            muestras_ventana = muestras_ventana - np.mean(muestras_ventana)

            print(f"\nSeñal detectada. Max: {nivel_maximo:.3f} | Ruido: {nivel_medio:.3f} | Índice: {inicio_burst}")
            
            # 4. Procesamiento matemático sobre la ventana
            correlacion, inicio_relativo, f_shift_grueso = buscar_preambulo(muestras_ventana)

            if correlacion is None:
                continue

            if correlacion < UMBRAL_CORRELACION:
                print(f"Correlación descartada: {correlacion:.3f} (Inferior al umbral)")
                continue

            print(f"Correlación: {correlacion:.3f} | Inicio: {inicio_relativo} | Shift FFT: {f_shift_grueso:.1f} Hz")

            # Es vital pasar el f_shift_grueso a la función de análisis
            resultado_trama = analizar_trama(muestras_ventana, inicio_relativo, f_shift_grueso)

            if resultado_trama is None:
                print("Trama incompleta en la ventana de muestras.")
                continue

            # ============================================================
            # RECONSTRUIR PAQUETE Y MOSTRAR RESULTADOS
            # ============================================================
            
            bits = np.array([int(b) for b in resultado_trama["bits_datos"]], dtype=np.uint8)
            datos_rx = np.packbits(bits).tobytes()

            print("\n============================================")
            print("RESULTADO")
            print("============================================")
            print(f"Preámbulo recibido: {resultado_trama['bits_preambulo']}")
            print(f"Errores preámbulo: {resultado_trama['errores_preambulo']}\n")
            print("Bits de datos recibidos:\n" + resultado_trama["bits_datos"] + "\n")
            print(f"Bytes recibidos: {datos_rx.hex()}\n")

            try:
                print("Paquete interpretado:")
                print(describir_paquete(datos_rx))
            except ValueError as e:
                print(f"Error interpretando paquete: {e}")

            print(f"\nFase inicial: {np.degrees(resultado_trama['fase_inicial']):+.1f} grados")
            print(f"Variación de fase: {np.degrees(resultado_trama['pendiente_fase']):+.3f} grados/símbolo")
            print(f"Offset de frecuencia: {resultado_trama['frecuencia_offset']:+.1f} Hz\n")

            if resultado_trama["errores_preambulo"] == 0 and len(datos_rx) == TAMAÑO_PAQUETE_BYTES:
                print("PRUEBA SUPERADA: PREÁMBULO Y PAQUETE RECIBIDOS.\n")
            else:
                print("PRUEBA FALLIDA.\n")

    except KeyboardInterrupt:
        print("\nRX detenido.")
    finally:
        cerrar_sdr(sdr, stream)