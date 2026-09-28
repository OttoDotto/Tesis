import SoapySDR
from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_TX, SOAPY_SDR_CF32

def inicializar_sdr(modo, args, sample_rate, freq_central, ganancia, antena, canal=0):
    """
    Inicializa el dispositivo SDR y configura los parámetros base.
    """
    sdr = SoapySDR.Device(args)
    soapy_modo = SOAPY_SDR_TX if modo.upper() == 'TX' else SOAPY_SDR_RX
    
    sdr.setSampleRate(soapy_modo, canal, sample_rate)
    sdr.setFrequency(soapy_modo, canal, freq_central)
    
    # Corrección específica para HackRF en TX (evita saturar el AMP)
    if 'hackrf' in args.lower() and modo.upper() == 'TX':
        try:
            vga_gain = min(ganancia, 47)
            amp_gain = 14.0 if ganancia > 25 else 0.0
            sdr.setGain(soapy_modo, canal, 'VGA', vga_gain)
            sdr.setGain(soapy_modo, canal, 'AMP', amp_gain)
        except Exception:
            sdr.setGain(soapy_modo, canal, ganancia)
    else:
        sdr.setGain(soapy_modo, canal, ganancia)
        
    sdr.setAntenna(soapy_modo, canal, antena)
    
    stream = sdr.setupStream(soapy_modo, SOAPY_SDR_CF32)
    sdr.activateStream(stream)
    
    return sdr, stream

def cerrar_sdr(sdr, stream):
    """
    Desactiva y cierra el stream de datos de forma segura.
    """
    if sdr is not None and stream is not None:
        sdr.deactivateStream(stream)
        sdr.closeStream(stream)