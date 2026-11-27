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
# O SD é o estado de repouso: o OLED só ocupa o barramento durante o envio do quadro
# (show/show_parcial/write_cmd) e devolve o SPI0 ao SD logo em seguida. Assim, qualquer
# leitura do SD (Player) encontra o barramento já configurado para ele.
#
# Observações:
#  - O MISO (GP0) fica sempre ligado ao SPI0 (o OLED não usa MISO; é só uma entrada).
#    Ele é passado em toda reconfiguração para o SPI nunca cair no pino MISO padrão
#    (GP4 = CS do SD).
#  - A reconfiguração usa o construtor SPI(id, ...): em várias versões do MicroPython
#    (rp2) SPI.init() não aceita sck/mosi/miso.
#  - Nenhuma IRQ usa o SPI, e o laço é de uma thread só, então não há acesso concorrente.
# ============================================================
from machine import Pin, SPI
from ssd1309 import SSD1309_SPI


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
        self._aplicar(d)
        self.atual = d

    def _aplicar(self, d):
        # Chamar SPI(id, ...) de novo reconfigura o mesmo periférico (singleton por id)
        # com os novos pinos.
        self.spi = SPI(self.id, baudrate=d.baud, polarity=0, phase=0,
                       sck=d.sck, mosi=d.mosi, miso=self.miso)

    def repousar(self):
        """Devolve o SPI0 ao SD."""
        if self.repouso is not None:
            self.selecionar(self.repouso)


class SPIVirtual:
    """Faz o papel de um objeto SPI para o driver (sdcard.py / ssd1309.py).
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
            b._aplicar(self)
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


class SSD1309_SPI0(SSD1309_SPI):
    """SSD1309 em SPI compartilhado. Pega o barramento antes de baixar o CS e devolve ao
    SD no fim. show() ocupa o barramento uma vez só para os comandos + o quadro inteiro.

    O SSD1309 não tem controle de "páginas sujas" como o SH1106 do projeto antigo; para
    manter a interface (ui.py e app.py chamam show_parcial), a tela é marcada como suja
    em fill() (todo desenhar() começa com fill(0)) e show_parcial() só envia se houver
    algo novo. Um quadro inteiro (1024 bytes a 8 MHz) leva ~1 ms."""

    def __init__(self, width, height, spi, dc, rst, cs, bus, rotate=0):
        self._bus = bus
        self._lote = False
        self._sujo = False
        super().__init__(width, height, spi, dc, rst, cs)
        if rotate == 180:
            # gira 180°: inverte o mapeamento de segmentos e a direção de varredura
            self.write_cmd(0xA0)        # SEG remap normal  (padrão do driver: 0xA1)
            self.write_cmd(0xC0)        # COM scan normal   (padrão do driver: 0xC8)
        self.fill(0)                    # a GDDRAM do SSD1309 liga com lixo: limpa
        self.show()

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

    def fill(self, color):
        super().fill(color)
        self._sujo = True

    def show(self):
        self._bus.selecionar(self.spi)
        self._lote = True
        try:
            super().show()
        finally:
            self._lote = False
            self._bus.repousar()
        self._sujo = False

    def show_parcial(self, max_paginas=1):
        """Compatível com a interface antiga: envia o quadro se houver algo novo.
        Retorna False (nunca sobram páginas pendentes)."""
        if self._sujo:
            self.show()
        return False

