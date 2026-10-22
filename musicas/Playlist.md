# Lista de Músicas
•Life Goes On\
•Thunderstruck\
•Bohemian Rapasody\
•Até que Durou\
•Sinonimos\
•Silhouette\
•Ceu Azul\
•The real Slim Shady\
•Castelvania Matue\
\
As Músicas devem ser colocadas no cartão micro SD em formato WAV, 16 bits com Sample Rate de 44.1kHz,\
abaixo temos um comando no terminal que converte arquivos MP3 para WAV com as configurações corretas.\
ffmpeg -i "nome.mp3" -ar 44100 -ac 1 -c:a pcm_s16le "nome.wav"
