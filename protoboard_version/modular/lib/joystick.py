# ============================================================
# joystick.py - Joystick analógico com botão
# ============================================================
from machine import Pin, ADC
import utime

from botao import Botao


class Joystick:
    def __init__(self, pin_x, pin_y, pin_sw, limiar=12000,
                 inverte_x=True, inverte_y=True):
        self.sw = Pin(pin_sw, Pin.IN, Pin.PULL_UP)
        self.adc_x = ADC(Pin(pin_x))
        self.adc_y = ADC(Pin(pin_y))
        self.botao = Botao(self.sw)
        self.limiar = limiar
        self.inverte_x = inverte_x
        self.inverte_y = inverte_y
        self.neutra_x = True
        self.neutra_y = True

        utime.sleep_ms(100)  # calibração do centro do joystick
        self.centro_x = self.adc_x.read_u16()
        self.centro_y = self.adc_y.read_u16()

    def ler(self):
        """Retorna (x, movimento_x, movimento_y).
        x = desvio analógico em X (para o 'pular' do Player);
        movimento_x/y = -1, 0 ou +1, UM evento por empurrão (com histerese)."""
        x = self.centro_x - self.adc_x.read_u16()
        y = self.centro_y - self.adc_y.read_u16()
        if self.inverte_x:
            x = -x
        if self.inverte_y:
            y = -y

        lim = self.limiar
        movimento_x = 0
        movimento_y = 0

        if self.neutra_x:
            if x > lim:
                movimento_x = 1
                self.neutra_x = False
            elif x < -lim:
                movimento_x = -1
                self.neutra_x = False
        elif abs(x) < lim // 3:
            self.neutra_x = True

        if self.neutra_y:
            if y > lim:
                movimento_y = 1
                self.neutra_y = False
            elif y < -lim:
                movimento_y = -1
                self.neutra_y = False
        elif abs(y) < lim // 3:
            self.neutra_y = True

        return (x, movimento_x, movimento_y)

    def clicou(self):
        return self.botao.pressionado()
