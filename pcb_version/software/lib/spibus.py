# ============================================================
# spibus.py - SPI0 de hardware compartilhado entre o cartão SD e o display OLED
#
# O SD (GP2/GP3/GP0) e o OLED (GP18/GP19) usam o MESMO periférico SPI0, só que em
# pinos diferentes. Dois objetos SPI(0, ...) não podem coexistir: cada um reconfigura o
# periférico, e os pinos do dispositivo que NÃO está em uso continuariam ligados à função
# SPI (clock duplicado nos dois pares de pinos = "picote").
#
# Solução: um único SPI(0) e um "seletor". Antes de falar com um dispositivo, o seletor:
#   1. devolve SCK/MOSI do dispositivo anterior para GPIO (SCK = 0, MOSI = nível ocioso);
#   2. reconfigura o SPI0 com os pinos e a velocidade do novo dispositivo.
# O SD é o estado de repouso: o OLED só ocupa o barramento durante o envio de páginas
# (show/show_parcial/write_cmd) e devolve o SPI0 ao SD logo em seguida. Assim, qualquer
# leitura do SD (Player) encontra o barramento já configurado para ele.
#
# Observações:
#  - O MISO (GP0) fica sempre ligado ao SPI0 (o OLED não usa MISO; é só uma entrada).
#    Ele é passado em todo init() para o SPI nunca cair no pino MISO padrão (GP4 = CS do SD).
#  - Nenhuma IRQ usa o SPI, e o laço é de uma thread só, então não há acesso concorrente.
# ============================================================
from machine import Pin, SPI
from sh1106 import SH1106_SPI


class BarramentoSPI0:
    def __init__(self, spi_id, miso):
        self.id = spi_id
        self.miso = Pin(miso)
        self.spi = None
        self.atual = None       # dispositivo (SPIVirtual) com o barramento agora
        self.repouso = None     # dispositivo para onde voltar (o SD)

    def dispositivo(self, sck, mosi, baud, mosi_ocioso=0):
        return SPIVirtual(self, sck, mosi, baud, mosi_ocioso)

    def selecionar(self, d):
        if d is self.atual:
            return
        if self.atual is not None:
            self.atual._soltar()
        if self.spi is None:
            self.spi = SPI(self.id, baudrate=d.baud, polarity=0, phase=0,
                           sck=d.sck, mosi=d.mosi, miso=self.miso)
        else:
            self.spi.init(baudrate=d.baud, polarity=0, phase=0,
                          sck=d.sck, mosi=d.mosi, miso=self.miso)
        self.atual = d

    def repousar(self):
        """Devolve o SPI0 ao SD."""
        if self.repouso is not None:
            self.selecionar(self.repouso)


class SPIVirtual:
    """Faz o papel de um objeto SPI para o driver (sdcard.py / sh1106.py).
    Toda operação garante que o SPI0 está configurado para este dispositivo."""

    def __init__(self, bus, sck, mosi, baud, mosi_ocioso):
        self.bus = bus
        self.sck = Pin(sck)
        self.mosi = Pin(mosi)
        self.baud = baud
        self.mosi_ocioso = mosi_ocioso

    def _soltar(self):
        self.sck.init(Pin.OUT, value=0)
        self.mosi.init(Pin.OUT, value=self.mosi_ocioso)

    def init(self, baudrate=None, **kw):
        """O sdcard.py chama init(baudrate=...) (100 kHz na partida, depois a velocidade
        final). Polaridade/fase são sempre 0 (modo 0), usados por SD e OLED."""
        if baudrate:
            self.baud = baudrate
        b = self.bus
        if b.atual is self:
            b.spi.init(baudrate=self.baud, polarity=0, phase=0,
                       sck=self.sck, mosi=self.mosi, miso=b.miso)
        else:
            b.selecionar(self)

    def write(self, *a):
        b = self.bus
        if b.atual is not self:
            b.selecionar(self)
        return b.spi.write(*a)

    def read(self, *a):
        b = self.bus
        if b.atual is not self:
            b.selecionar(self)
        return b.spi.read(*a)

    def readinto(self, *a):
        b = self.bus
        if b.atual is not self:
            b.selecionar(self)
        return b.spi.readinto(*a)

    def write_readinto(self, *a):
        b = self.bus
        if b.atual is not self:
            b.selecionar(self)
        return b.spi.write_readinto(*a)


class SH1106_SPI0(SH1106_SPI):
    """SH1106 em SPI compartilhado. Pega o barramento antes de baixar o CS e devolve ao
    SD no fim. show()/show_parcial() ocupam o barramento uma vez só para todas as páginas."""

    def __init__(self, width, height, spi, dc, res, cs, bus, rotate=0):
        self._bus = bus
        self._lote = False
        super().__init__(width, height, spi, dc, res, cs, rotate=rotate)

    def write_cmd(self, cmd):
        if self._lote:
            super().write_cmd(cmd)
            return
        self._bus.selecionar(self.spi)
        super().write_cmd(cmd)
        self._bus.repousar()

    def write_data(self, buf):
        if self._lote:
            super().write_data(buf)
            return
        self._bus.selecionar(self.spi)
        super().write_data(buf)
        self._bus.repousar()

    def show(self, full_update=False):
        self._bus.selecionar(self.spi)
        self._lote = True
        try:
            super().show(full_update)
        finally:
            self._lote = False
            self._bus.repousar()

    def show_parcial(self, max_paginas=1):
        if not self.pages_to_update:
            return False                    # nada a enviar: não mexe no barramento
        self._bus.selecionar(self.spi)
        self._lote = True
        try:
            return super().show_parcial(max_paginas)
        finally:
            self._lote = False
            self._bus.repousar()
