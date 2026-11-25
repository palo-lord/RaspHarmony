# ============================================================
# armazenamento.py - Cartão SD (SPI0 compartilhado): montagem e lista de WAVs
# ============================================================
from machine import Pin
import os
import sdcard


def montar_sd(spi, cs_pin, ponto_montagem, baud):
    """Monta o SD e retorna a lista de caminhos .wav.
    'spi' é o SPIVirtual do SD (ver spibus.py).
    Se o cartão não estiver presente, retorna lista vazia (o Teclado continua funcionando)."""
    cs = Pin(cs_pin, Pin.OUT)
    cs.value(1)  # Desativa o dispositivo inicialmente

    try:
        sd = sdcard.SDCard(spi, cs, baud)
        try:
            os.mount(sd, ponto_montagem)
        except OSError:
            pass  # já montado
        return [ponto_montagem + "/" + nome
                for nome in sorted(os.listdir(ponto_montagem))
                if nome.lower().endswith(".wav")]
    except Exception as e:
        print("SD indisponivel:", e)
        return []
