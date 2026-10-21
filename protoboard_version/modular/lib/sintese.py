# ============================================================
# sintese.py - Motor de síntese polifônico (tabela de onda + envelope)
# ============================================================
import math
import array
import gc
import micropython

from config import SAMPLE_RATE

TAM_TAB = 1024


def _tabela(harmonicos):
    """Tabela de 1024 amostras (int16) somando harmônicos [(n, amplitude), ...].
    Usa duas passadas para não criar listas temporárias de floats."""
    gc.collect()
    w = 2 * math.pi / TAM_TAB

    # Passada 1: só descobre o pico
    pico = 0.0
    for i in range(TAM_TAB):
        s = 0.0
        for h, a in harmonicos:
            s += a * math.sin(w * h * i)
        if abs(s) > pico:
            pico = abs(s)
    k = 30000 / pico

    # Passada 2: grava direto no array de 2 KB
    tab = array.array('h', bytes(2 * TAM_TAB))
    for i in range(TAM_TAB):
        s = 0.0
        for h, a in harmonicos:
            s += a * math.sin(w * h * i)
        tab[i] = int(s * k)
    return tab


tab_seno = _tabela([(1, 1.0)])
tab_piano = _tabela([(1, 1.0), (2, 0.55), (3, 0.30), (4, 0.18), (5, 0.10), (6, 0.05)])
tab_serra = _tabela([(h, 1.0 / h) for h in range(1, 11)])   # "serra" suave

# nome: (tabela, sustain/bloco, release/bloco, ataque (fração/bloco), nível Q12)
INSTR = {
    "Piano":        (tab_piano, 0.988, 0.55, 1.0, 2400),   # decai sozinho enquanto a tecla está apertada
    "Sintetizador": (tab_serra, 1.000, 0.72, 0.35, 1800),  # sustenta, ataque suave
    "Afinador":     (tab_seno,  1.000, 0.60, 0.50, 2400),  # senoide pura
}
GANHO_SINT = 2   # ganho extra do sintetizador em relação ao player


@micropython.viper
def mix_voz(acc, n: int, tab, fase: int, passo: int, a0: int, a1: int) -> int:
    """Soma n amostras de uma voz no acumulador int32 'acc'.
    fase: acumulador de 24 bits; amplitude em Q12 com rampa linear a0 -> a1."""
    pa = ptr32(acc)
    pt = ptr16(tab)
    amp = a0 << 8
    step = ((a1 - a0) << 8) // n
    for i in range(n):
        s = int(pt[fase >> 14])
        if s >= 32768:
            s -= 65536
        pa[i] = int(pa[i]) + ((s * (amp >> 8)) >> 12)
        amp += step
        fase = (fase + passo) & 0xFFFFFF
    return fase


@micropython.viper
def finalizar(acc, out, n: int, ganho: int):
    """Aplica volume, satura em 16 bits, grava em 'out' e zera o acumulador."""
    pa = ptr32(acc)
    po = ptr16(out)
    for i in range(n):
        v = (int(pa[i]) * ganho) >> 8
        if v > 32767:
            v = 32767
        elif v < -32768:
            v = -32768
        po[i] = v & 0xFFFF
        pa[i] = 0


class Sintese:
    """Gera um bloco de áudio mono 16 bits a partir da lista de notas MIDI ligadas."""

    def __init__(self, midi, bloco=256, taxa=SAMPLE_RATE):
        self.midi = midi
        self.n = bloco                      # 256 amostras = ~11,6 ms
        self.k = 16777216.0 / taxa          # 2^24 / taxa
        self.acc = array.array('i', [0] * bloco)
        self.out = bytearray(bloco * 2)
        self.vozes = {}   # midi -> [fase, amp, ligada, estava_ligada, alvo_env]

    def gerar(self, alvo, instr, ganho_volume):
        tab, sust, rel, atk, nivel = INSTR[instr]
        vozes = self.vozes
        for v in vozes.values():
            v[3] = v[2]
            v[2] = False
        for m in alvo:
            v = vozes.get(m)
            if v is None:
                vozes[m] = [0, 0.0, True, False, nivel]
            else:
                v[2] = True
        mortos = []
        for m in vozes:
            v = vozes[m]
            amp = v[1]
            if v[2]:
                if not v[3]:
                    v[4] = nivel          # novo ataque
                v[4] *= sust
                a1 = amp + (v[4] - amp) * atk
            else:
                a1 = amp * rel
                if a1 < 8:
                    mortos.append(m)
            passo = int(self.midi.freq_afinada(m) * self.k)
            v[0] = mix_voz(self.acc, self.n, tab, v[0], passo, int(amp), int(a1))
            v[1] = a1
        for m in mortos:
            del vozes[m]
        finalizar(self.acc, self.out, self.n, ganho_volume * GANHO_SINT)
        return self.out
