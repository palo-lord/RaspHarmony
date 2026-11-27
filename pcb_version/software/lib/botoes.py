# ============================================================
# botoes.py - Botões de navegação (Up, Down, Left, Right, Ok)
#
# Cada botão registra as bordas por interrupção (só guarda carimbos de tempo),
# então um aperto curto NÃO se perde mesmo quando o laço principal demora
# (no Player ele passa ~93 ms em cada bloco de áudio). Quem decide o que
# aconteceu é atualizar(), chamado uma vez por volta do laço.
#
# Eventos (valem só até a próxima chamada de atualizar()):
#   press : o botão foi apertado (dispara na hora, sem esperar soltar)
#   curto : foi apertado e solto em menos de NAV_LONGO_MS
#   longo : segurado além de NAV_LONGO_MS; repete a cada NAV_REPETE_MS
#   seg   : estado atual (True enquanto estiver apertado)
# ============================================================
from machine import Pin, disable_irq, enable_irq
import utime

import config as C


class BotaoNav:
    def __init__(self, num_pino, debounce_ms=C.NAV_DEBOUNCE_MS,
                 longo_ms=C.NAV_LONGO_MS, repete_ms=C.NAV_REPETE_MS):
        self.pino = Pin(num_pino, Pin.IN, Pin.PULL_UP)
        self.deb = debounce_ms
        self.longo_ms = longo_ms
        self.repete_ms = repete_ms
        # preenchidos na IRQ
        self._baixo = self.pino.value() == 0   # estado aceito pela IRQ
        self._t_ult = utime.ticks_ms()
        self._t_dn = 0
        self._t_up = 0
        self._ev_dn = False
        self._ev_up = False
        # preenchidos em atualizar()
        self.press = False
        self.curto = False
        self.longo = False
        self.seg = False
        self._t_press = 0
        self._t_rep = 0
        self._longo_ok = False
        self.pino.irq(trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING,
                      handler=self._irq, hard=True)

    def _irq(self, pino):
        t = utime.ticks_ms()
        if utime.ticks_diff(t, self._t_ult) < self.deb:
            return                              # repique
        baixo = pino.value() == 0
        if baixo == self._baixo:
            return
        self._baixo = baixo
        self._t_ult = t
        if baixo:
            self._t_dn = t
            self._ev_dn = True
        else:
            self._t_up = t
            self._ev_up = True

    def atualizar(self):
        self.press = False
        self.curto = False
        self.longo = False
        # Se a IRQ ignorou uma borda (repique ou toque mais curto que o debounce), o estado
        # aceito fica diferente do pino: ressincroniza assim que o debounce passar.
        if (self.pino.value() == 0) != self._baixo:
            self._irq(self.pino)
        st = disable_irq()
        dn = self._ev_dn
        up = self._ev_up
        t_dn = self._t_dn
        t_up = self._t_up
        self._ev_dn = False
        self._ev_up = False
        enable_irq(st)

        if dn:
            self.press = True
            self.seg = True
            self._t_press = t_dn
            self._longo_ok = False
        if up:
            if self.seg and not self._longo_ok \
                    and utime.ticks_diff(t_up, self._t_press) < self.longo_ms:
                self.curto = True
            self.seg = False
        elif self.seg:
            agora = utime.ticks_ms()
            if utime.ticks_diff(agora, self._t_press) >= self.longo_ms:
                if not self._longo_ok:
                    self._longo_ok = True
                    self.longo = True
                    self._t_rep = agora
                elif utime.ticks_diff(agora, self._t_rep) >= self.repete_ms:
                    self.longo = True
                    self._t_rep = agora


class Botoes:
    """Os cinco botões de navegação. Chame atualizar() uma vez por volta do laço."""

    def __init__(self):
        self.cima = BotaoNav(C.pin_Nav_U)
        self.baixo = BotaoNav(C.pin_Nav_D)
        self.esq = BotaoNav(C.pin_Nav_L)
        self.dir = BotaoNav(C.pin_Nav_R)
        self.ok = BotaoNav(C.pin_Nav_Ok)
        self._todos = (self.cima, self.baixo, self.esq, self.dir, self.ok)

    def atualizar(self):
        for b in self._todos:
            b.atualizar()

