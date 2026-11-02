import hashlib
import numpy as np

# ---------- 1. Clave de texto -> m-sequence ----------
# Taps verificados: los 6 polinomios primitivos de grado 6 para este LFSR
POLINOMIOS = [(1,2),(1,6),(1,2,3,6),(1,2,4,5),(1,2,5,6),(1,3,4,6)]
GRADO, N = 6, 63

def lfsr(taps, estado0):
    st = [(estado0 >> i) & 1 for i in range(GRADO)]
    out = np.zeros(N, dtype=np.uint8)
    for n in range(N):
        out[n] = st[0]
        fb = 0
        for t in taps:
            fb ^= st[t-1]
        st = st[1:] + [fb]
    return out

def derivar_clave(texto, id_red="UGV-NET"):
    # PBKDF2: encarece la fuerza bruta sobre contraseñas de texto
    k = hashlib.pbkdf2_hmac("sha256", texto.encode(), id_red.encode(), 100_000)
    poli = int.from_bytes(k[:4], "big") % len(POLINOMIOS)
    fase = int.from_bytes(k[4:8], "big") % N + 1      # nunca 0
    bits = lfsr(POLINOMIOS[poli], fase)
    return bits, 2.0*bits - 1.0, (poli, fase)

def golomb(bits, bip):
    ac = np.array([np.sum(bip*np.roll(bip,-k)) for k in range(N)])
    return abs(int(bits.sum()) - int((1-bits).sum())) == 1 and np.all(ac[1:] == -1)

# ---------- 2. Trama: preámbulo + datos ----------
PREAMBULO = np.array([1,0,1,0,1,1,0,0], dtype=int)   # conocido por la red

def texto_a_bits(msg):
    return np.unpackbits(np.frombuffer(msg.encode(), np.uint8)).astype(int)

def bits_a_texto(b):
    b = np.array(b[:len(b)//8*8], dtype=np.uint8)
    return bytes(np.packbits(b)).decode(errors="replace")

def ensanchar(bits, pn):
    return np.repeat(2*bits-1, len(pn)) * np.tile(pn, len(bits))

def desensanchar(rx, pn):
    nb = len(rx)//len(pn)
    c = rx[:nb*len(pn)].reshape(nb, len(pn)) @ pn
    return (c > 0).astype(int), c

# ---------- 3. Control de acceso ----------
def intentar_acceso(rx, pn, umbral=0.6):
    bits, corr = desensanchar(rx, pn)
    pre = bits[:len(PREAMBULO)]
    energia = np.mean(np.abs(corr[:len(PREAMBULO)])) / len(pn)  # 1.0 = perfecta
    ok = np.array_equal(pre, PREAMBULO) and energia > umbral
    return ok, bits[len(PREAMBULO):], energia

# ---------- 4. Prueba ----------
if __name__ == "__main__":
    rng = np.random.default_rng(1)
    claves = {"clave1": "12345678", "clave2": "87654321", "clave3": "RED_SECRETA_UGV"}
    pn = {}
    for nombre, c in claves.items():
        b, bip, par = derivar_clave(c)
        pn[nombre] = bip
        print(f"{nombre:8s} clave='{c}' -> poli={par[0]} fase={par[1]:2d}  Golomb OK: {golomb(b,bip)}")

    msg = "Hola UGV"
    tx = ensanchar(np.concatenate([PREAMBULO, texto_a_bits(msg)]), pn["clave2"])
    rx = tx + rng.normal(0, 2.0, tx.size)     # AWGN con ruido mayor que la señal por chip

    for nombre in claves:
        ok, datos, e = intentar_acceso(rx, pn[nombre])
        print(f"{nombre:8s} acceso={ok!s:5}  corr={e:.2f}  datos='{bits_a_texto(datos) if ok else '---'}'")