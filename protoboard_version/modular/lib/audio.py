# ============================================================
# audio.py - Saída de áudio I2S (MAX98357A) e volume por software
# ============================================================
from machine import Pin, I2S
import micropython

from config import SCK_PIN, WS_PIN, SD_PIN, IBUF_PLAYER, VOL_PASSO, VOLUME_INICIAL

SILENCIO = bytearray(512)
GANHO_UNIT = 4096

def calcula_ganho(vol):
    """Percentual -> ganho em ponto fixo (256 = 1.0). Curva quadrática."""
    g = vol * vol * GANHO_UNIT // 10000
    if vol > 0 and g < 1:
        g = 1
    return g

@micropython.viper
def aplicar_volume(buf, n: int, ganho: int):
    """Multiplica in-place n bytes de amostras PCM 16 bits (little-endian)."""
    p = ptr16(buf)
    for i in range(n >> 1):
        s = int(p[i])
        if s >= 32768:       # amostra com sinal
            s -= 65536
        p[i] = ((s * ganho) >> 12) & 0xFFFF


class SaidaAudio:
    """Gerencia o I2S e o volume (o MAX98357A não tem controle de volume por I2S)."""

    def __init__(self):
        self.i2s = None
        self._cfg = None
        self.volume = VOLUME_INICIAL          # 0..100 (%)
        self.ganho = calcula_ganho(self.volume)
        self.mudo = False
        
    def _atualiza_ganho(self):
        self.ganho = 0 if self.mudo else calcula_ganho(self.volume)

    def alternar_mudo(self):
        self.mudo = not self.mudo
        self._atualiza_ganho()

    def desmutar(self):
        self.mudo = False
        self._atualiza_ganho()

    def abrir(self, taxa, canais, ibuf):
        """(Re)cria o I2S só se a configuração mudou."""
        cfg = (taxa, canais, ibuf)
        if cfg == self._cfg:
            return
        if self.i2s is not None:
            self.i2s.deinit()
        self.i2s = I2S(0,
            sck=Pin(SCK_PIN),
            ws=Pin(WS_PIN),
            sd=Pin(SD_PIN),
            mode=I2S.TX,
            rate=taxa,
            bits=16,
            format=I2S.STEREO if canais == 2 else I2S.MONO,
            ibuf=ibuf)
        self._cfg = cfg

    def ajustar_volume(self, delta):
        if delta:
            self.volume = max(0, min(100, self.volume + delta * VOL_PASSO))            
            self.mudo = False
            
            self._atualiza_ganho()

    def escrever(self, dados):
        self.i2s.write(dados)

    def saida_wav(self, dados, n, wav):
        """Callback do Player: envia PCM do WAV ao amplificador, com volume.
        Reconfigura o I2S automaticamente se taxa/canais do WAV forem diferentes."""
        if (wav.taxa, wav.canais, IBUF_PLAYER) != self._cfg:
            self.abrir(wav.taxa, wav.canais, IBUF_PLAYER)
        if self.ganho != GANHO_UNIT:
            aplicar_volume(dados, n, self.ganho)
        self.i2s.write(dados)

