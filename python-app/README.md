# POC — Transcrição com Diarização de Consultas Médicas

Prova de conceito que recebe o **áudio de uma consulta médica** (2 pessoas — médico e
paciente — em português do Brasil, gravadas por **um único microfone**) e gera:

1. Um **roteiro em texto** onde cada fala está rotulada por falante e com horário.
2. Um **rascunho de prontuário** com campos clínicos (QP, HDA, hipótese diagnóstica,
   conduta, etc.), estruturado por um **LLM rodando 100% localmente**.

```
[00:00:00] Falante 1: Bom dia. Por favor, me conte o que você está sentindo hoje.
[00:00:06] Falante 2: Bom dia, doutora. Estou com uma dor de cabeça há quatro dias.
[00:00:14] Falante 1: Entendo. Essa dor é constante ou ela vai e volta?
```

> Por convenção, **quem fala primeiro (Falante 1) é o médico** e o Falante 2 é o paciente.

## 🔒 Privacidade (LGPD)

São **dados de saúde sensíveis**. Tudo roda **100% localmente** na máquina:

- Os modelos de IA rodam **offline**, na CPU. Nenhum áudio ou transcrição sai do computador.
- O **único** acesso externo é o **download único dos pesos dos modelos** na primeira
  execução. Depois disso, nada sai do equipamento.
- O token do Hugging Face (necessário só para baixar o modelo gated) fica no arquivo
  `.env`, que é ignorado pelo Git.

## 🏗️ Arquitetura

```
                    ┌────────────────────┐
   microfone  ───▶  │   index.html       │   Gravador de áudio no navegador.
                    │ (Web Audio API)    │   Captura PCM e exporta WAV mono 16-bit.
                    └─────────┬──────────┘
                              │  gravacao-AAAA-MM-DD...wav
                              ▼
                    ┌────────────────────┐
   arquivo .wav ──▶ │  transcrever.py    │   Orquestrador (Python).
                    └─────────┬──────────┘
                              │
              ┌───────────────┴────────────────┐
              ▼                                 ▼
   ┌────────────────────┐          ┌────────────────────────┐
   │  faster-whisper    │          │   pyannote.audio        │
   │  (modelo medium)   │          │  (speaker-diarization-  │
   │                    │          │      community-1)       │
   │  O QUE foi dito +  │          │   QUEM falou em cada    │
   │  horário p/ palavra│          │   intervalo de tempo    │
   └─────────┬──────────┘          └───────────┬─────────────┘
             │  palavras + tempos              │  segmentos por falante
             └────────────────┬────────────────┘
                              ▼
                    ┌────────────────────┐
                    │  Alinhamento +     │   Cada palavra recebe o falante
                    │  agrupamento       │   com maior sobreposição de tempo.
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │  glossario.py      │   Correção de grafia de termos
                    │  (corrigir_texto)  │   clínicos (fuzzy match, offline).
                    └─────────┬──────────┘
                              ▼
                    transcricoes/<slug>.txt   ← roteiro com falantes e horários
                              │
                    ┌─────────▼──────────┐
                    │  estruturar.py     │   Lê o roteiro e chama o Ollama
                    └─────────┬──────────┘   via HTTP (localhost:11434).
                              │  POST /api/chat
                              ▼
                    ┌────────────────────┐
                    │  Ollama            │   Servidor de LLM local.
                    │  (llama3.1:8b)     │   Extrai campos de prontuário
                    │                    │   a partir do prompt estruturado.
                    └─────────┬──────────┘
                              ▼
                    prontuarios/<slug>.json + .txt   ← rascunho de prontuário
```

### Etapas do `transcrever.py`

1. **Transcrição** (`faster-whisper`, modelo `medium`, `language="pt"`): converte a fala
   em texto com **timestamp por palavra**. Roda em `device="cpu"` / `compute_type="int8"`.
2. **Diarização** (`pyannote.audio`, modelo `speaker-diarization-community-1`): descobre
   **quem** falou em cada intervalo. Forçamos `num_speakers=2`, pois sabemos que são
   sempre 2 pessoas — isso melhora a precisão.
3. **Alinhamento**: cada palavra é atribuída ao falante com **maior sobreposição de
   tempo**. Palavras consecutivas do mesmo falante são agrupadas em uma única linha.
4. **Glossário** (`glossario.py`): corrige automaticamente a grafia de termos clínicos
   que o Whisper costuma errar (ex.: `"dispineia"` → `"dispneia"`). Só troca quando a
   similaridade é alta — conservador de propósito.
5. **Saída**: gera `transcricoes/<slug>.txt` no formato `[HH:MM:SS] Falante N: texto`.

### Etapa do `estruturar.py`

Lê o roteiro em `transcricoes/<slug>.txt` e envia ao **Ollama** (LLM local) com um
prompt estruturado para extrair:

| Campo | Descrição |
|-------|-----------|
| **Queixa Principal (QP)** | O que o paciente relatou sentir |
| **História da Doença Atual (HDA)** | Contexto, evolução e detalhes dos sintomas |
| **Antecedentes / Hábitos** | Histórico médico, medicações em uso, hábitos |
| **Hipótese Diagnóstica** | Suspeita declarada pelo médico |
| **Conduta / Plano** | Exames, encaminhamentos ou orientações definidos |

O prompt instrui o modelo a usar **somente o que foi verbalizado** e escrever
`"Não relatado"` quando faltar informação — para evitar alucinação de dados clínicos.
A saída sai em `prontuarios/<slug>.json` (para integração) e `prontuarios/<slug>.txt`
(legível).

> **Atenção:** o prontuário é um **rascunho gerado por IA**. O médico deve revisar e
> validar antes de lançar no sistema.

## 📚 Glossário médico (`glossario.py` + `glossario.json`)

O glossário tem dois papéis:

- **Correção pós-transcrição** — aplicada automaticamente ao gerar o roteiro. Compara
  cada palavra transcrita com os termos do glossário usando `difflib` (similaridade
  fuzzy, biblioteca padrão do Python). Só corrige quando a semelhança supera
  `MIN_SIMILARIDADE = 0.86` e a palavra tem ≥ 5 letras, evitando falsos positivos.

- **Categorização** — detecta quais termos do glossário aparecem no roteiro e os agrupa
  por categoria:

  | Categoria | Exemplos |
  |-----------|---------|
  | Sintomas e queixas | dispneia, cefaleia, náusea |
  | Doenças e condições | hipertensão, diabetes, asma |
  | Medicamentos | dipirona, amoxicilina, losartana |
  | Exames | hemograma, eletrocardiograma, raio-x |
  | Procedimentos e condutas | sutura, curativo, internação |
  | Anatomia | abdômen, tórax, mediastino |
  | Sinais vitais e medidas | pressão arterial, SpO2, glicemia |

O `glossario.json` não contém dados de pacientes e é versionado — edite à vontade para
expandir a terminologia. Tudo offline, sem dependências além da biblioteca padrão.

## 🛠️ Ferramentas utilizadas

| Ferramenta | Papel | Versão testada |
|------------|-------|----------------|
| **Python** | Linguagem do orquestrador | 3.12 (via Homebrew) |
| **faster-whisper** | Transcrição (speech-to-text) com timestamps | 1.2.1 |
| **pyannote.audio** | Diarização (separação de falantes) | 4.0.4 |
| **PyTorch** | Motor de redes neurais (CPU, Apple Silicon) | 2.12 |
| **python-dotenv** | Lê o token do `.env` com segurança | 1.2.2 |
| **ffmpeg** | Leitura/decodificação de áudio | 8.1.1 (Homebrew) |
| **Ollama** | Servidor de LLM local (prontuário) | 0.9+ |
| **llama3.1:8b** | Modelo de linguagem para estruturar o roteiro | via Ollama |
| **difflib** | Correção fuzzy do glossário | biblioteca padrão |
| **Web Audio API** | Gravação no navegador (`index.html`) | nativo do browser |

> O modelo do pyannote é *gated*: exige uma conta gratuita no Hugging Face e aceitar os
> termos de uso de `pyannote/speaker-diarization-community-1`.

## 📦 Pré-requisitos

- macOS com **Apple Silicon** (testado em M4, 16 GB). Não usa GPU NVIDIA/CUDA.
- **Homebrew** instalado.
- Uma conta gratuita no [Hugging Face](https://huggingface.co) com um **Access Token** (tipo *read*).
- **Ollama** instalado e rodando (necessário para `estruturar.py`).

## 🚀 Instalação

```bash
# 1. Dependências de sistema
brew install ffmpeg python@3.12

# 2. Ambiente virtual + bibliotecas Python
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install torch torchaudio faster-whisper "pyannote.audio" python-dotenv

# 3. Ollama (LLM local para o prontuário)
brew install ollama
ollama serve          # deixe rodando em segundo plano
ollama pull llama3.1:8b
```

Depois, acesse e **aceite os termos** do modelo (logado na sua conta HF):
<https://huggingface.co/pyannote/speaker-diarization-community-1>

## ⚙️ Configuração do token

Crie um arquivo **`.env`** na raiz do projeto com o seu token (ele **não** vai para o
código nem para o Git):

```
HF_TOKEN=hf_seu_token_aqui
```

## ▶️ Como usar

### Opção A — gravar pelo navegador

1. Abra o `index.html` no navegador.
2. Clique em **Gravar**, conduza a consulta, clique em **Parar** e **baixe o `.wav`**.
3. Mova o arquivo baixado para a pasta `audios/` do projeto.

### Opção B — usar um áudio já existente

Coloque um arquivo `.wav` (ou `.mp3`, `.m4a`) em `audios/`.

### Passo 1 — transcrever e diarizar

```bash
source .venv/bin/activate
.venv/bin/python transcrever.py audios/consulta_teste.wav
# saída: transcricoes/consulta_teste.txt
```

A **primeira execução** baixa os modelos (Whisper `medium` ~1,5 GB + pyannote) e demora
mais; as seguintes são rápidas e totalmente offline.

### Passo 2 — gerar o rascunho de prontuário

```bash
# certifique-se que o Ollama está rodando: ollama serve
.venv/bin/python estruturar.py transcricoes/consulta_teste.txt
# saída: prontuarios/consulta_teste.json + prontuarios/consulta_teste.txt

# sem argumento, usa o roteiro mais recente automaticamente:
.venv/bin/python estruturar.py
```

## 🎙️ Dicas de gravação (1 microfone)

- **Posicione o microfone entre as duas pessoas**, a distância parecida de cada uma.
- Prefira **WAV mono, 16 kHz** (o gravador já exporta mono; o script reamostra se preciso).
- Reduza ruído de fundo: desligue ar-condicionado barulhento, evite salas com eco.
- Como os papéis são fixos, é trivial renomear "Falante 1/2" para "Médico/Paciente".

## ⚠️ Limitações conhecidas

- **Fala sobreposta**: quando as duas pessoas falam ao mesmo tempo, a diarização erra
  mais. Aceitável para a POC. (Um setup de 2 microfones resolve — ver `manual_mic2.md`.)
- A precisão da transcrição depende da qualidade do áudio. O modelo `medium` equilibra
  velocidade e qualidade; para mais precisão, troque por `large-v3` em `transcrever.py`.
- O prontuário gerado é um **rascunho** — o LLM segue instruções rígidas contra
  alucinação, mas revisão médica é obrigatória antes de qualquer uso clínico.

## 📁 Estrutura do projeto

```
poc1/
├── transcrever.py     # Transcrição + diarização + glossário → roteiro
├── estruturar.py      # Roteiro → prontuário via LLM local (Ollama)
├── glossario.py       # Correção e categorização de termos clínicos
├── glossario.json     # Terminologia médica PT-BR (versionado, sem PII)
├── servidor.py        # Backend do painel web local (http.server, 127.0.0.1)
├── painel.html        # Interface web: gravar → transcrever → prontuário
├── index.html         # Gravador de áudio standalone (Web Audio API)
├── .env               # Token do Hugging Face (NÃO versionado)
├── .gitignore         # Ignora .env, .venv, áudios e saídas clínicas
├── audios/            # <slug>.wav (ignorado pelo Git)
├── transcricoes/      # <slug>.txt — roteiros gerados (ignorado pelo Git)
├── prontuarios/       # <slug>.json + <slug>.txt — prontuários (ignorado pelo Git)
├── manual_mic1.md     # Guia do setup de 1 microfone (implementado)
├── manual_mic2.md     # Guia do setup de 2 microfones (futuro)
└── README.md          # Este arquivo
```
