# ============================================================
# toque.py - Teclado de toque capacitivo DIY (16 pads no MCP23017)
#
# Princípio (tempo de carga): cada pad tem um resistor de 1 MΩ para 3V3 e está
# ligado a um GPIO do MCP23017.
#   1. Os 16 GPIOs viram SAÍDA em nível baixo -> todos os pads descarregam.
#   2. Os 16 GPIOs viram ENTRADA ao mesmo tempo (uma escrita I2C de 2 bytes) ->
#      cada pad carrega pelo resistor, com constante de tempo R x C.
#   3. Lê-se o GPIO (2 bytes, uma transação) várias vezes, carimbando o tempo de
#      cada leitura. O primeiro carimbo em que o pad aparece em nível alto é o
#      "tempo de carga" dele.
# O dedo soma capacitância ao pad -> carga mais lenta -> tempo maior que a linha
# de base (medida na calibração e acompanhada devagar para absorver deriva).
#
# Limite físico: a resolução é o tempo de uma leitura I2C (~100 µs a 400 kHz).
# Para compensar, cada varredura faz TOQUE_AMOSTRAS ciclos com atrasos
# diferentes (dither) e tira a média. Ajuste os TOQUE_* do config.py com o
# script teste_toque.py.
#
# Só varra este teclado no modo Instrumento: cada varredura ocupa o I2C.
# ============================================================
from array import array
import utime

import config as C

_IODIR = 0x00    # IODIRA (IODIRB = 0x01); BANK=0 e SEQOP=0 -> escrita sequencial A,B
_GPIO = 0x12     # GPIOA  (GPIOB = 0x13)
_OLAT = 0x14     # OLATA  (OLATB = 0x15)


class TecladoToque:
    def __init__(self, mcp, pullup=C.TOQUE_PULLUP, amostras=C.TOQUE_AMOSTRAS,
                 dither_us=C.TOQUE_DITHER_US, leituras=C.TOQUE_LEITURAS,
                 limiar_us=C.TOQUE_LIMIAR_US, t_max_us=C.TOQUE_T_MAX_US):
        # 'mcp' é um MCP23017 já inicializado (todos os pinos como entrada, IOCON = 0).
        # Só usamos o I2C e o endereço dele: o acesso rápido é direto nos registradores.
        self.i2c = mcp._i2c
        self.addr = mcp._address
        self.n = C.N_TECLAS
        self.amostras = amostras
        self.dither = dither_us
        self.leituras = leituras
        self.limiar = limiar_us
        self.t_max = t_max_us
        # nível de descarga: 0 V se o resistor puxa para 3V3; 3V3 se puxa para GND
        nivel = 0x00 if pullup else 0xFF
        self.inv = 0x0000 if pullup else 0xFFFF
        self._saida = bytes((0x00, 0x00))
        self._entrada = bytes((0xFF, 0xFF))
        self._buf = bytearray(2)
        self.t = array('i', [0] * self.n)       # tempo de carga medido (µs, média)
        self.base = array('i', [0] * self.n)    # linha de base (µs)
        self.tocado = 0                         # máscara das teclas tocadas (bit i = tecla i)
        self._ant = 0
        # latch de saída = nível de descarga (só entra em ação quando o pino vira saída)
        self.i2c.writeto_mem(self.addr, _OLAT, bytes((nivel, nivel)))
        self.i2c.writeto_mem(self.addr, _IODIR, self._entrada)
        self.calibrar()

    def _ciclo(self, atraso_us, acum):
        """Um ciclo descarga -> carga -> leituras. Soma os tempos em 'acum'."""
        i2c = self.i2c
        addr = self.addr
        buf = self._buf
        i2c.writeto_mem(addr, _IODIR, self._saida)      # descarrega
        i2c.writeto_mem(addr, _IODIR, self._entrada)    # libera: começa a carregar
        t0 = utime.ticks_us()
        if atraso_us:
            utime.sleep_us(atraso_us)
        pend = 0xFFFF
        inv = self.inv
        for _ in range(self.leituras):
            i2c.readfrom_mem_into(addr, _GPIO, buf)
            t = utime.ticks_diff(utime.ticks_us(), t0)
            novos = ((buf[0] | (buf[1] << 8)) ^ inv) & pend
            if novos:
                for i in range(self.n):
                    if (novos >> i) & 1:
                        acum[i] += t
                pend &= ~novos
                if not pend:
                    return
        if pend:
            tm = self.t_max
            for i in range(self.n):
                if (pend >> i) & 1:
                    acum[i] += tm

    def medir(self):
        """Mede o tempo de carga de cada pad (média de 'amostras' ciclos) em self.t."""
        acum = [0] * self.n
        for k in range(self.amostras):
            self._ciclo(k * self.dither, acum)
        a = self.amostras
        t = self.t
        for i in range(self.n):
            t[i] = acum[i] // a

    def calibrar(self, ciclos=8):
        """Define a linha de base com os pads livres. Não encoste nas teclas."""
        soma = [0] * self.n
        for _ in range(ciclos):
            self.medir()
            for i in range(self.n):
                soma[i] += self.t[i]
        for i in range(self.n):
            self.base[i] = soma[i] // ciclos
        self.tocado = 0
        self._ant = 0

    def varrer(self):
        """Faz uma varredura e retorna a máscara das teclas tocadas (bit i = tecla i)."""
        try:
            self.medir()
        except OSError:                 # MCP não respondeu: considera tudo solto
            self.tocado = 0
            self._ant = 0
            return 0
        t = self.t
        base = self.base
        lim = self.limiar
        cand = 0
        for i in range(self.n):
            if t[i] - base[i] > lim:
                cand |= 1 << i
            else:
                base[i] += (t[i] - base[i]) >> 3      # acompanha a deriva devagar
        # debounce: só muda depois de duas varreduras seguidas concordando
        ant = self._ant
        self.tocado = (cand & ant) | (self.tocado & (cand | ant))
        self._ant = cand
        return self.tocado

    @staticmethod
    def teclas(mascara):
        """Máscara -> lista de índices de teclas (0..15), em ordem."""
        return [i for i in range(16) if (mascara >> i) & 1]
