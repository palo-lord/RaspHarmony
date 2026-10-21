# ============================================================
# estado.py - Estado global da aplicação e navegação de menus
# ============================================================
import utime

from config import MODES, DURACAO_ACORDE_MS
from midi import ACORDES_LISTA

# A lista de acordes depende do módulo midi, então é montada aqui
MODES[4] = ACORDES_LISTA + ["Teclado"]


class Estado:
    def __init__(self):
        self.mode_ui = 0              # 0 = Menu principal
        self.mode_sel = 0
        self.instrumento = "Piano"
        self.oitava = 4               # 3..5 (muda com o botão do encoder)
        self.sel_nota = 0             # nota selecionada no Afinador (0 = C ... 11 = B)
        self.acorde_idx = 0           # acorde selecionado/tocando
        self.acorde_fim = utime.ticks_ms()
        self.notas_tocando = []       # números MIDI soando agora (para o display)
        self.player = None
        self.ultima_tecla = None

    def nota_midi(self, idx):
        return 12 * (self.oitava + 1) + idx

    def acorde_ativo(self):
        return utime.ticks_diff(self.acorde_fim, utime.ticks_ms()) > 0

    def nav_mode(self, mov_x, mov_y, clicou):
        """Navega nas listas com o joystick e executa a seleção com o botão dele."""
        itens = MODES[self.mode_ui]
        n = len(itens)

        if mov_y:
            self.mode_sel = (self.mode_sel + mov_y) % n
        # Na lista de acordes, o eixo X pula de raiz em raiz (4 itens)
        if self.mode_ui == 4 and mov_x and self.mode_sel < n - 1:
            self.mode_sel = (self.mode_sel + 4 * mov_x) % (n - 1)

        if not clicou:
            return

        escolhido = itens[self.mode_sel]

        if self.mode_ui == 4 and self.mode_sel < n - 1:   # acorde: toca por 1,5 s
            self.acorde_idx = self.mode_sel
            self.acorde_fim = utime.ticks_add(utime.ticks_ms(), DURACAO_ACORDE_MS)
            return
        if escolhido == "Piano" or escolhido == "Sintetizador":
            self.instrumento = escolhido
            return

        if escolhido == "Menu":
            self.mode_ui = 0
        elif escolhido == "Teclado":
            self.mode_ui = 1
        elif escolhido == "Player":
            self.mode_ui = 2
        elif escolhido == "Instrumento":
            self.mode_ui = 3
        elif escolhido == "Acordes":
            self.mode_ui = 4
        else:  # "Afinador"
            self.mode_ui = 5
        self.mode_sel = 1 if self.mode_ui == 3 and self.instrumento == "Sintetizador" else 0
