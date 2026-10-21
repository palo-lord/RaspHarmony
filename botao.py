# ============================================================
# botao.py - Botão com detecção de borda e debounce sem sleep
# ============================================================
import utime


class Botao:
    """Botão com detecção de borda (um único evento por aperto) e debounce
    por tempo, SEM sleep: não trava o áudio."""

    def __init__(self, pino, debounce_ms=250):
        self.pino = pino
        self.deb = debounce_ms
        self.ant = pino.value()
        self.t = utime.ticks_ms()

    def pressionado(self):
        v = self.pino.value()
        agora = utime.ticks_ms()
        evento = False
        if v == 0 and self.ant == 1 and utime.ticks_diff(agora, self.t) > self.deb:
            evento = True
            self.t = agora
        self.ant = v
        return evento
