# ============================================================
# RaspHarmony - Sistema Embarcado Sintetizador e Reprodutor de Áudio
# ============================================================
# Nome: Paulo Sergio Gonçalves Júnior RA: 218474
# Nome: Vinicius Pedrillo de Souza RA: 258667
# ============================================================
# Ponto de entrada. O código foi dividido em módulos:
#   config.py        pinos e constantes
#   encoder.py       Encoder (encoder rotativo)
#   botao.py         Botao (debounce sem sleep)
#   joystick.py      Joystick
#   teclado.py       Teclado (matriz 4x4)
#   armazenamento.py montagem do SD e lista de WAVs
#   wavfile.py       WavFile
#   audio.py         SaidaAudio (I2S + volume)
#   midi.py          MIDI (notas, acordes, escalas)
#   sintese.py       Sintese (motor polifônico)
#   player.py        Player
#   estado.py        Estado (estado global + navegação)
#   ui.py            Tela (display OLED)
#   app.py           Aplicacao (hardware + laço principal)
# Dependências externas (copiar para o Pico): sh1106.py, sdcard.py
# ============================================================
import micropython

micropython.alloc_emergency_exception_buf(100)  # permite ver erros dentro de IRQ

from app import Aplicacao

Aplicacao().executar()
