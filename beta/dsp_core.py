import numpy as np
from config import (
    PREAMBULO, GUARDA, MUESTRAS_POR_BIT, SAMPLE_RATE, FREQ_CENTRAL,
    CFO_MAX_HZ, AMPLITUD_TX
)
from paquete import TAMAÑO_TRAMA_BYTES
from funciones_dsss import generar_codigo_pn, ensanchar

# ------------------------------------------------------------
# Constantes derivadas
# ------------------------------------------------------------
CANTIDAD_BITS_DATOS = TAMAÑO_TRAMA_BYTES * 8          # payload + CRC

TAPS_PN = [6, 1]
LONGITUD_PN = 63
PN_BIPOLAR = generar_codigo_pn(TAPS_PN, LONGITUD_PN)

CANTIDAD_CHIPS_DATOS = CANTIDAD_BITS_DATOS * LONGITUD_PN
N_PREAMBULO = len(PREAMBULO)

PREAMBULO_SIMBOLOS = np.array(
    [1.0 if b == "1" else -1.0 for b in PREAMBULO], dtype=np.float32)
GUARDA_SIMBOLOS = np.array(
    [1.0 if b == "1" else -1.0 for b in GUARDA], dtype=np.float32)

# Muestras que RX necesita (preambulo + datos; la guarda no hace falta)
N_SIMBOLOS_UTILES = N_PREAMBULO + CANTIDAD_CHIPS_DATOS
N_MUESTRAS_UTILES = N_SIMBOLOS_UTILES * MUESTRAS_POR_BIT
N_MUESTRAS_TRAMA = (N_SIMBOLOS_UTILES + len(GUARDA)) * MUESTRAS_POR_BIT

# ============================================================
# TX
# ============================================================

def generar_trama_dsss(bits_datos):
    chips = ensanchar(bits_datos, PN_BIPOLAR)
    trama = np.concatenate((PREAMBULO_SIMBOLOS, chips.astype(np.float32), GUARDA_SIMBOLOS))
    return np.repeat(trama, MUESTRAS_POR_BIT) * AMPLITUD_TX

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


def buscar_preambulo(muestras):
    """Devuelve (correlacion, inicio_fraccional, f_cfo) o (None, None, None)."""
    muestras = muestras - np.mean(muestras)
    f_cfo = estimar_cfo_grueso(muestras)
    t = np.arange(len(muestras)) / SAMPLE_RATE
    corr_x = muestras * np.exp(-2j * np.pi * f_cfo * t)
    T = periodo_chip(f_cfo)

    ref = PREAMBULO_SIMBOLOS.astype(np.complex64)
    L = N_PREAMBULO
    e_ref = float(np.sum(np.abs(ref) ** 2))

    mejor, mejor_ini = -1.0, None
    n_blk = int(len(corr_x) // T) - 1
    if n_blk < L:
        return None, None, None

    # busqueda gruesa: 8 fases enteras
    for off in range(MUESTRAS_POR_BIT):
        nsim = (len(corr_x) - off) // MUESTRAS_POR_BIT
        if nsim < L:
            continue
        s = corr_x[off:off + nsim * MUESTRAS_POR_BIT].reshape(nsim, MUESTRAS_POR_BIT).mean(axis=1)
        c = np.correlate(s, ref, mode="valid")
        en = np.convolve(np.abs(s) ** 2, np.ones(L, dtype=np.float32), mode="valid")
        cn = np.abs(c) / np.maximum(np.sqrt(en * e_ref), 1e-12)
        i = int(np.argmax(cn))
        if cn[i] > mejor:
            mejor, mejor_ini = float(cn[i]), off + i * MUESTRAS_POR_BIT

    # refinamiento fraccional (+-0.75 muestra) sobre el preambulo
    for d in np.arange(-0.75, 0.76, 0.25):
        ini = mejor_ini + d
        if ini < 0:
            continue
        s = integrar_simbolos(corr_x, ini, L, T)
        cn = abs(np.vdot(ref, s)) / max(np.sqrt(np.sum(np.abs(s) ** 2) * e_ref), 1e-12)
        if cn > mejor:
            mejor, mejor_ini = float(cn), ini
    return mejor, mejor_ini, f_cfo


def analizar_trama(muestras, inicio, f_cfo):
    n_necesarias = int(np.ceil(inicio + (N_SIMBOLOS_UTILES + 1) * periodo_chip(f_cfo)))
    if inicio < 0 or n_necesarias > len(muestras):
        return None

    muestras = muestras - np.mean(muestras)
    t = np.arange(len(muestras)) / SAMPLE_RATE
    x = muestras * np.exp(-2j * np.pi * f_cfo * t)
    T = periodo_chip(f_cfo)

    simb = integrar_simbolos(x, inicio, N_SIMBOLOS_UTILES, T)

    # --- Seguimiento de fase con el truco del cuadrado (preambulo + chips son +-1) ---
    # s^2 = A^2 e^{j2phi}: sin modulacion. Promedio movil -> fase lentamente variable.
    cuad = simb ** 2
    W = 2 * LONGITUD_PN + 1
    prom = np.convolve(cuad, np.ones(W) / W, mode="same")
    fase = 0.5 * np.unwrap(np.angle(prom))

    corr = simb * np.exp(-1j * fase)

    # resolver ambiguedad de pi con el preambulo conocido
    if np.real(np.sum(corr[:N_PREAMBULO] * PREAMBULO_SIMBOLOS)) < 0:
        corr = -corr
        fase = fase + np.pi

    pre = corr[:N_PREAMBULO]
    chips = corr[N_PREAMBULO:]

    # --- Despreading vectorizado ---
    bloques = chips.reshape(CANTIDAD_BITS_DATOS, LONGITUD_PN)
    corrs = np.real(bloques @ PN_BIPOLAR.astype(np.float64))
    bits = (corrs > 0).astype(np.uint8)

    bits_pre = "".join("1" if np.real(s) >= 0 else "0" for s in pre)
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
