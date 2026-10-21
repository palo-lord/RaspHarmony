# ============================================================
# encoder.py - Encoder rotativo em quadratura
# ============================================================
from machine import Pin, disable_irq, enable_irq

# Tabela de decodificação em quadratura.
# Índice = (estado_anterior << 2) | estado_novo, com estado = (A << 1) | B.
_TAB_ENC = (0, 1, -1, 0,
            -1, 0, 0, 1,
            1, 0, 0, -1,
            0, -1, 1, 0)


class Encoder:
    """Encoder rotativo em quadratura. A interrupção só acumula passos;
    o resto do programa lê com cliques(), sem nunca mexer em SD/I2S/OLED na IRQ."""

    def __init__(self, pino_a, pino_b, passos_por_clique=4):
        self.a = pino_a
        self.b = pino_b
        self.ppc = passos_por_clique      # 4 para a maioria (KY-040); 2 ou 1 em outros
        self.estado = (self.a.value() << 1) | self.b.value()
        self.contagem = 0
        gatilho = Pin.IRQ_RISING | Pin.IRQ_FALLING
        self.a.irq(trigger=gatilho, handler=self._irq, hard=True)
        self.b.irq(trigger=gatilho, handler=self._irq, hard=True)

    def _irq(self, pino):
        novo = (self.a.value() << 1) | self.b.value()
        self.contagem += _TAB_ENC[(self.estado << 2) | novo]
        self.estado = novo

    def cliques(self):
        """Retorna os 'cliques' (detents) desde a última chamada:
        positivo = horário, negativo = anti-horário. Troque o sinal se o
        seu encoder estiver ligado ao contrário."""
        st = disable_irq()
        c = self.contagem
        n = c // self.ppc if c >= 0 else -((-c) // self.ppc)
        self.contagem = c - n * self.ppc   # guarda o resto de um clique incompleto
        enable_irq(st)
        return n
