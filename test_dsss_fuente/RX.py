import numpy as np
import SoapySDR

from SoapySDR import (
    SOAPY_SDR_RX,
    SOAPY_SDR_CF32
)

from config import (
    FREQ_CENTRAL,
    SAMPLE_RATE,
    CANAL_SDR,
    ANTENA_RX,
    GANANCIA_RX,
    MUESTRAS_POR_BIT,
    PREAMBULO,
    GUARDA,
    UMBRAL_NIVEL,
    UMBRAL_CORRELACION,
    MUESTRAS_RX,
    LONGITUD_PN,
    TAPS_PN
)

from paquete import (
    TAMAÑO_PAQUETE_BYTES,
    interpretar_paquete,
    describir_paquete,
    LUZ_MAX,
    LUZ_MIN,
    TEMPERATURA_MAX,
    TEMPERATURA_MIN,
    HUMEDAD_MAX,
    HUMEDAD_MIN
)

from funciones_dsss import (
    generar_codigo_pn,
    despreader,
    refinar_fase
)

# ============================================================
# CONSTANTES
# ============================================================

CANTIDAD_BITS_DATOS = TAMAÑO_PAQUETE_BYTES * 8
CANTIDAD_CHIPS_DATOS = CANTIDAD_BITS_DATOS * LONGITUD_PN
CANTIDAD_SIMBOLOS_TRAMA = len(PREAMBULO) + CANTIDAD_CHIPS_DATOS + len(GUARDA)
MUESTRAS_TRAMA = CANTIDAD_SIMBOLOS_TRAMA * MUESTRAS_POR_BIT

PREAMBULO_SIMBOLOS = np.array(
    [1.0 if bit == "1" else -1.0 for bit in PREAMBULO],
    dtype=np.float32
)

# ============================================================
# CÓDIGO PN
# ============================================================

pn_bipolar = generar_codigo_pn(TAPS_PN, LONGITUD_PN)


# ============================================================
# MEDICIÓN DE NIVEL
# ============================================================

def calcular_nivel_db(muestras):
    potencia = np.mean(np.abs(muestras) ** 2)
    return 10.0 * np.log10(max(potencia, 1e-12))


# ============================================================
# BÚSQUEDA DEL PREÁMBULO
# ============================================================

def buscar_preambulo(muestras):
    mejor_correlacion = -1.0
    mejor_inicio = None
    referencia = PREAMBULO_SIMBOLOS.astype(np.complex64)
    longitud = len(PREAMBULO)

    for offset in range(MUESTRAS_POR_BIT):
        muestras_offset = muestras[offset:]
        cantidad_simbolos = len(muestras_offset) // MUESTRAS_POR_BIT

        if cantidad_simbolos < longitud:
            continue

        muestras_offset = muestras_offset[:cantidad_simbolos * MUESTRAS_POR_BIT]
        bloques = muestras_offset.reshape(cantidad_simbolos, MUESTRAS_POR_BIT)
        simbolos = np.mean(bloques, axis=1)

        correlaciones = np.correlate(simbolos, referencia, mode="valid")
        energia_rx = np.convolve(
            np.abs(simbolos) ** 2,
            np.ones(longitud, dtype=np.float32),
            mode="valid"
        )
        energia_ref = np.sum(np.abs(referencia) ** 2)
        denominador = np.sqrt(energia_rx * energia_ref)
        correlaciones_normalizadas = np.abs(correlaciones) / np.maximum(denominador, 1e-12)

        indice = np.argmax(correlaciones_normalizadas)
        correlacion = correlaciones_normalizadas[indice]

        if correlacion > mejor_correlacion:
            mejor_correlacion = correlacion
            mejor_inicio = offset + indice * MUESTRAS_POR_BIT

    if mejor_inicio is None:
        return None, None

    return mejor_correlacion, mejor_inicio


# ============================================================
# ESTIMACIÓN DE OFFSET DE FRECUENCIA
# ============================================================

def estimar_offset_frecuencia(simbolos_preambulo):
    corregidos = simbolos_preambulo * PREAMBULO_SIMBOLOS
    fases = np.unwrap(np.angle(corregidos))
    indices = np.arange(len(fases), dtype=np.float64)
    pesos = np.maximum(np.abs(corregidos) ** 2, 1e-12)

    pendiente, fase_inicial = np.polyfit(indices, fases, 1, w=pesos)

    tasa_simbolos = SAMPLE_RATE / MUESTRAS_POR_BIT
    frecuencia_offset = pendiente * tasa_simbolos / (2.0 * np.pi)

    return pendiente, fase_inicial, frecuencia_offset


# ============================================================
# ANÁLISIS DE TRAMA
# ============================================================

def analizar_trama(muestras, inicio):
    fin = inicio + MUESTRAS_TRAMA

    if inicio < 0 or fin > len(muestras):
        return None

    trama = muestras[inicio:fin]
    nivel_db = calcular_nivel_db(trama)

    bloques = trama.reshape(CANTIDAD_SIMBOLOS_TRAMA, MUESTRAS_POR_BIT)
    simbolos = np.mean(bloques, axis=1)

    n_preambulo = len(PREAMBULO)
    simbolos_preambulo = simbolos[:n_preambulo]

    pendiente_fase, fase_inicial, frecuencia_offset = estimar_offset_frecuencia(simbolos_preambulo)

    indices_simbolos = np.arange(CANTIDAD_SIMBOLOS_TRAMA, dtype=np.float64)
    fase_simbolos = fase_inicial + pendiente_fase * indices_simbolos
    simbolos_corregidos = simbolos * np.exp(-1j * fase_simbolos)

    simbolos_datos = simbolos_corregidos[n_preambulo:n_preambulo + CANTIDAD_CHIPS_DATOS]

    simbolos_datos, pendiente_residual = refinar_fase(simbolos_datos, pn_bipolar)

    bits_datos, _ = despreader(simbolos_datos, pn_bipolar)

    return {
        "bits_datos": bits_datos,
        "nivel_db": nivel_db,
        "pendiente_residual": pendiente_residual,
        "pendiente_fase": pendiente_fase,
        "fase_inicial": fase_inicial,
        "frecuencia_offset": frecuencia_offset
    }


# ============================================================
# VALIDAR PAQUETE
# ============================================================

def validar_paquete(datos):
    if len(datos) != TAMAÑO_PAQUETE_BYTES:
        return False
    try:
        numero, temperatura, humedad, luz = interpretar_paquete(datos)
    except ValueError:
        return False
    if not np.isfinite(temperatura) or not np.isfinite(humedad):
        return False
    if not (TEMPERATURA_MIN <= temperatura <= TEMPERATURA_MAX):
        return False
    if not (HUMEDAD_MIN <= humedad <= HUMEDAD_MAX):
        return False
    if not (LUZ_MIN <= luz <= LUZ_MAX):
        return False
    return True


# ============================================================
# SDR
# ============================================================

sdr = SoapySDR.Device("driver=uhd")
sdr.setSampleRate(SOAPY_SDR_RX, CANAL_SDR, SAMPLE_RATE)
sdr.setFrequency(SOAPY_SDR_RX, CANAL_SDR, FREQ_CENTRAL)
sdr.setGain(SOAPY_SDR_RX, CANAL_SDR, GANANCIA_RX)
sdr.setAntenna(SOAPY_SDR_RX, CANAL_SDR, ANTENA_RX)

stream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
sdr.activateStream(stream)


# ============================================================
# INFORMACIÓN
# ============================================================

print()
print("============================================")
print("RECEPTOR DSSS-BPSK - ENSAYO DE DISTANCIA")
print("============================================")
print(f"Frecuencia : {FREQ_CENTRAL / 1e6:.3f} MHz")
print(f"Sample rate: {SAMPLE_RATE / 1e6:.3f} Msps")
print(f"Ganancia RX: {GANANCIA_RX}")
print(f"Antena     : {ANTENA_RX}")
print()
print("RANGOS VÁLIDOS")
print("--------------------------------------------")
print(f"Temperatura : {TEMPERATURA_MIN:.1f} a {TEMPERATURA_MAX:.1f} °C")
print(f"Humedad     : {HUMEDAD_MIN:.1f} a {HUMEDAD_MAX:.1f} %")
print(f"Luz         : {LUZ_MIN} a {LUZ_MAX}")
print()
print("MEDICIÓN DE NIVEL")
print("--------------------------------------------")
print("Nivel = potencia media de las muestras IQ")
print("Escala relativa, no dBm calibrados.")
print("Ganancia RX fija para comparar distancias.")
print()
print("Diagnóstico por paquete:")
print("  Nro    = número de secuencia asignado por el TX")
print("  Perd   = paquetes perdidos detectados (salto en Nro)")
print("  Corr   = correlación normalizada del preámbulo (0 a 1)")
print("  FOff   = offset de frecuencia estimado (Hz)")
print()
print("Esperando paquetes...")
print()


# ============================================================
# BUFFER
# ============================================================

buffer_rx = np.zeros(MUESTRAS_RX, dtype=np.complex64)
buffer_acumulado = np.zeros(0, dtype=np.complex64)


# ============================================================
# CONTADORES Y ESTADÍSTICAS
# ============================================================

contador_paquetes = 0
contador_validos = 0
contador_invalidos = 0

ultimo_numero_valido = None
total_perdidos = 0

niveles = []


# ============================================================
# RECEPCIÓN
# ============================================================

try:
    while True:
        resultado = sdr.readStream(stream, [buffer_rx], MUESTRAS_RX)

        if resultado.ret < 0:
            print(f"Error RX: {resultado.ret}")
            continue

        cantidad = resultado.ret
        if cantidad == 0:
            continue

        nuevas_muestras = buffer_rx[:cantidad].copy()
        muestras = np.concatenate((buffer_acumulado, nuevas_muestras))

        # ----------------------------------------------------
        # Mantener cola
        # ----------------------------------------------------
        if len(muestras) > MUESTRAS_TRAMA:
            buffer_acumulado = muestras[-MUESTRAS_TRAMA:]
        else:
            buffer_acumulado = muestras

        # ----------------------------------------------------
        # Detectar actividad
        # ----------------------------------------------------
        nivel_maximo = np.max(np.abs(muestras))
        if nivel_maximo < UMBRAL_NIVEL:
            continue

        # ----------------------------------------------------
        # Buscar preámbulo
        # ----------------------------------------------------
        correlacion, inicio = buscar_preambulo(muestras)

        if correlacion is None:
            continue
        if correlacion < UMBRAL_CORRELACION:
            continue

        # ----------------------------------------------------
        # Analizar trama
        # ----------------------------------------------------
        resultado_trama = analizar_trama(muestras, inicio)

        if resultado_trama is None:
            buffer_acumulado = muestras[inicio:]
            continue

        # ----------------------------------------------------
        # Recuperar datos
        # ----------------------------------------------------
        bits_datos = resultado_trama["bits_datos"]
        datos_rx = np.packbits(bits_datos).tobytes()

        nivel_db = resultado_trama["nivel_db"]
        freq_offset = resultado_trama["frecuencia_offset"]

        niveles.append(nivel_db)
        contador_paquetes += 1

        # ----------------------------------------------------
        # Validar paquete + detectar pérdidas por número de secuencia
        # ----------------------------------------------------
        paquete_valido = validar_paquete(datos_rx)
        perdidos = 0
        numero_pkt = None

        if paquete_valido:
            contador_validos += 1
            estado = "VALIDO"
            numero_pkt, _, _, _ = interpretar_paquete(datos_rx)

            if ultimo_numero_valido is not None and numero_pkt > ultimo_numero_valido:
                perdidos = numero_pkt - ultimo_numero_valido - 1
                total_perdidos += perdidos

            ultimo_numero_valido = numero_pkt
        else:
            contador_invalidos += 1
            estado = "INVALIDO"

        # ----------------------------------------------------
        # Mostrar paquete — diagnóstico en una sola línea
        # ----------------------------------------------------
        nro_str = f"{numero_pkt:06d}" if numero_pkt is not None else "??????"
        perdidos_str = f"+{perdidos}" if perdidos > 0 else "-"

        print(
            f"#{contador_paquetes:04d} | Nro:{nro_str} | Perd:{perdidos_str:>3s} | "
            f"Nivel:{nivel_db:6.1f}dB | Corr:{correlacion:.2f} | "
            f"FOff:{freq_offset:+6.0f}Hz | {estado:8s} | {describir_paquete(datos_rx)}"
        )

        # ----------------------------------------------------
        # Estadísticas cada 10 paquetes
        # ----------------------------------------------------
        if contador_paquetes % 10 == 0:
            nivel_minimo = min(niveles)
            nivel_maximo = max(niveles)
            nivel_promedio = np.mean(niveles)

            print()
            print("--------------------------------------------")
            print("ESTADISTICAS")
            print("--------------------------------------------")
            print(f"Paquetes recibidos : {contador_paquetes}")
            print(f"Paquetes válidos   : {contador_validos}")
            print(f"Paquetes inválidos : {contador_invalidos}")
            print(f"Paquetes perdidos  : {total_perdidos} (detectados por salto en Nro)")
            print(f"Nivel mínimo       : {nivel_minimo:.2f} dB")
            print(f"Nivel máximo       : {nivel_maximo:.2f} dB")
            print(f"Nivel promedio     : {nivel_promedio:.2f} dB")

            if contador_paquetes > 0:
                porcentaje_validos = 100.0 * contador_validos / contador_paquetes
                print(f"Tasa de paquetes válidos: {porcentaje_validos:.1f} %")

            print("--------------------------------------------")
            print()

            niveles = []

        # ----------------------------------------------------
        # Eliminar trama procesada
        # ----------------------------------------------------
        buffer_acumulado = muestras[inicio + MUESTRAS_TRAMA:]

except KeyboardInterrupt:
    print()
    print("============================================")
    print("ENSAYO FINALIZADO")
    print("============================================")
    print(f"Paquetes recibidos : {contador_paquetes}")
    print(f"Paquetes válidos   : {contador_validos}")
    print(f"Paquetes inválidos : {contador_invalidos}")
    print(f"Paquetes perdidos  : {total_perdidos} (detectados por salto en Nro)")

    if contador_paquetes > 0:
        porcentaje_validos = 100.0 * contador_validos / contador_paquetes
        print(f"Tasa de paquetes válidos: {porcentaje_validos:.1f} %")

    if len(niveles) > 0:
        print()
        print(f"Nivel mínimo restante: {min(niveles):.2f} dB")
        print(f"Nivel máximo restante: {max(niveles):.2f} dB")
        print(f"Nivel promedio restante: {np.mean(niveles):.2f} dB")

    print()
    print("RX detenido.")

finally:
    sdr.deactivateStream(stream)
    sdr.closeStream(stream)