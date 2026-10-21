# ============================================================
# wavfile.py - Leitura de arquivos WAV PCM
# ============================================================
import struct


class WavFile:
    """Abre um WAV, interpreta o cabeçalho e permite ler os dados em blocos."""

    def __init__(self, caminho):
        self.caminho = caminho
        self.f = open(caminho, "rb")
        self.formato = 0
        self.canais = 0
        self.taxa = 0
        self.bits = 0
        self.data_inicio = 0
        self.data_tamanho = 0
        self.restante = 0
        try:
            self._ler_cabecalho()
        except Exception:
            self.f.close()
            raise

    def _ler_cabecalho(self):
        f = self.f
        cab = f.read(12)
        if len(cab) < 12 or cab[0:4] != b"RIFF" or cab[8:12] != b"WAVE":
            raise ValueError("Não é um arquivo WAV válido: " + self.caminho)

        achou_fmt = False
        while True:
            cab_chunk = f.read(8)
            if len(cab_chunk) < 8:
                raise ValueError("Chunk 'data' não encontrado")
            chunk_id = cab_chunk[0:4]
            (chunk_size,) = struct.unpack("<I", cab_chunk[4:8])

            if chunk_id == b"fmt ":
                fmt = f.read(chunk_size)
                (self.formato, self.canais, self.taxa,
                 _byte_rate, _align, self.bits) = struct.unpack("<HHIIHH", fmt[:16])
                achou_fmt = True
            elif chunk_id == b"data":
                if not achou_fmt:
                    raise ValueError("'data' antes de 'fmt '")
                self.data_inicio = f.tell()
                self.data_tamanho = chunk_size
                self.restante = chunk_size
                break
            else:
                f.seek(chunk_size, 1)  # ignora LIST, INFO, etc.

            if chunk_size & 1:         # chunks são alinhados em 2 bytes
                f.seek(1, 1)

        if self.formato != 1:
            raise ValueError("Somente WAV PCM (formato 1) é suportado")

    @property
    def duracao_s(self):
        bytes_por_seg = self.taxa * self.canais * (self.bits // 8)
        return self.data_tamanho / bytes_por_seg if bytes_por_seg else 0

    @property
    def posicao_s(self):
        bytes_por_seg = self.taxa * self.canais * (self.bits // 8)
        lidos = self.data_tamanho - self.restante
        return lidos / bytes_por_seg if bytes_por_seg else 0

    def info(self):
        return "{}: {} Hz, {} bits, {} canal(is), {:.1f} s".format(
            self.caminho, self.taxa, self.bits, self.canais, self.duracao_s)

    def ler_bloco(self, buf):
        """Lê para dentro de 'buf' (bytearray/memoryview). Retorna nº de bytes."""
        if self.restante <= 0:
            return 0
        n = self.f.readinto(buf if len(buf) <= self.restante
                            else memoryview(buf)[:self.restante])
        n = n or 0
        self.restante -= n
        return n

    def reiniciar(self):
        self.f.seek(self.data_inicio)
        self.restante = self.data_tamanho

    def buscar(self, delta_s):
        """Move a posição de leitura em delta_s segundos (negativo retrocede)."""
        frame = self.canais * (self.bits // 8)
        if frame == 0:
            return
        lidos = self.data_tamanho - self.restante
        novo = lidos + int(delta_s * self.taxa) * frame
        if novo < 0:
            novo = 0
        elif novo > self.data_tamanho:
            novo = self.data_tamanho
        novo -= novo % frame
        self.f.seek(self.data_inicio + novo)
        self.restante = self.data_tamanho - novo

    def fechar(self):
        self.f.close()
