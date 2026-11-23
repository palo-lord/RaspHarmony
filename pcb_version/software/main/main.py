# ============================================================
# RaspHarmony (versão PCB) - Sistema Embarcado Sintetizador e Reprodutor de Áudio
# ============================================================
# Nome: Paulo Sergio Gonçalves Júnior RA: 218474
# Nome: Vinicius Pedrillo de Souza RA: 258667
# ============================================================
# Ponto de entrada. Módulos (copiar a pasta lib para /lib no Pico):
#   config.py        pinos e constantes
#   encoder.py       Encoder (encoder rotativo, só giro = volume)
#   botoes.py        Botoes (Up, Down, Left, Right, Ok: curto/longo, por interrupção)
#   mcp23017.py      MCP23017 (expansor de GPIO I2C, de terceiros)
#   toque.py         TecladoToque (16 pads capacitivos, tempo de carga)
#   armazenamento.py montagem do SD e lista de WAVs
#   wavfile.py       WavFile
#   audio.py         SaidaAudio (I2S + volume)
#   midi.py          MIDI (notas, acordes, escalas)
#   sintese.py       Sintese (motor polifônico)
#   player.py        Player
#   estado.py        Estado (estado global + navegação + mapeamento das teclas)
#   ui.py            Tela (display OLED SH1106 SPI)
#   app.py           Aplicacao (hardware + laço principal)
# Dependências externas: sh1106.py, sdcard.py, mcp23017.py
# ============================================================
import micropython

micropython.alloc_emergency_exception_buf(100)  # permite ver erros dentro de IRQ

from app import Aplicacao

Aplicacao().executar()
