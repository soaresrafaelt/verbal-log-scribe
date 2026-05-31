# CLAUDE.md

Guia para o Claude Code trabalhar neste repositório. Leia antes de editar.

## O que é

POC que transcreve consultas médicas (2 pessoas, PT-BR, 1 microfone) e gera um
`roteiro.txt` com cada fala rotulada por falante e horário. **Mantenha simples** — é
uma POC, não produção. Sem GUI desktop, sem banco de dados, sem frameworks pesados.

## Restrição inegociável: privacidade (LGPD)

São dados de saúde sensíveis. **Tudo roda localmente e offline.** Nunca introduza código
que envie áudio (ou transcrição) para serviços de nuvem/APIs externas. O único acesso à
rede permitido é o download dos pesos dos modelos na primeira execução.

## Hardware alvo

macOS Apple Silicon (M4, 16 GB), **sem GPU NVIDIA/CUDA**. Sempre use CPU:
- faster-whisper: `device="cpu"`, `compute_type="int8"`.
- pyannote.audio: rodar em CPU (`pipeline.to(torch.device("cpu"))`).
- **Nunca** adicione dependências de CUDA. MPS é instável para esta POC; CPU é o padrão.

## Arquitetura

O fluxo é operado por um **painel web local** (`servidor.py` + `painel.html`) com 3 abas:
gravar áudio → transcrever/diarizar → prontuário (JSON). Os scripts CLI (`transcrever.py`,
`estruturar.py`) continuam valendo isoladamente e são reaproveitados pelo painel como
**funções importadas** — não duplicar lógica nem chamar via subprocess.

**Organização por etapa + histórico por consulta (slug).** Cada consulta tem um
identificador único (**slug**) e seus arquivos são nomeados por ele em cada pasta — o
histórico **acumula, nada é sobrescrito**. As três pastas estão no `.gitignore` (dados
clínicos sensíveis):
- `audios/` — `<slug>.wav`
- `transcricoes/` — `<slug>.txt` (saída do `transcrever.py`, entrada do `estruturar.py`)
- `prontuarios/` — `<slug>.json` + `<slug>.txt` (JSON resolvido, saída do `estruturar.py`)

O slug é definido por contexto: **no painel** é o horário do upload (`AAAA-MM-DD_HH-MM-SS`,
gerado por `servidor.novo_slug()`); **no CLI** é o nome-base do arquivo de entrada
(`transcrever.slug_de_arquivo`), então `audios/consulta_teste.wav` → `transcricoes/consulta_teste.txt`
→ `prontuarios/consulta_teste.{json,txt}` (cadeia rastreável pelo nome).

Caminhos são montados por **helpers**, não por constantes de arquivo fixo: `transcrever.caminho_roteiro(slug)`,
`estruturar.caminho_prontuario(slug, ext)`, `servidor.caminho_audio(slug)`. As pastas vêm de
`DIR_TRANSCRICOES`/`DIR_PRONTUARIOS`/`DIR_AUDIOS` (absolutas, ancoradas em `DIR_BASE`); o
`servidor.py` e o `estruturar.py` **reúsam** as do `transcrever.py` (DRY). Quem grava chama
`os.makedirs(..., exist_ok=True)` antes — as pastas nascem na 1ª execução.

- `servidor.py` — backend do painel. **Só biblioteca padrão** (`http.server`), zero deps
  novas. Escuta **somente em `127.0.0.1`** (LGPD: nunca expor na rede). Mantém em `estado`
  a **consulta ativa** (`estado["consulta"]`, o slug sobre o qual as tarefas operam); na
  inicialização aponta para a mais recente. Endpoints:
  `POST /api/upload` (recebe o WAV cru → inicia **nova consulta** `audios/<slug>.wav` e a torna ativa),
  `POST /api/transcrever` e `POST /api/estruturar` (pipeline em **thread de fundo**, uma tarefa por vez, sobre a consulta ativa),
  `GET /api/status` (progresso por polling; inclui `consulta`), `GET|POST /api/roteiro`, `GET /api/prontuario`,
  `GET /api/termos` (categoriza os termos do glossário no roteiro ativo: `{categorias, rotulos}`),
  `GET /api/consultas` (lista o histórico com flags de etapa), `POST /api/consulta` (reabre uma consulta do histórico).
- `painel.html` — interface de aba única servida pelo `servidor.py`. Tem uma **barra de
  histórico** (seletor que reabre consultas anteriores via `/api/consulta`). Reusa o gravador
  WAV do `index.html`; o roteiro é **editável** (corrigir falantes antes de estruturar). Abaixo do
  roteiro, um painel **"Termos identificados"** mostra os termos do glossário por categoria (via `/api/termos`).
- `index.html` — gravador standalone no navegador (Web Audio API + ScriptProcessor), exporta
  WAV PCM 16-bit mono. Estático, sem build, sem deps. Fallback do painel.
- `transcrever.py` — orquestrador. Expõe `gerar_roteiro_do_audio(audio, token, progresso=...)`
  (usado pelo painel) e roda como CLI. Pipeline:
  1. `faster-whisper` (modelo `medium`, `language="pt"`, `word_timestamps=True`) → texto + tempo por palavra.
  2. `pyannote.audio` (`num_speakers=2`) → quem falou em cada intervalo.
  3. Alinhamento por **maior sobreposição de tempo** entre palavra e segmento de falante.
  4. Agrupa palavras consecutivas do mesmo falante → `transcricoes/<slug>.txt` (`[HH:MM:SS] Falante N: texto`).
  5. **Correção pelo glossário** (`glossario.corrigir_texto`, ligada por `USAR_GLOSSARIO`): ajusta a
     grafia de termos clínicos no texto de cada fala (nunca no prefixo `[hora] Falante N:`). O CLI
     ainda imprime a categorização (`glossario.categorizar_texto`) ao final.
- `glossario.py` + `glossario.json` — terminologia médica PT-BR. **Só biblioteca padrão** (`difflib`),
  offline. `glossario.json` é dado de referência (sem PII) → **versionado**, edite à vontade. Duas
  funções: `corrigir_texto(texto)` (correção fonética conservadora — só troca quando a similaridade
  é alta, ver `MIN_SIMILARIDADE`/`MIN_TAMANHO`; devolve `(texto, correcoes)`) e `categorizar_texto(texto)`
  (detecta termos e os agrupa por categoria — `CATEGORIAS_ROTULOS`). O roteiro fica **limpo** (a
  categorização é exibida à parte, não anotada inline, para não quebrar o formato nem a entrada do `estruturar.py`).
- `estruturar.py` — `transcricoes/<slug>.txt` → campos de prontuário via LLM local (Ollama). Expõe
  `estruturar_transcricao(transcricao, progresso=...)`, que **levanta exceção** em falha
  (`ConnectionError`/`ValueError`); o CLI e o painel tratam e formatam a mensagem. Sem
  argumento, o CLI usa o roteiro **mais recente** (`roteiro_mais_recente()`).

As funções de pipeline aceitam um callback `progresso(texto)` (no CLI é o `print`; no painel
atualiza o status do job). Falante 1 = quem fala primeiro = médico (convenção).

## ⚠️ Gotchas da pyannote.audio 4.x (NÃO regredir para a API 3.x)

A versão instalada é a **4.0.4**, cuja API difere dos tutoriais antigos (série 3.x):

- **Modelo:** use `pyannote/speaker-diarization-community-1` (gated, autocontido).
  **Não** use `speaker-diarization-3.1` nem dependa de `segmentation-3.0` separado.
- **Auth:** `Pipeline.from_pretrained(checkpoint, token=...)` — o parâmetro é `token`,
  **não** `use_auth_token`.
- **Retorno:** `pipeline(audio, num_speakers=2)` devolve um objeto `DiarizeOutput`, não
  uma `Annotation`. Use `resultado.exclusive_speaker_diarization` (sem sobreposição,
  ideal para alinhar com transcrição) e nela chame `.itertracks(yield_label=True)`.

## Convenções de código

- **Comentários e mensagens ao usuário em português.**
- Mensagens de progresso amigáveis ("Transcrevendo...", "Identificando falantes...").
- Trate erros comuns com mensagens claras: arquivo não encontrado, token ausente/inválido,
  formato de áudio não suportado, termos do modelo não aceitos.
- Configurações no topo de `transcrever.py` (constantes `MODELO_WHISPER`, `IDIOMA`,
  `NUM_FALANTES`, `ARQUIVO_SAIDA`).

## Comandos

```bash
# Ativar ambiente
source .venv/bin/activate

# Painel web (fluxo completo): abre em http://127.0.0.1:8000
.venv/bin/python servidor.py            # ou: python servidor.py 9000

# CLI isolado (sem o painel) — o slug vem do nome do arquivo de audio
.venv/bin/python transcrever.py audios/consulta_teste.wav  # -> transcricoes/consulta_teste.txt
.venv/bin/python estruturar.py transcricoes/consulta_teste.txt  # -> prontuarios/consulta_teste.{json,txt}
.venv/bin/python estruturar.py                              # sem arg: usa o roteiro mais recente

# Checar sintaxe
.venv/bin/python -m py_compile transcrever.py estruturar.py servidor.py
```

## Segredos

O token do Hugging Face fica em `.env` (`HF_TOKEN=hf_...`), lido via `python-dotenv`.
**Nunca** coloque o token no código, em logs ou em mensagens. `.env`, `.venv/` e as três
pastas de dados clínicos — `audios/` (inclui o `audio_atual.wav` que o painel salva),
`transcricoes/` e `prontuarios/` — são ignoradas pelo `.gitignore` (além dos padrões
`*.wav/*.mp3/*.m4a`, `roteiro.txt`, `prontuario.*` para qualquer arquivo solto na raiz).
Mantenha assim.

## Não confundir

`manual_mic1.md` é o guia do setup de **1 microfone** (implementado). `manual_mic2.md`
descreve o setup de **2 microfones** (ainda não implementado) — não misture os dois.
