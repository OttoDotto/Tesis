#!/usr/bin/env python3
"""
comparar_rrc.py - Compara el pulso rectangular (antes) contra el filtro RRC (ahora).
No necesita SDR: usa el codigo real del proyecto (dsp_core) y simula el canal.

Uso (desde la carpeta del proyecto):
    python comparar_rrc.py               # todo (~2-3 min)
    python comparar_rrc.py --rapido      # solo senal / espectro / ojo (segundos)
    python comparar_rrc.py --pruebas 30  # mas tramas por punto en la curva de sensibilidad
    python comparar_rrc.py --no-show     # solo guarda los PNG, no abre ventanas

Genera:
    comparacion_rrc_senal.png         (pulso, forma de onda, espectro, diagrama de ojo)
    comparacion_rrc_sensibilidad.png  (% de paquetes recibidos vs ruido)

Requiere: numpy y matplotlib  (pip install numpy matplotlib)
"""
import argparse
import importlib
import time

import numpy as np
import matplotlib

ap = argparse.ArgumentParser()
ap.add_argument("--rapido", action="store_true", help="omite la curva de sensibilidad")
ap.add_argument("--pruebas", type=int, default=15, help="tramas por punto de la curva")
ap.add_argument("--no-show", action="store_true", help="no abrir ventanas")
args = ap.parse_args()
if args.no_show:
    matplotlib.use("Agg")
import matplotlib.pyplot as plt

import config as C
import dsp_core as D
from funciones_dsss import ensanchar
from paquete import agregar_crc, verificar_crc, generar_paquete_ejemplo

FS = C.SAMPLE_RATE
SPS = C.MUESTRAS_POR_BIT
RC = FS / SPS                                   # tasa de chips [chips/s]
COL = {"rect": "tab:red", "rrc": "tab:blue", "rrc_rms": "tab:green"}

payload = generar_paquete_ejemplo(False)
bits = np.unpackbits(np.frombuffer(agregar_crc(payload), np.uint8)).astype(int)


def cargar_dsp(usar_rrc):
    """Recarga dsp_core con USAR_RRC = True/False (devuelve el mismo objeto modulo)."""
    C.USAR_RRC = usar_rrc
    return importlib.reload(D)


# =====================================================================
# 1) Senales TX con el codigo real del proyecto
# =====================================================================
datos = {}
for nombre, flag in (("rect", False), ("rrc", True)):
    d = cargar_dsp(flag)
    tx = d.generar_trama_dsss(bits).astype(np.float64)
    chips = np.concatenate((d.PREAMBULO_CHIPS, ensanchar(bits, d.PN_BIPOLAR))).astype(float)
    datos[nombre] = dict(tx=tx, chips=chips, h=d.H_RRC)
BETA = C.BETA_RRC
H = datos["rrc"]["h"]
chips = datos["rrc"]["chips"]


def metricas(x):
    pico = np.max(np.abs(x))
    rms = np.sqrt(np.mean(x ** 2))
    X = np.abs(np.fft.fft(x, 1 << 20)) ** 2
    f = np.fft.fftfreq(1 << 20, 1 / FS)
    tot = X.sum()
    cum = np.cumsum(np.fft.fftshift(X)) / tot
    fs_ = np.fft.fftshift(f)
    bw99 = fs_[np.searchsorted(cum, 0.995)] - fs_[np.searchsorted(cum, 0.005)]
    borde = RC * (1 + BETA) / 2
    oob1 = 10 * np.log10(X[np.abs(f) > borde].sum() / tot)
    oob2 = 10 * np.log10(X[np.abs(f) > RC].sum() / tot)
    return dict(pico=pico, rms=rms, papr=20 * np.log10(pico / rms), bw99=bw99 / 1e3,
                oob1=oob1, oob2=oob2, borde=borde / 1e3)


M = {k: metricas(v["tx"]) for k, v in datos.items()}


def psd(x, nseg=8192):
    """Periodograma promediado (Hann, 50% solape), normalizado a potencia total 1."""
    w = np.hanning(nseg)
    acc = np.zeros(nseg)
    n = 0
    for i in range(0, len(x) - nseg, nseg // 2):
        acc += np.abs(np.fft.fft(x[i:i + nseg] * w)) ** 2
        n += 1
    acc /= n
    f = np.fft.fftshift(np.fft.fftfreq(nseg, 1 / FS)) / 1e3
    return f, np.fft.fftshift(acc) / acc.sum()


def salida_rx(tx, usar_rrc):
    """Salida del receptor y funcion que da el indice de muestreo del chip k."""
    if usar_rrc:
        y = np.convolve(tx, H, "full")                       # filtro adaptado
        return y, lambda k: k * SPS + 2 * ((len(H) - 1) // 2)
    y = np.convolve(tx, np.ones(SPS) / SPS, "full")          # integrate & dump
    return y, lambda k: k * SPS + SPS - 1


def ojo(ax, tx, usar_rrc, color, titulo, sigma, rng):
    y, idx = salida_rx(tx + sigma * rng.standard_normal(len(tx)), usar_rrc)
    ks = np.arange(300, 1500)
    ref = np.median(np.abs(y[[idx(k) for k in ks]]))
    t = np.arange(-SPS, SPS + 1) / SPS
    for k in ks[::2]:
        s = idx(k)
        ax.plot(t, y[s - SPS:s + SPS + 1] / ref, color=color, alpha=0.12, lw=0.8)
    ax.axvline(0, color="k", ls=":", lw=1)
    ax.set_title(titulo)
    ax.set_xlabel("tiempo [chips] (0 = instante de decision)")
    ax.set_ylim(-2.2, 2.2)
    ax.grid(alpha=0.3)


# =====================================================================
# Figura 1: senal, espectro, ojo
# =====================================================================
rng = np.random.default_rng(3)
fig, ax = plt.subplots(2, 3, figsize=(17, 9))
fig.suptitle("Pulso rectangular (antes) vs filtro RRC (ahora)   |   "
             f"{RC / 1e3:.0f} kchip/s, {SPS} muestras/chip, beta = {BETA}", fontsize=14)

# (0,0) un chip aislado
a = ax[0, 0]
n_r = np.arange(SPS)
a.step(np.r_[n_r, SPS] / SPS - 0.5, np.r_[np.ones(SPS), 1], where="post", color=COL["rect"],
       lw=2, label="rectangular (np.repeat)")
n_h = np.arange(len(H))
a.plot((n_h - (len(H) - 1) / 2) / SPS, H / H.max(), color=COL["rrc"], lw=2, label="RRC")
a.axhline(0, color="k", lw=0.5)
a.set_title("Respuesta a UN chip (+1)")
a.set_xlabel("tiempo [chips]")
a.set_ylabel("amplitud (pico = 1)")
a.legend()
a.grid(alpha=0.3)
a.text(0.02, 0.05, "El RRC se extiende varios chips:\nes lo que angosta el espectro",
       transform=a.transAxes, fontsize=9, va="bottom")

# (0,1) forma de onda real del TX
a = ax[0, 1]
k0, k1 = 100, 124
tr = datos["rect"]["tx"]
tf = datos["rrc"]["tx"]
nr = np.arange(len(tr))
nf = np.arange(len(tf))
mr = (nr / SPS - 0.5 + 0.5 / SPS >= k0 - 0.5) & (nr / SPS - 0.5 + 0.5 / SPS <= k1 - 0.5)
tt_r = (nr - (SPS - 1) / 2) / SPS
tt_f = (nf - (len(H) - 1) / 2) / SPS
mr = (tt_r >= k0 - 0.5) & (tt_r < k1 - 0.5)
mf = (tt_f >= k0 - 0.5) & (tt_f < k1 - 0.5)
a.plot(tt_r[mr], tr[mr], color=COL["rect"], lw=1.6, drawstyle="steps-mid", label="rectangular")
a.plot(tt_f[mf], tf[mf], color=COL["rrc"], lw=1.6, label="RRC")
a.stem(np.arange(k0, k1), chips[k0:k1] * M["rect"]["pico"], linefmt="0.6", markerfmt=" ",
       basefmt=" ")
a.set_title("Senal que sale al SDR (24 chips, mismo pico)")
a.set_xlabel("chip n")
a.set_ylabel("amplitud (I)")
a.legend(loc="upper right")
a.grid(alpha=0.3)
a.text(0.02, 0.04, f"PAPR: rect {M['rect']['papr']:.1f} dB | RRC {M['rrc']['papr']:.1f} dB",
       transform=a.transAxes, fontsize=9)

# (0,2) espectro
a = ax[0, 2]
for k, etq in (("rect", "rectangular"), ("rrc", "RRC")):
    f, p = psd(datos[k]["tx"])
    a.plot(f, 10 * np.log10(p + 1e-18), color=COL[k], lw=1.4, label=etq)
a.axvline(M["rect"]["borde"], color="k", ls="--", lw=1)
a.axvline(-M["rect"]["borde"], color="k", ls="--", lw=1, label=f"+-{M['rect']['borde']:.0f} kHz = Rc(1+beta)/2")
a.axvline(RC / 1e3, color="gray", ls=":", lw=1)
a.axvline(-RC / 1e3, color="gray", ls=":", lw=1, label=f"+-{RC / 1e3:.0f} kHz = Rc")
a.set_xlim(-700, 700)
a.set_ylim(-90, -20)
a.set_title("Espectro (potencia total normalizada a 1)")
a.set_xlabel("frecuencia [kHz]")
a.set_ylabel("dB")
a.legend(fontsize=8, loc="upper right")
a.grid(alpha=0.3)

# (1,0) y (1,1) diagramas de ojo, mismo pico y mismo ruido
SIG_OJO = 0.08
ojo(ax[1, 0], datos["rect"]["tx"], False, COL["rect"], "Ojo RX rectangular (integrate & dump)",
    SIG_OJO, rng)
ojo(ax[1, 1], datos["rrc"]["tx"], True, COL["rrc"], "Ojo RX RRC (filtro adaptado)", SIG_OJO, rng)
ax[1, 0].set_ylabel(f"salida normalizada (ruido s={SIG_OJO}, mismo pico TX)")

# (1,2) tabla
a = ax[1, 2]
a.axis("off")
r, f_ = M["rect"], M["rrc"]
txt = (
    f"{'':34s}{'rect':>9s}{'RRC':>9s}\n"
    f"{'-' * 52}\n"
    f"{'Pico TX':34s}{r['pico']:9.2f}{f_['pico']:9.2f}\n"
    f"{'Potencia media (RMS)':34s}{r['rms']:9.3f}{f_['rms']:9.3f}\n"
    f"{'Pico / RMS (PAPR) [dB]':34s}{r['papr']:9.1f}{f_['papr']:9.1f}\n"
    f"{'Ancho de banda 99% [kHz] (*)':34s}{r['bw99']:9.0f}{f_['bw99']:9.0f}\n"
    f"{'Pot. fuera de +-%.0f kHz [dB]' % r['borde']:34s}{r['oob1']:9.1f}{f_['oob1']:9.1f}\n"
    f"{'Pot. fuera de +-%.0f kHz [dB]' % (RC / 1e3):34s}{r['oob2']:9.1f}{f_['oob2']:9.1f}\n"
    f"{'Potencia media relativa [dB]':34s}{0:9.1f}{20 * np.log10(f_['rms'] / r['rms']):9.1f}\n"
)
a.text(0.0, 0.95, txt, family="monospace", fontsize=10, va="top")
a.text(0.0, 0.40,
       "Lectura:\n"
       " - RRC: casi toda la potencia queda dentro de\n"
       "   Rc(1+beta); el rectangular 'ensucia' el espectro.\n"
       " - A igual pico el RRC transmite menos potencia media\n"
       "   (menos alcance si no se sube AMPLITUD_TX).\n"
       " - En el ojo, ambos abren en el instante de decision\n"
       "   (sin ISI); el RRC es mas sensible al ruido por su\n"
       "   menor potencia, no por ISI.\n\n"
       "(*) el del rectangular esta limitado por el muestreo (2 MHz);\n"
       "    en realidad sus lobulos decaen muy lento.",
       fontsize=9.5, va="top")
fig.tight_layout()
fig.savefig("comparacion_rrc_senal.png", dpi=130)
print("Guardado: comparacion_rrc_senal.png")
print("\n" + txt)

if args.rapido:
    if not args.no_show:
        plt.show()
    raise SystemExit

# =====================================================================
# 2) Curva de sensibilidad: % de paquetes recibidos vs ruido
#    Usa buscar_preambulo / analizar_trama / detectar_rafaga reales.
# =====================================================================
NEC = C.MARGEN_PREVIO_RX + C.SUAVIZADO_RAFAGA + D.N_MUESTRAS_UTILES + 2000
MAXI = C.MARGEN_PREVIO_RX + C.SUAVIZADO_RAFAGA + 500
FC = C.FREQ_CENTRAL


def canal(tx, sigma, seed, cfo):
    """Ruido previo + trama con deriva de reloj, CFO, fase aleatoria y ruido blanco."""
    rng = np.random.default_rng(seed)
    ini = int(rng.integers(8000, 20000))
    n_out = len(tx) + 60000
    pos = np.arange(n_out - ini) * (1 + cfo / FC)
    xi = np.arange(len(tx))
    y = np.interp(pos, xi, tx, right=0).astype(complex)
    buf = np.zeros(n_out, complex)
    buf[ini:] = y
    n = np.arange(n_out)
    buf *= np.exp(1j * (2 * np.pi * cfo * n / FS + rng.uniform(0, 2 * np.pi)))
    buf += sigma * (rng.standard_normal(n_out) + 1j * rng.standard_normal(n_out)) / np.sqrt(2)
    return buf, ini


def decodifica(d, buf, ini_real, sin_detector):
    ventana = buf - buf.mean()
    if sin_detector:
        ir = ini_real + 300            # la ventana arranca 200 muestras antes de la trama
    else:
        ir, _ = d.detectar_rafaga(ventana)
        if ir is None:
            return False
    ini = max(0, ir - C.MARGEN_PREVIO_RX)
    m = ventana[ini:ini + NEC]
    if len(m) < NEC:
        return False
    corr, inicio, f = d.buscar_preambulo(m, max_inicio=MAXI)
    if corr is None or corr < C.UMBRAL_CORRELACION:
        return False
    res = d.analizar_trama(m, inicio, f)
    return res is not None and verificar_crc(np.packbits(res["bits"]).tobytes()) == payload


SIG_DET = np.round(np.arange(0.2, 1.21, 0.1), 2)     # con detector de rafaga (RX real)
SIG_DEM = np.round(np.arange(0.8, 2.61, 0.2), 2)     # solo demodulacion (sin detector)
k_rms = M["rect"]["rms"] / M["rrc"]["rms"]
casos = {                                            # nombre -> (modo, factor de escala)
    "rect": (False, 1.0),
    "rrc": (True, 1.0),
    "rrc_rms": (True, k_rms),
}
etiquetas = {
    "rect": f"rectangular (pico {M['rect']['pico']:.2f})",
    "rrc": f"RRC, igual pico (pico {M['rrc']['pico']:.2f}, potencia {20 * np.log10(1 / k_rms):+.1f} dB)",
    "rrc_rms": f"RRC, igual potencia media (pico {M['rrc']['pico'] * k_rms:.2f}, no cabe en el DAC)",
}
N = args.pruebas
res = {c: {"det": np.zeros(len(SIG_DET)), "dem": np.zeros(len(SIG_DEM))} for c in casos}
seeds = [(int(s), float(np.random.default_rng(s).uniform(-40e3, 40e3)))
         for s in range(7000, 7000 + N)]

t0 = time.time()
total = len(casos) * (len(SIG_DET) + len(SIG_DEM)) * N
hecho = 0
for modo in (False, True):
    d = cargar_dsp(modo)
    for nombre, (m_, esc) in casos.items():
        if m_ != modo:
            continue
        tx = datos["rrc" if modo else "rect"]["tx"] * esc
        for clave, sigs, sin_det in (("det", SIG_DET, False), ("dem", SIG_DEM, True)):
            for i, sg in enumerate(sigs):
                ok = 0
                for seed, cfo in seeds:
                    buf, ini = canal(tx, sg, seed, cfo)
                    ok += decodifica(d, buf, ini, sin_det)
                    hecho += 1
                res[nombre][clave][i] = 100 * ok / N
            print(f"  [{hecho}/{total}] {nombre:8s} {clave}  ({time.time() - t0:.0f} s)", flush=True)


def umbral50(sigs, pct):
    """sigma donde la curva cruza 50% (interpolacion lineal)."""
    for i in range(1, len(sigs)):
        if pct[i - 1] >= 50 > pct[i]:
            return sigs[i - 1] + (sigs[i] - sigs[i - 1]) * (pct[i - 1] - 50) / (pct[i - 1] - pct[i])
    return None


fig2, ax2 = plt.subplots(1, 2, figsize=(15, 5.5))
fig2.suptitle(f"Paquetes recibidos con CRC valido vs ruido ({N} tramas por punto, CFO +-40 kHz, "
              "deriva de reloj)", fontsize=13)
for a, clave, sigs, titulo in (
        (ax2[0], "det", SIG_DET, "Sistema completo (con detector de rafaga, como RX.py)"),
        (ax2[1], "dem", SIG_DEM, "Solo demodulacion (inicio conocido, sin detector)")):
    for c in casos:
        a.plot(sigs, res[c][clave], "o-", color=COL[c], lw=2, label=etiquetas[c])
    a.axhline(50, color="gray", ls=":", lw=1)
    a.set_title(titulo)
    a.set_xlabel("sigma del ruido por muestra (misma escala de amplitud que el TX)")
    a.set_ylabel("% paquetes OK")
    a.set_ylim(-3, 103)
    a.grid(alpha=0.3)
a = ax2[0]
a.legend(fontsize=8.5, loc="lower left")
fig2.tight_layout()
fig2.savefig("comparacion_rrc_sensibilidad.png", dpi=130)
print("Guardado: comparacion_rrc_sensibilidad.png\n")

print("Umbral al 50% de paquetes (sigma de ruido) y diferencia respecto al rectangular:")
for clave, sigs, nom in (("det", SIG_DET, "sistema completo"), ("dem", SIG_DEM, "solo demodulacion")):
    u = {c: umbral50(sigs, res[c][clave]) for c in casos}
    print(f"  {nom}:")
    for c in casos:
        if u[c] is None:
            print(f"    {etiquetas[c]:75s} sin cruce en el rango")
        elif c == "rect" or u["rect"] is None:
            print(f"    {etiquetas[c]:75s} sigma50 = {u[c]:.2f}")
        else:
            print(f"    {etiquetas[c]:75s} sigma50 = {u[c]:.2f}  ({20 * np.log10(u[c] / u['rect']):+.1f} dB vs rect)")

if not args.no_show:
    plt.show()
