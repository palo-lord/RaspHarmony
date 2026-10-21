# ============================================================
# player.py - Reprodutor de faixas WAV
# ============================================================
import utime

from config import PARADO, TOCANDO, PAUSADO, TAM_BUFFER
from wavfile import WavFile

PULO_VEL_MAX_S = 15           # s de áudio por s real, com o joystick no fundo de escala
PULO_GAP_MAX_MS = 300         # pausa maior que isso = novo gesto
PULO_PASSO_INICIAL_MS = 50    # intervalo assumido na 1ª chamada de um gesto


class Player:
    def __init__(self, arquivos, callback, repetir=True):
        self.arquivos = arquivos
        self.callback = callback
        self.repetir = repetir
        self.indice = 0
        self.wav = None
        self.estado = PARADO
        self.buf = bytearray(TAM_BUFFER)
        self.mv = memoryview(self.buf)
        self._t_pulo = utime.ticks_ms()

    def selecionar(self, i):
        """Troca para a faixa i (0..N-1), mesmo no meio da leitura atual."""
        if not 0 <= i < len(self.arquivos):
            return False
        self._fechar_atual()
        try:
            self.wav = WavFile(self.arquivos[i])
        except (OSError, ValueError):
            self.estado = PARADO
            return False
        if self.wav.bits != 16 or self.wav.canais not in (1, 2):
            self._fechar_atual()          # só 16 bits, mono ou estéreo
            self.estado = PARADO
            return False
        self.indice = i
        self.estado = TOCANDO
        return True

    def proximo(self):
        if not self.arquivos:
            return False
        return self.selecionar((self.indice + 1) % len(self.arquivos))

    def anterior(self):
        if not self.arquivos:
            return False
        return self.selecionar((self.indice - 1) % len(self.arquivos))

    def pausar_retomar(self):
        if self.estado == TOCANDO:
            self.estado = PAUSADO
        elif self.estado == PAUSADO:
            self.estado = TOCANDO
        elif self.estado == PARADO:
            self.selecionar(self.indice)

    def reiniciar(self):
        if self.wav:
            self.wav.reiniciar()
            self.estado = TOCANDO

    def pular(self, x, vel_max_s=PULO_VEL_MAX_S, fundo_escala=32768):
        """Avança (x > 0) ou retrocede (x < 0) a faixa atual, proporcional ao desvio."""
        if self.wav is None or self.estado == PARADO:
            return 0.0

        agora = utime.ticks_ms()
        dt_ms = utime.ticks_diff(agora, self._t_pulo)
        self._t_pulo = agora
        if dt_ms > PULO_GAP_MAX_MS:
            dt_ms = PULO_PASSO_INICIAL_MS

        frac = x / fundo_escala
        if frac > 1.0:
            frac = 1.0
        elif frac < -1.0:
            frac = -1.0

        delta = frac * vel_max_s * (dt_ms / 1000)
        self.wav.buscar(delta)
        return delta

    def parar(self):
        self._fechar_atual()
        self.estado = PARADO

    def _fechar_atual(self):
        if self.wav:
            try:
                self.wav.fechar()
            except OSError:
                pass
            self.wav = None

    def atualizar(self):
        """Lê UM bloco da faixa atual. Chame em loop."""
        if self.estado != TOCANDO or self.wav is None:
            return

        n = self.wav.ler_bloco(self.buf)
        if n:
            self.callback(self.mv[:n], n, self.wav)
            return

        # Fim da faixa
        ultima = self.indice == len(self.arquivos) - 1
        if ultima and not self.repetir:
            self.parar()
        else:
            self.proximo()
