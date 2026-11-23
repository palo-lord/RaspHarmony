# ============================================================
# midi.py - Notas, frequências, acordes e escalas
# ============================================================
import math
import array

from config import SAMPLE_RATE


class MIDI:
    NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

    CHORD_TYPES = ["Maior", "Menor", "Diminuto", "Aumentado"]
    NUM_CHORD_TYPES = len(CHORD_TYPES)

    CHORD_INTERVALS = {
        "Maior":     [0, 4, 7],
        "Menor":     [0, 3, 7],
        "Diminuto":  [0, 3, 6],
        "Aumentado": [0, 4, 8],
    }

    SCALE_INTERVALS = {
        "Maior":     [0, 2, 4, 5, 7, 9, 11, 12],
        "Menor":     [0, 2, 3, 5, 7, 8, 10, 12],
        "Diminuto":  [0, 2, 3, 5, 6, 8, 9, 11, 12],
        "Aumentado": [0, 2, 4, 6, 8, 10, 12],
    }

    CHORD_COLORS = {
        "Maior":     (0, 20, 0),
        "Menor":     (0, 0, 20),
        "Diminuto":  (20, 0, 0),
        "Aumentado": (20, 20, 0),
    }

    def __init__(self, root_base_midi=60, sample_rate=44100):
        self.root_base_midi = root_base_midi
        self.sample_rate = sample_rate
        # Afinação por nota (em cents, -50..+50), vale para todas as oitavas
        self.afinacao = [0] * 12

    @staticmethod
    def midi_to_freq(n):
        """A4 (MIDI 69) = 440 Hz, temperamento igual"""
        return 440.0 * (2 ** ((n - 69) / 12))

    def freq_afinada(self, n):
        """Frequência da nota MIDI n já com o ajuste de afinação (cents)."""
        return 440.0 * (2 ** ((n - 69) / 12 + self.afinacao[n % 12] / 1200))

    def midi_to_name(self, n):
        """Converte valor MIDI para nome com oitava (ex: 60 -> 'C4')"""
        nome = self.NOTE_NAMES[n % 12]
        oitava = (n // 12) - 1
        return nome + str(oitava)

    def nome_to_freq(self, nome):
        if len(nome) == 3:
            letra = nome[0:2]
            oitava = int(nome[2])
        else:
            letra = nome[0]
            oitava = int(nome[1])
        semitom = self.NOTE_NAMES.index(letra)
        midi = (oitava + 1) * 12 + semitom
        return self.midi_to_freq(midi)

    def obter_acorde(self, indice_raiz, tipo_acorde):
        """Retorna [(nome, freq), ...] para tônica, terça e quinta."""
        root_midi = self.root_base_midi + indice_raiz
        intervalos = self.CHORD_INTERVALS[tipo_acorde]
        return [(self.midi_to_name(root_midi + iv), self.midi_to_freq(root_midi + iv)) for iv in intervalos]

    def acorde_midis(self, indice_raiz, tipo_acorde):
        """Retorna só os números MIDI das notas do acorde."""
        root_midi = self.root_base_midi + indice_raiz
        return [root_midi + iv for iv in self.CHORD_INTERVALS[tipo_acorde]]

    def obter_escala(self, indice_raiz, tipo_acorde):
        root_midi = self.root_base_midi + indice_raiz
        intervalos = self.SCALE_INTERVALS[tipo_acorde]
        return [(self.midi_to_name(root_midi + iv), self.midi_to_freq(root_midi + iv)) for iv in intervalos]

    def wave_gen(self, frequencia, duracao_ms, volume=0.2):
        """Gera um buffer PCM 16-bit com uma senoide (mantido da versão anterior;
        o teclado usa o motor 'Sintese', que é bem mais rápido)."""
        num_amostras = int(self.sample_rate * (duracao_ms / 1000.0))
        if frequencia == 0:
            return bytearray(num_amostras * 2)
        amostras = array.array('h')
        amplitude = int(32767 * max(0.0, min(1.0, volume)))
        for i in range(num_amostras):
            t = i / self.sample_rate
            valor = int(amplitude * math.sin(2 * math.pi * frequencia * t))
            amostras.append(valor)
        return amostras


NOTAS = MIDI.NOTE_NAMES

# Lista de acordes: 12 raízes x 4 tipos, agrupados por raiz
ACORDES_LISTA = [NOTAS[r] + " " + t for r in range(12) for t in MIDI.CHORD_TYPES]

midi = MIDI(root_base_midi=60, sample_rate=SAMPLE_RATE)
