# ============================================================
# sintese.py - Motor de síntese polifônico (tabela de onda + envelope)
# ============================================================
import math
import array
import gc
import random
import micropython

from config import SAMPLE_RATE

TAM_TAB = 1024


def _tabela(harmonicos, alvo_rms=None):
    """Tabela de 1024 amostras (int16) somando harmônicos [(n, amplitude), ...].
    Usa duas passadas para não criar listas temporárias de floats.
    alvo_rms=None: normaliza o PICO em 30000 (comportamento original).
    alvo_rms=N:    normaliza a energia (RMS) em N, limitando o pico a 32000,
                   para tabelas diferentes terem o mesmo volume percebido."""
    gc.collect()
    w = 2 * math.pi / TAM_TAB

    # Passada 1: descobre o pico (e a energia)
    pico = 0.0
    soma2 = 0.0
    for i in range(TAM_TAB):
        s = 0.0
        for h, a in harmonicos:
            s += a * math.sin(w * h * i)
        if abs(s) > pico:
            pico = abs(s)
        soma2 += s * s
    if alvo_rms is None:
        k = 30000 / pico
    else:
        k = alvo_rms / math.sqrt(soma2 / TAM_TAB)
        if pico * k > 32000:
            k = 32000 / pico

    # Passada 2: grava direto no array de 2 KB
    tab = array.array('h', bytes(2 * TAM_TAB))
    for i in range(TAM_TAB):
        s = 0.0
        for h, a in harmonicos:
            s += a * math.sin(w * h * i)
        tab[i] = int(s * k)
    return tab


tab_seno = _tabela([(1, 1.0)])
RMS_PIANO = 14400   # [PIANO 2] mesmo RMS em todas as tabelas do piano
tab_piano = _tabela([(1, 1.0), (2, 0.55), (3, 0.30), (4, 0.18), (5, 0.10), (6, 0.05)], RMS_PIANO)
tab_serra = _tabela([(h, 1.0 / h) for h in range(1, 11)])   # "serra" suave

# ---- [PIANO 2 e 5] tabelas extras do piano --------------------------------
# tab_piano (acima) passa a ser a tabela "média" (oitava 4).
# Graves: mais harmônicos. Agudos: poucos (evita som estridente/aliasing).
tab_piano_grave = _tabela([(1, 1.0), (2, 0.70), (3, 0.50), (4, 0.35), (5, 0.25),
                           (6, 0.18), (7, 0.12), (8, 0.08), (9, 0.05), (10, 0.03)], RMS_PIANO)
tab_piano_agudo = _tabela([(1, 1.0), (2, 0.35), (3, 0.12), (4, 0.04)], RMS_PIANO)
# Tabela "escura": a nota vai migrando da tabela rica para esta enquanto decai.
tab_escura = _tabela([(1, 1.0), (2, 0.25)], RMS_PIANO)
# Índice = registro: 0 = oitava 3 (e abaixo), 1 = oitava 4, 2 e 3 = oitava 5 (e acima)
TABS_RICAS = (tab_piano_grave, tab_piano, tab_piano_agudo, tab_piano_agudo)

# ---- [PIANO 3] tabela de ruído para a "martelada" -------------------------
tab_ruido = array.array('h', bytes(2 * TAM_TAB))
for _i in range(TAM_TAB):
    tab_ruido[_i] = random.getrandbits(15) - 16384

# nome: (tabela, sustain/bloco, release/bloco, ataque (fração/bloco), nível Q12)
# Obs.: o "Piano" usa o caminho próprio de gerar() (parâmetros PIANO abaixo);
# a linha dele aqui só mantém o formato da tabela.
INSTR = {
    "Piano":        (tab_piano, 0.988, 0.55, 1.0, 2400),
    "Sintetizador": (tab_serra, 1.000, 0.72, 0.35, 1800),  # sustenta, ataque suave
    "Afinador":     (tab_seno,  1.000, 0.60, 0.50, 2400),  # senoide pura
}
GANHO_SINT = 2   # ganho extra do sintetizador em relação ao player

# ---- Parâmetros do piano (1 bloco = 256 amostras = 5,8 ms a 44,1 kHz) -------
# [PIANO 1] decaimento em duas fases, por registro
F_RAPIDO = 0.974                                  # fase rápida: tau ~0,22 s
FATOR_LENTO = (0.9982, 0.9972, 0.9958, 0.9936)    # fase lenta: C3 3,2 s ... C6 0,9 s
PESO_RAPIDO = 0.6                                 # peso da fase rápida na amplitude
REL_PIANO = (0.70, 0.65, 0.60, 0.55)              # release por registro (grave dura mais)
# [PIANO 2] brilho que decai
F_BRILHO = 0.968                                  # tau ~0,18 s
PISO_BRILHO = 0.25                                # nunca vira senoide pura
# [PIANO 3] ataque e martelada
NIVEL_PIANO = 1700                                # nível Q12 por voz (antes 2400)
ATAQUE_INICIAL = 0.9                              # fração do nível já no 1º bloco
RUIDO_NIVEL = 0.10                                # martelada = 10% do nível
RUIDO_FATOR = 0.6                                 # cai ~17 ms
PASSO_RUIDO = 10368889                            # ~0,618 * 2^24 (não repete padrão)
# [PIANO 4] duas cordas
DESAFINA = 1.0015                                 # ~2,5 cents
CORDA2 = 0.35                                     # fatia da 2ª corda (desigual: o batimento
                                                  # vira ondulação, sem "apagar" a nota)
# [PIANO 6] polifonia
MAX_VOZES = 6


@micropython.viper
def mix_voz(acc, n: int, tab, fase: int, passo: int, a0: int, a1: int) -> int:
    """Soma n amostras de uma voz no acumulador int32 'acc'.
    fase: acumulador de 24 bits; amplitude em Q12 com rampa linear a0 -> a1.
    [PIANO 5] leitura da tabela com interpolação linear (menos granulação)."""
    pa = ptr32(acc)
    pt = ptr16(tab)
    amp = a0 << 8
    step = ((a1 - a0) << 8) // n
    for i in range(n):
        k = fase >> 14                    # índice (10 bits)
        fr = (fase >> 6) & 255            # fração entre amostras (8 bits)
        s0 = int(pt[k])
        s1 = int(pt[(k + 1) & 1023])
        if s0 >= 32768:
            s0 -= 65536
        if s1 >= 32768:
            s1 -= 65536
        s = s0 + (((s1 - s0) * fr) >> 8)
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
        v = ((int(pa[i]) >> 2) * ganho) >> 10
        # [PIANO 6] joelho suave: acima de 16384 a inclinação cai para 1/8,
        # em vez de cortar seco (acordes e volume alto distorciam).
        if v > 16384:
            v = 16384 + ((v - 16384) >> 3)
        elif v < -16384:
            v = -16384 + ((v + 16384) >> 3)
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
        self.n = bloco                      # 256 amostras = ~5,8 ms a 44,1 kHz
        self.k = 16777216.0 / taxa          # 2^24 / taxa
        self.acc = array.array('i', [0] * bloco)
        self.out = bytearray(bloco * 2)
        # midi -> [fase, amp, ligada, estava_ligada, alvo_env,          (todos os instrumentos)
        #          a_rapida, a_lenta, exc_brilho, fase2, ruido]         (só o piano usa)
        self.vozes = {}

    def gerar(self, alvo, instr, ganho_volume):
        tab, sust, rel, atk, nivel = INSTR[instr]
        piano = instr == "Piano"
        n = self.n
        vozes = self.vozes
        if len(alvo) > MAX_VOZES:           # [PIANO 6] limite de polifonia
            alvo = alvo[:MAX_VOZES]
        for v in vozes.values():
            v[3] = v[2]
            v[2] = False
        for m in alvo:
            v = vozes.get(m)
            if v is None:
                vozes[m] = [0, 0.0, True, False, nivel, 0.0, 0.0, 1.0, 0, 0.0]
            else:
                v[2] = True
        mortos = []
        for m in vozes:
            v = vozes[m]
            amp = v[1]
            passo = int(self.midi.freq_afinada(m) * self.k)

            if piano:
                # registro: 0 = oitava 3 ... 3 = oitava 6
                reg = (m - 48) // 12
                if reg < 0:
                    reg = 0
                elif reg > 3:
                    reg = 3

                if v[2]:                                    # tecla apertada
                    if not v[3]:                            # novo ataque
                        v[5] = NIVEL_PIANO                  # [PIANO 1] fase rápida
                        v[6] = NIVEL_PIANO                  # [PIANO 1] fase lenta
                        v[7] = 1.0                          # [PIANO 2] brilho máximo
                        v[9] = NIVEL_PIANO * RUIDO_NIVEL    # [PIANO 3] martelada
                        if amp == 0.0:                      # voz nova: ataque imediato
                            amp = NIVEL_PIANO * ATAQUE_INICIAL
                    w0 = PISO_BRILHO + (1.0 - PISO_BRILHO) * v[7]
                    v[5] *= F_RAPIDO                        # [PIANO 1]
                    v[6] *= FATOR_LENTO[reg]                # [PIANO 1]
                    v[7] *= F_BRILHO                        # [PIANO 2]
                    a1 = PESO_RAPIDO * v[5] + (1.0 - PESO_RAPIDO) * v[6]
                    w1 = PISO_BRILHO + (1.0 - PISO_BRILHO) * v[7]
                else:                                       # tecla solta: release
                    a1 = amp * REL_PIANO[reg]               # [PIANO 1]
                    w0 = w1 = PISO_BRILHO + (1.0 - PISO_BRILHO) * v[7]
                    if a1 < 8:
                        mortos.append(m)

                rica = TABS_RICAS[reg]                      # [PIANO 5] tabela por registro
                passo2 = int(passo * DESAFINA)              # [PIANO 4] 2ª corda
                h0 = amp * (1.0 - CORDA2)                   # corda 1 (65%)
                h1 = a1 * (1.0 - CORDA2)
                g0 = amp * CORDA2                           # corda 2 (35%)
                g1 = a1 * CORDA2
                f1 = v[0]
                f2 = v[8]
                # [PIANO 2 + 4] 2 cordas x (tabela rica + tabela escura), fases em par
                v[0] = mix_voz(self.acc, n, rica, f1, passo,
                               int(h0 * w0), int(h1 * w1))
                mix_voz(self.acc, n, tab_escura, f1, passo,
                        int(h0 * (1.0 - w0)), int(h1 * (1.0 - w1)))
                v[8] = mix_voz(self.acc, n, rica, f2, passo2,
                               int(g0 * w0), int(g1 * w1))
                mix_voz(self.acc, n, tab_escura, f2, passo2,
                        int(g0 * (1.0 - w0)), int(g1 * (1.0 - w1)))
                if v[9] > 8:                                # [PIANO 3] martelada
                    mix_voz(self.acc, n, tab_ruido, f1, PASSO_RUIDO,
                            int(v[9]), int(v[9] * RUIDO_FATOR))
                    v[9] *= RUIDO_FATOR
                v[1] = a1

            else:
                if v[2]:
                    if not v[3]:
                        v[4] = nivel          # novo ataque
                    v[4] *= sust
                    a1 = amp + (v[4] - amp) * atk
                else:
                    a1 = amp * rel
                    if a1 < 8:
                        mortos.append(m)
                v[0] = mix_voz(self.acc, n, tab, v[0], passo, int(amp), int(a1))
                v[1] = a1
        for m in mortos:
            del vozes[m]
        finalizar(self.acc, self.out, n, ganho_volume * GANHO_SINT)
        return self.out
