import argparse
import numpy as np
import SoapySDR

from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_CF32

# ============================================================
# ARGUMENTOS DE TERMINAL
# ============================================================
parser = argparse.ArgumentParser(description="Receptor SDR Simple")
parser.add_argument("-d", "--driver", type=str, required=True, help="Driver del SDR (ej: hackrf, uhd)")
parser.add_argument("-a", "--antena", type=str, default=None, help="Puerto de antena (ej: AMP, TX/RX, RX2)")
args = parser.parse_args()

# ============================================================
# CONFIGURACIÓN
# ============================================================
FREQ_CENTRAL = 920e6
SAMPLE_RATE = 1e6
GANANCIA_RX = 30
CANAL = 0
CANTIDAD_MUESTRAS = 200000

# Lógica dinámica para la antena
if args.antena:
    ANTENA = args.antena  # Usa lo que el usuario pase por consola
elif args.driver == "uhd":
    ANTENA = "TX/RX"        # Puerto de recepción típico en USRP (puede ser TX/RX según cómo conectes el cable)
else:
    ANTENA = "AMP"        # Puerto usado en tu código original para HackRF

# ============================================================
# SDR
# ============================================================
print(f"Abriendo SDR RX ({args.driver})...")

# Usamos el argumento ingresado por consola
sdr = SoapySDR.Device(f"driver={args.driver}")

sdr.setSampleRate(SOAPY_SDR_RX, CANAL, SAMPLE_RATE)
sdr.setFrequency(SOAPY_SDR_RX, CANAL, FREQ_CENTRAL)
sdr.setGain(SOAPY_SDR_RX, CANAL, GANANCIA_RX)
sdr.setAntenna(SOAPY_SDR_RX, CANAL, ANTENA)

rx_stream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32, [CANAL])
sdr.activateStream(rx_stream)

print("\n" + "=" * 50)
print("RX SIMPLE")
print("=" * 50)
print(f"Driver        : {args.driver}")
print(f"Frecuencia RF : {FREQ_CENTRAL / 1e6:.3f} MHz")
print(f"Sample rate   : {SAMPLE_RATE / 1e6:.3f} Msps")
print(f"Ganancia      : {GANANCIA_RX} dB")
print("=" * 50 + "\n")

print("Esperando señal...\nCtrl+C para detener.\n")

# ============================================================
# RECEPCIÓN
# ============================================================
buffer_rx = np.empty(CANTIDAD_MUESTRAS, dtype=np.complex64)

try:
    while True:
        resultado = sdr.readStream(
            rx_stream,
            [buffer_rx],
            CANTIDAD_MUESTRAS,
            timeoutUs=1_000_000
        )

        if resultado.ret <= 0:
            print(f"Error RX: {resultado.ret}")
            continue

        muestras = buffer_rx[:resultado.ret]

        # ----------------------------------------------------
        # FFT
        # ----------------------------------------------------
        ventana = np.hanning(len(muestras))
        espectro = np.fft.fftshift(np.fft.fft(muestras * ventana))
        frecuencias = np.fft.fftshift(np.fft.fftfreq(len(muestras), 1 / SAMPLE_RATE))
        magnitud = np.abs(espectro)

        # ----------------------------------------------------
        # IGNORAR PICO DC (0 Hz)
        # ----------------------------------------------------
        centro = len(magnitud) // 2
        ancho_dc = 10  # Cantidad de bins a ignorar alrededor de 0 Hz
        
        # Hacemos cero la magnitud en el centro para que argmax no lo vea
        magnitud[centro - ancho_dc : centro + ancho_dc] = 0

        # Buscar pico (ahora buscará la señal real, ignorando el 0 Hz)
        indice_pico = np.argmax(magnitud)

        frecuencia_pico = frecuencias[indice_pico]
        
        # Buscar pico
        indice_pico = np.argmax(magnitud)
        frecuencia_pico = frecuencias[indice_pico]
        pico = magnitud[indice_pico]
        potencia = 20 * np.log10(pico + 1e-12)

        # ----------------------------------------------------
        # Mostrar resultado
        # ----------------------------------------------------
        print(f"Pico: {frecuencia_pico / 1e3:+.1f} kHz | Nivel: {potencia:.1f} dB")

except KeyboardInterrupt:
    print("\nRX detenido.")

# ============================================================
# CERRAR
# ============================================================
sdr.deactivateStream(rx_stream)
sdr.closeStream(rx_stream)
print("SDR RX cerrado.")