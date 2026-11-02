import numpy as np
from config import (
    PREAMBULO, GUARDA, MUESTRAS_POR_BIT, SAMPLE_RATE, FREQ_CENTRAL,
    CFO_MAX_HZ, AMPLITUD_TX, USAR_RRC, BETA_RRC, SPAN_CHIPS_RRC
)
from paquete import TAMANIO_TRAMA_BYTES
from funciones_dsss import generar_codigo_pn, ensanchar, filtro_rrc

# ------------------------------------------------------------
# Constantes derivadas
# ------------------------------------------------------------
CANTIDAD_BITS_DATOS = TAMANIO_TRAMA_BYTES * 8          # payload + CRC

TAPS_PN = [6, 1]
LONGITUD_PN = 63
PN_BIPOLAR = generar_codigo_pn(TAPS_PN, LONGITUD_PN)

CANTIDAD_CHIPS_DATOS = CANTIDAD_BITS_DATOS * LONGITUD_PN

# El preambulo ahora es una secuencia de BITS que se ensancha con el mismo PN
# que los datos (cada bit del preambulo -> LONGITUD_PN chips).
PREAMBULO_BITS = np.array([int(b) for b in PREAMBULO], dtype=int)
N_BITS_PREAMBULO = len(PREAMBULO_BITS)
PREAMBULO_CHIPS = ensanchar(PREAMBULO_BITS, PN_BIPOLAR).astype(np.float32)
N_CHIPS_PREAMBULO = len(PREAMBULO_CHIPS)              # = N_BITS_PREAMBULO * LONGITUD_PN

GUARDA_SIMBOLOS = np.array(
    [1.0 if b == "1" else -1.0 for b in GUARDA], dtype=np.float32)

# Muestras que RX necesita (preambulo + datos; la guarda no hace falta)
N_SIMBOLOS_UTILES = N_CHIPS_PREAMBULO + CANTIDAD_CHIPS_DATOS
N_MUESTRAS_UTILES = N_SIMBOLOS_UTILES * MUESTRAS_POR_BIT
N_MUESTRAS_TRAMA = (N_SIMBOLOS_UTILES + len(GUARDA)) * MUESTRAS_POR_BIT

# ------------------------------------------------------------
# Filtro RRC (pulse shaping en TX / filtro adaptado en RX)
# ------------------------------------------------------------
if USAR_RRC:
    N_TAPS_RRC = SPAN_CHIPS_RRC * MUESTRAS_POR_BIT + 1      # impar -> retardo entero
    H_RRC = filtro_rrc(BETA_RRC, MUESTRAS_POR_BIT, N_TAPS_RRC)
    RETARDO_PULSO = (N_TAPS_RRC - 1) // 2   # muestras de cola del filtro tras el ultimo chip
else:
    N_TAPS_RRC = 0
    H_RRC = None
    RETARDO_PULSO = 0


def _filtrar_rrc(x):
    """Filtro adaptado (mismo RRC que el TX). Salida con el mismo largo que x."""
    return np.convolve(x, H_RRC, mode="same")


def _muestrear_en_pico(xf, inicio, n_simb, T):
    """
    Toma 1 valor por chip de la senal ya filtrada, en inicio + k*T (T fraccionario,
    compensa la deriva de reloj). Con RRC 'inicio' es el instante del PICO del chip 0.
    """
    pos = inicio + T * np.arange(n_simb)
    idx = np.arange(len(xf))
    return np.interp(pos, idx, xf.real) + 1j * np.interp(pos, idx, xf.imag)

# ============================================================
# TX
# ============================================================

def generar_trama_dsss(bits_datos):
    chips = ensanchar(bits_datos, PN_BIPOLAR)
    trama = np.concatenate((PREAMBULO_CHIPS, chips.astype(np.float32), GUARDA_SIMBOLOS))
    if not USAR_RRC:
        return np.repeat(trama, MUESTRAS_POR_BIT) * AMPLITUD_TX      # pulso rectangular

    # RRC: impulsos (no repeticion) + convolucion. mode='full' no recorta ningun chip;
    # el chip k queda centrado en la muestra k*MUESTRAS_POR_BIT + RETARDO_PULSO.
    up = np.zeros(len(trama) * MUESTRAS_POR_BIT, dtype=np.float32)
    up[::MUESTRAS_POR_BIT] = trama
    y = np.convolve(up, H_RRC, mode="full")
    # Normalizar por el PICO: el RRC tiene picos mayores que los chips y saturaria el DAC
    return (y / np.max(np.abs(y)) * AMPLITUD_TX).astype(np.float32)

# ============================================================
# RX
# ============================================================

def detectar_rafaga(muestras, desde=0):
    """
    Devuelve (indice_inicio, nivel_ruido) o (None, nivel_ruido).
    Usa nivel suavizado (promedio movil) para ignorar picos de ruido sueltos
    y un piso de ruido robusto (percentil 10) en vez de un umbral absoluto fijo.
    """
    from config import UMBRAL_NIVEL, FACTOR_UMBRAL_RAFAGA, SUAVIZADO_RAFAGA
    mag = np.abs(muestras)
    L = SUAVIZADO_RAFAGA
    cs = np.cumsum(np.concatenate(([0.0], mag)), dtype=np.float64)
    suave = (cs[L:] - cs[:-L]) / L                    # suave[i] = media de mag[i:i+L]
    ruido = float(np.percentile(suave[::8], 10))
    umbral = max(UMBRAL_NIVEL, ruido * FACTOR_UMBRAL_RAFAGA)
    idx = np.where(suave[desde:] > umbral)[0]
    if len(idx) == 0:
        return None, ruido
    return desde + int(idx[0]), ruido


def estimar_cfo_grueso(muestras):
    """
    BPSK/DSSS con chips +-1: al elevar al cuadrado la modulacion desaparece y
    queda un tono a 2*f. FFT de TODA la ventana (zero-padded) -> resolucion ~8 Hz.
    Rango de busqueda: +-CFO_MAX_HZ (en el dominio del cuadrado: +-2*CFO_MAX_HZ).
    """
    cuad = muestras.astype(np.complex128) ** 2
    nfft = 1 << int(np.ceil(np.log2(len(cuad))))
    esp = np.abs(np.fft.fft(cuad, nfft))
    freqs = np.fft.fftfreq(nfft, d=1.0 / SAMPLE_RATE)
    esp[np.abs(freqs) > 2.0 * CFO_MAX_HZ] = 0.0
    k = int(np.argmax(esp))
    # interpolacion parabolica del pico
    if 0 < k < nfft - 1 and esp[k - 1] > 0 and esp[k + 1] > 0:
        a, b, c = np.log(esp[k - 1] + 1e-30), np.log(esp[k] + 1e-30), np.log(esp[k + 1] + 1e-30)
        den = a - 2 * b + c
        delta = 0.5 * (a - c) / den if den != 0 else 0.0
    else:
        delta = 0.0
    return (freqs[k] + delta * (freqs[1] - freqs[0])) / 2.0


def periodo_chip(f_cfo):
    """
    Largo del chip en muestras RX. Si TX y RX derivan LO y reloj de muestreo de un
    mismo cristal (B200 y HackRF lo hacen), el error en ppm del reloj es el mismo
    que el del portador: ppm = f_cfo / fc.
    """
    return MUESTRAS_POR_BIT * (1.0 - f_cfo / FREQ_CENTRAL)


def integrar_simbolos(x, inicio, n_simb, T):
    """Integrate & dump con periodo fraccionario T (compensa deriva de reloj)."""
    cs = np.concatenate(([0.0 + 0j], np.cumsum(x, dtype=np.complex128)))
    bordes = inicio + T * np.arange(n_simb + 1)
    pos = np.arange(len(cs))
    c = np.interp(bordes, pos, cs.real) + 1j * np.interp(bordes, pos, cs.imag)
    return (c[1:] - c[:-1]) / T


def _correlacion_normalizada(s, ref, e_ref):
    """
    Correlacion cruzada normalizada |<s[k:k+L], ref>| / (||s[k:k+L]|| * ||ref||)
    para todos los desfases k (via FFT: el preambulo ensanchado tiene ~10^3 chips,
    la correlacion directa seria demasiado lenta).
    """
    L = len(ref)
    n = len(s)
    nfft = 1 << int(np.ceil(np.log2(n + L)))
    c = np.fft.ifft(np.fft.fft(s, nfft) * np.conj(np.fft.fft(ref, nfft)))[:n - L + 1]
    cs = np.concatenate(([0.0], np.cumsum(np.abs(s) ** 2, dtype=np.float64)))
    en = cs[L:] - cs[:-L]
    return np.abs(c) / np.maximum(np.sqrt(en * e_ref), 1e-12)


def buscar_preambulo(muestras, max_inicio=None):
    """
    Devuelve (correlacion, inicio_fraccional, f_cfo) o (None, None, None).
    El preambulo esta ensanchado con el mismo PN que los datos: se correlaciona
    contra los N_CHIPS_PREAMBULO chips completos (ganancia de procesamiento
    LONGITUD_PN x N_BITS_PREAMBULO).

    max_inicio: si se indica, el preambulo solo se busca en los primeros
    'max_inicio' muestras de la ventana. Como preambulo y datos usan el mismo
    PN, los datos tienen desfases alineados a bit que se parecen al preambulo
    (hasta ~0.7-0.9 de correlacion); acotar la zona de busqueda evita engancharse
    a los datos y, de paso, reduce ~9x el costo de la correlacion.
    """
    muestras = muestras - np.mean(muestras)
    f_cfo = estimar_cfo_grueso(muestras)
    t = np.arange(len(muestras)) / SAMPLE_RATE
    corr_x = muestras * np.exp(-2j * np.pi * f_cfo * t)
    T = periodo_chip(f_cfo)

    ref = PREAMBULO_CHIPS.astype(np.complex64)
    L = N_CHIPS_PREAMBULO
    e_ref = float(np.sum(np.abs(ref) ** 2))

    n_blk = int(len(corr_x) // T) - 1
    if n_blk < L:
        return None, None, None

    # zona donde se admite que empiece el preambulo
    zona = corr_x
    if max_inicio is not None:
        n_corte = int(max_inicio + (L + 2) * MUESTRAS_POR_BIT + MUESTRAS_POR_BIT) + N_TAPS_RRC
        zona = corr_x[:n_corte]

    # con RRC: filtro adaptado UNA vez sobre la zona (ya sin CFO)
    zf = _filtrar_rrc(zona) if USAR_RRC else None

    # busqueda gruesa: MUESTRAS_POR_BIT fases enteras
    mejor, mejor_ini = -1.0, None
    for off in range(MUESTRAS_POR_BIT):
        nsim = (len(zona) - off) // MUESTRAS_POR_BIT
        if nsim < L:
            continue
        if USAR_RRC:
            s = zf[off::MUESTRAS_POR_BIT]            # 1 muestra por chip, en el pico
        else:
            s = zona[off:off + nsim * MUESTRAS_POR_BIT].reshape(nsim, MUESTRAS_POR_BIT).mean(axis=1)
        cn = _correlacion_normalizada(s, ref, e_ref)
        i = int(np.argmax(cn))
        if cn[i] > mejor:
            mejor, mejor_ini = float(cn[i]), off + i * MUESTRAS_POR_BIT

    # refinamiento fraccional (+-0.75 muestra) sobre el preambulo completo
    for d in np.arange(-0.75, 0.76, 0.25):
        ini = mejor_ini + d
        if ini < 0:
            continue
        s = (_muestrear_en_pico(zf, ini, L, T) if USAR_RRC
             else integrar_simbolos(corr_x, ini, L, T))
        cn = abs(np.vdot(ref, s)) / max(np.sqrt(np.sum(np.abs(s) ** 2) * e_ref), 1e-12)
        if cn > mejor:
            mejor, mejor_ini = float(cn), ini
    return mejor, mejor_ini, f_cfo


def analizar_trama(muestras, inicio, f_cfo):
    n_necesarias = int(np.ceil(inicio + (N_SIMBOLOS_UTILES + 1) * periodo_chip(f_cfo))) + RETARDO_PULSO
    if inicio < 0 or n_necesarias > len(muestras):
        return None

    muestras = muestras - np.mean(muestras)
    t = np.arange(len(muestras)) / SAMPLE_RATE
    x = muestras * np.exp(-2j * np.pi * f_cfo * t)
    T = periodo_chip(f_cfo)

    if USAR_RRC:
        simb = _muestrear_en_pico(_filtrar_rrc(x), inicio, N_SIMBOLOS_UTILES, T)
    else:
        simb = integrar_simbolos(x, inicio, N_SIMBOLOS_UTILES, T)

    # --- Seguimiento de fase con el truco del cuadrado (preambulo + chips son +-1) ---
    # s^2 = A^2 e^{j2phi}: sin modulacion. Promedio movil -> fase lentamente variable.
    cuad = simb ** 2
    W = 2 * LONGITUD_PN + 1
    prom = np.convolve(cuad, np.ones(W) / W, mode="same")
    fase = 0.5 * np.unwrap(np.angle(prom))

    corr = simb * np.exp(-1j * fase)

    # resolver ambiguedad de pi con el preambulo conocido (ya ensanchado)
    if np.real(np.sum(corr[:N_CHIPS_PREAMBULO] * PREAMBULO_CHIPS)) < 0:
        corr = -corr
        fase = fase + np.pi

    pre = corr[:N_CHIPS_PREAMBULO]
    chips = corr[N_CHIPS_PREAMBULO:]

    # --- Despreading vectorizado ---
    bloques = chips.reshape(CANTIDAD_BITS_DATOS, LONGITUD_PN)
    corrs = np.real(bloques @ PN_BIPOLAR.astype(np.float64))
    bits = (corrs > 0).astype(np.uint8)

    # el preambulo tambien se desensancha: se compara bit a bit con PREAMBULO
    corrs_pre = np.real(pre.reshape(N_BITS_PREAMBULO, LONGITUD_PN) @ PN_BIPOLAR.astype(np.float64))
    bits_pre = "".join("1" if c > 0 else "0" for c in corrs_pre)
    errores_pre = sum(a != b for a, b in zip(bits_pre, PREAMBULO))

    pend = float(np.polyfit(np.arange(len(fase)), fase, 1)[0])
    return {
        "bits_preambulo": bits_pre,
        "bits": bits,
        "errores_preambulo": errores_pre,
        "calidad": float(np.mean(np.abs(corrs)) / LONGITUD_PN),
        "pendiente_fase": pend,
        "fase_inicial": float(fase[0]),
        "frecuencia_offset": f_cfo + pend * (SAMPLE_RATE / T) / (2 * np.pi),
    }
