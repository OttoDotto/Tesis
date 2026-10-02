import SoapySDR
from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_TX, SOAPY_SDR_CF32

def inicializar_sdr(modo, args, sample_rate, freq_central, ganancia, antena, canal=0):
    sdr = SoapySDR.Device(args)
    soapy_modo = SOAPY_SDR_TX if modo.upper() == 'TX' else SOAPY_SDR_RX
    
    sdr.setSampleRate(soapy_modo, canal, sample_rate)
    sdr.setFrequency(soapy_modo, canal, freq_central)
    sdr.setAntenna(soapy_modo, canal, antena)
    
    # Configuracion especifica de ganancia para HackRF TX
    if 'hackrf' in args.lower() and modo.upper() == 'TX':
        try:
            sdr.setGain(soapy_modo, canal, 'TXVGA', min(ganancia, 47))
            if ganancia > 25:
                sdr.setGain(soapy_modo, canal, 'AMP', 14.0) # Activa amplificador de 14dB
            else:
                sdr.setGain(soapy_modo, canal, 'AMP', 0.0)
        except RuntimeError:
            sdr.setGain(soapy_modo, canal, ganancia) # Fallback general
    else:
        sdr.setGain(soapy_modo, canal, ganancia)
    
    stream = sdr.setupStream(soapy_modo, SOAPY_SDR_CF32)
    sdr.activateStream(stream)
    
    return sdr, stream

def cerrar_sdr(sdr, stream):
    """
    Desactiva y cierra el stream de datos correctamente de forma segura.
    """
    if sdr is not None and stream is not None:
        sdr.deactivateStream(stream)
        sdr.closeStream(stream)