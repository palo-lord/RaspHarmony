# ============================================================
# armazenamento.py - Cartão SD (SPI): montagem e lista de WAVs
# ============================================================
from machine import Pin, SPI
import os
import sdcard


def montar_sd(sck, mosi, miso, cs_pin, ponto_montagem):
    """Monta o SD e retorna a lista de caminhos .wav.
    Se o cartão não estiver presente, retorna lista vazia (o Teclado continua funcionando)."""
    spi = SPI(0, baudrate=8000000, polarity=0, phase=0,
              sck=Pin(sck), mosi=Pin(mosi), miso=Pin(miso))
    cs = Pin(cs_pin, Pin.OUT)
    cs.value(1)  # Desativa o dispositivo inicialmente

    try:
        sd = sdcard.SDCard(spi, cs)
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
