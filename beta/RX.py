import time
import numpy as np

from config import (
    FREQ_CENTRAL, SAMPLE_RATE, CANAL_SDR, ANTENA_RX, 
    GANANCIA_RX, PREAMBULO, GUARDA, UMBRAL_NIVEL, 
    UMBRAL_CORRELACION, MUESTRAS_RX, SDR_ARGS
)
from paquete import TAMAÑO_PAQUETE_BYTES, describir_paquete
from dsp_core import buscar_preambulo, analizar_trama, CANTIDAD_BITS_DATOS
from sdr_utils import inicializar_sdr, cerrar_sdr

# ============================================================
# INFORMACIÓN
# ============================================================

print("\n============================================")
print("RECEPTOR BPSK - DATOS REALES (OPTIMIZADO)")
print("============================================")
print(f"Frecuencia : {FREQ_CENTRAL / 1e6:.3f} MHz")
print(f"Sample rate: {SAMPLE_RATE / 1e6:.3f} Msps")
print(f"Ganancia   : {GANANCIA_RX}")
print(f"Antena     : {ANTENA_RX}\n")
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
        'RX', SDR_ARGS, SAMPLE_RATE, FREQ_CENTRAL, GANANCIA_RX, ANTENA_RX, CANAL_SDR
    )
    
    print("Esperando señal...\n")

    while True:
        resultado = sdr.readStream(stream, [buffer_rx], MUESTRAS_RX)

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

        # 1. Filtro estático y de piso de ruido
        if nivel_maximo < max(UMBRAL_NIVEL, nivel_medio * 3.0):
            continue

        # 2. CORRECCIÓN: Umbral referenciado al pico de la señal (40% del máximo)
        # Esto evita disparos en falso por picos de estática aleatorios.
        umbral_disparo = max(nivel_medio * 5.0, nivel_maximo * 0.4)
        
        indices_burst = np.where(magnitud > umbral_disparo)[0]
        if len(indices_burst) == 0:
            continue
            
        inicio_burst = indices_burst[0]

        # 3. Enventanado
        MARGEN_PREVIO = 500
        LONGITUD_VENTANA = 4000
        
        idx_inicio = max(0, inicio_burst - MARGEN_PREVIO)
        idx_fin = min(len(muestras), idx_inicio + LONGITUD_VENTANA)
        
        muestras_ventana = muestras[idx_inicio:idx_fin]

        # Validación extra: si el paquete cayó justo al final del buffer y se cortó
        if len(muestras_ventana) < 2000:
            print("Paquete descartado: cayó en el borde del buffer.")
            continue

        print(f"\nSeñal detectada. Max: {nivel_maximo:.3f} | Ruido: {nivel_medio:.3f} | Índice: {inicio_burst}")
        
        # 4. Procesamiento matemático sobre la ventana
        correlacion, inicio_relativo = buscar_preambulo(muestras_ventana)

        if correlacion is None:
            continue

        if correlacion < UMBRAL_CORRELACION:
            print(f"Correlación descartada: {correlacion:.3f} (Inferior al umbral)")
            continue

        print(f"Correlación: {correlacion:.3f} | Inicio relativo: {inicio_relativo}")

        resultado_trama = analizar_trama(muestras_ventana, inicio_relativo)

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