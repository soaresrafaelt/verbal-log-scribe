# POC — Transcrição de Consultas Médicas

Backend (CLI + API) que processa **arquivos de áudio de consultas médicas** (2 pessoas — médico e
paciente — em português do Brasil, gravadas por **um único microfone**) e gera:

1. Um **arquivo de texto (.txt)** com a transcrição, onde cada segmento está rotulado por horário.
2. Um **rascunho de prontuário** estruturado por um **LLM via API**, preenchendo automaticamente
   as seções do template enviado.

```
[00:00:00] Bom dia. Por favor, me conte o que você está sentindo hoje.
[00:00:06] Bom dia, doutora. Estou com uma dor de cabeça há quatro dias.
[00:00:14] Entendo. Essa dor é constante ou ela vai e volta?
```

> Não há separação automática de falantes. O LLM infere quem é o médico e quem é o paciente
> pelo contexto da conversa ao estruturar o prontuário.

## 🔒 Privacidade (LGPD)

São **dados de saúde sensíveis**. Tudo roda **100% localmente** na máquina:

- Transcrição e correção rodam **offline**, sem nenhum acesso à rede.
- Antes de qualquer texto chegar à API do LLM, o módulo `anonimizar.py` mascara PII
  (CPF, telefone, e-mail, CEP, datas, CRM, RG e nomes de pessoas detectados por regex + spaCy NER).
- O arquivo `transcricoes/<id>.txt` mantém o texto original na máquina; **só o prompt anonimizado
  sai para a nuvem**.
- O **único** acesso externo além das APIs de LLM é o download dos pesos do Whisper na primeira
  execução.

## 🏗️ Arquitetura

Dois modos de uso — CLI direto ou via API HTTP:

**Via CLI:**
```
Arquivo de áudio
    │
    ▼
transcrever.py
  ├─▶ mlx-whisper (transcrição offline, Apple Silicon)
  └─▶ glossario.py (correção de termos clínicos via difflib)
    │
    ▼
transcricoes/<slug>.txt   ← texto original, sem mascaramento
    │
    ▼
estruturar.py
  ├─▶ anonimizar.py (mascara PII antes de sair da máquina)
  └─▶ LLM API (Gemini / OpenAI / Anthropic)
    │
    ▼
prontuarios/<slug>.json + <slug>.txt
```

**Via API (FastAPI):**
```
POST /consulta
  audio (WAV/MP3/M4A) + template (.txt)
    │
    ├─▶ Valida extensão, arquivo não-vazio, template não-vazio
    │
    ▼
  transcrever.gerar_roteiro_do_audio()
    │
    ▼
  anonimizar.anonimizar()   ← mascara PII
    │
    ▼
  estruturar.estruturar_com_template()   ← LLM preenche seções do template
    │
    ▼
  Persiste:
    transcricoes/<id>.txt
    prontuarios/<id>.json + <id>.txt
    consultas.db (SQLite) ← registro completo por id
    │
    ▼
  Retorna {id, transcricao, prontuario, timing}

GET /consulta/{id}
  ← Retorna {id, criado_em, transcricao, prontuario, template_preenchido, timing}
```

O **id** de cada consulta tem o formato `2026-05-31_14-30-00_a3f7` — timestamp + 4 chars hex
aleatórios — garantindo unicidade mesmo com requisições simultâneas.

### Etapas do `transcrever.py`

1. **Transcrição** (`mlx-whisper`, modelo `mlx-community/whisper-large-v3-turbo`): converte a fala
   em texto otimizado para Apple Silicon (Neural Engine do M4/M3/M2). Roda 100% offline.
2. **Correção de glossário** (`glossario.py`): corrige automaticamente a grafia de termos clínicos
   que o Whisper costuma errar (ex.: `"dispineia"` → `"dispneia"`). Usa fuzzy match com `difflib`.
3. **Saída**: gera `transcricoes/<slug>.txt` no formato `[HH:MM:SS] texto`.

### Etapa do `anonimizar.py`

Executa **antes** de qualquer texto chegar à API de LLM:

| Dado mascarado | Técnica |
|----------------|---------|
| CPF, telefone, e-mail, CEP, data, CRM, RG | Regex |
| Nomes após títulos ("Dr.", "paciente", "meu nome é") | Regex contextual |
| Nomes de pessoas sem título | NER spaCy `pt_core_news_sm` (opcional) |

Se o modelo spaCy não estiver instalado, os demais campos ainda são mascarados e um aviso é emitido.

### Etapa do `estruturar.py`

Recebe o roteiro anonimizado e um template com seções (linhas terminadas em `:`), envia ao LLM
e retorna um dict com cada seção preenchida. O prompt instrui o modelo a usar **somente o que foi
verbalizado** e escrever `""` quando faltar informação — para evitar alucinação de dados clínicos.

O provedor é detectado automaticamente pela presença de chave no `.env`:
- `GEMINI_API_KEY` — usa Gemini 2.5 Flash / 2.0 Flash (prioridade máxima)
- `OPENAI_API_KEY` — usa GPT-4o mini
- `ANTHROPIC_API_KEY` — usa Claude Haiku

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
| **Python** | Linguagem do orquestrador | 3.12+ |
| **mlx-whisper** | Transcrição (speech-to-text) otimizada para Apple Silicon | 0.3+ |
| **fastapi** | Servidor HTTP da API | 0.100+ |
| **uvicorn** | ASGI server para rodar o FastAPI | 0.20+ |
| **python-multipart** | Parse de uploads de arquivo na API | 0.0.6+ |
| **python-dotenv** | Lê as chaves de API do `.env` com segurança | 1.0+ |
| **spacy** | NER para detecção de nomes (opcional) | 3.0+ |
| **sqlite3** | Banco de dados local para persistência das consultas | stdlib |
| **google-generativeai** | Cliente da API Gemini (opcional) | 0.3+ |
| **openai** | Cliente da API OpenAI (opcional) | 1.0+ |
| **anthropic** | Cliente da API Anthropic (opcional) | 0.7+ |
| **difflib** | Correção fuzzy do glossário | biblioteca padrão |
| **ffmpeg** | Leitura/decodificação de áudio (instalado via Homebrew) | 6.0+ |

## 📦 Pré-requisitos

- macOS com **Apple Silicon** (testado em M4, 16 GB). Não usa GPU NVIDIA/CUDA.
- **Homebrew** instalado.
- Uma conta e chave de API em ao menos um provedor de LLM:
  - [Gemini API](https://ai.google.dev/) (gratuita com créditos)
  - [OpenAI API](https://platform.openai.com/) (pago)
  - [Anthropic API](https://www.anthropic.com/api) (pago)

## 🚀 Instalação

```bash
# 1. Dependências de sistema
brew install ffmpeg python@3.12

# 2. Ambiente virtual + bibliotecas Python
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 3. (Opcional) Modelo spaCy para mascaramento de nomes por NER
python -m spacy download pt_core_news_sm
```

O `requirements.txt` inclui as dependências essenciais. Os clientes de LLM são opcionais —
instale os que você pretende usar:

```bash
# Para usar Gemini:
pip install google-generativeai

# Para usar OpenAI:
pip install openai

# Para usar Anthropic:
pip install anthropic
```

## ⚙️ Configuração das chaves de API

Crie um arquivo **`.env`** na raiz do projeto com as chaves das APIs que você pretende usar
(ele **não** vai para o código nem para o Git):

```bash
# Escolha ao menos um provedor de LLM:

# Gemini (Google)
GEMINI_API_KEY=sua_chave_aqui

# OpenAI
OPENAI_API_KEY=sua_chave_aqui

# Anthropic
ANTHROPIC_API_KEY=sua_chave_aqui

# Credenciais HTTP Basic da API (obrigatórias para usar o servidor FastAPI)
API_USER=usuario
API_PASSWORD=senha

# Token do Hugging Face (necessário para o download do modelo Whisper na 1ª execução)
HF_TOKEN=hf_seu_token_aqui
```

A prioridade de detecção de LLM é: **Gemini > OpenAI > Anthropic**. A primeira chave configurada
será usada automaticamente.

## ▶️ Como usar

Prepare um arquivo de áudio (`.wav`, `.mp3`, `.m4a`, `.ogg` ou `.flac`) com uma consulta médica
de duas pessoas.

### Modo CLI

#### Passo 1 — transcrever

```bash
source .venv/bin/activate
python transcrever.py /caminho/para/consulta.wav
# saída: transcricoes/consulta.txt
```

A **primeira execução** baixa o modelo Whisper (~1 GB) e demora mais; as seguintes são rápidas
e 100% offline.

Exemplo de saída (`transcricoes/consulta.txt`):
```
[00:00:00] Bom dia. Por favor, me conte o que você está sentindo hoje.
[00:00:06] Bom dia, doutora. Estou com uma dor de cabeça há quatro dias.
[00:00:14] Entendo. Essa dor é constante ou ela vai e volta?
```

#### Passo 2 — estruturar em prontuário

```bash
# com arquivo específico:
python estruturar.py transcricoes/consulta.txt
# saída: prontuarios/consulta.json + prontuarios/consulta.txt

# sem argumento: usa o roteiro mais recente automaticamente:
python estruturar.py
```

O prontuário será salvo em dois formatos:
- `prontuarios/consulta.json` — estruturado, para integração com sistemas
- `prontuarios/consulta.txt` — legível, pronto para cópia manual

### Modo API

```bash
source .venv/bin/activate
uvicorn api:app --reload
# Disponível em http://localhost:8000
# Docs interativas: http://localhost:8000/docs
```

#### `POST /consulta`

Recebe `audio` e `template` via `multipart/form-data`, com autenticação HTTP Basic.

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `audio` | arquivo | Áudio da consulta (`.wav`, `.mp3`, `.m4a`, `.ogg`, `.flac`) |
| `template` | arquivo | Template `.txt` com seções terminadas em `:` |

Retorna `201` com:
```json
{
  "id": "2026-05-31_14-30-00_a3f7",
  "transcricao": "[00:00:00] Bom dia...",
  "prontuario": { "Subjetivo": "...", "Análise": "..." },
  "timing": { "transcricao_s": 22.1, "estruturacao_s": 10.6, "total_s": 32.7 }
}
```

#### `GET /consulta/{id}`

Retorna os dados de uma consulta já processada, lidos do banco SQLite.

```json
{
  "id": "2026-05-31_14-30-00_a3f7",
  "criado_em": "2026-05-31T14:30:32.810123",
  "transcricao": "[00:00:00] Bom dia...",
  "prontuario": { "Subjetivo": "...", "Análise": "..." },
  "template_preenchido": "Pronto atendimento\n\nSubjetivo:\n...",
  "timing": { "transcricao_s": 22.1, "estruturacao_s": 10.6, "total_s": 32.7 }
}
```

Retorna `404` se o id não existir.

## 🎙️ Dicas de gravação (1 microfone)

- **Posicione o microfone entre as duas pessoas**, a distância parecida de cada uma.
- Prefira **WAV mono, 16 kHz ou superior** (o script reconverte automaticamente se preciso).
- Reduza ruído de fundo: desligue ar-condicionado barulhento, evite salas com eco.
- O LLM infere pelo contexto quem é médico e quem é paciente; quanto mais clara a conversa, melhor.

## ⚠️ Limitações conhecidas

- A precisão da transcrição depende da qualidade do áudio. O modelo `mlx-community/whisper-large-v3-turbo`
  equilibra velocidade e qualidade em Apple Silicon.
- O prontuário gerado é um **rascunho** — o LLM segue instruções rígidas contra
  alucinação, mas revisão médica é obrigatória antes de qualquer uso clínico.
- Não há separação de falantes (diarização): o Whisper gera segmentos por horário sem rótulo de
  quem fala. A identificação de médico/paciente é feita pelo LLM com base no conteúdo — se a
  conversa for ambígua, o prontuário pode misturar os papéis.
- O banco SQLite (`consultas.db`) é local e não é replicado. Para produção, substituir por
  PostgreSQL ou equivalente.

## 📁 Estrutura do projeto

```
python-app/
├── api.py                  # Servidor FastAPI (POST /consulta, GET /consulta/{id})
├── transcrever.py          # CLI + módulo: transcrição + glossário → roteiro
├── estruturar.py           # CLI + módulo: roteiro → prontuário via LLM API
├── anonimizar.py           # Mascara PII antes do envio à LLM (LGPD)
├── glossario.py            # Correção e categorização de termos clínicos
├── glossario.json          # Terminologia médica PT-BR (versionado, sem PII)
├── templates/              # Modelos de prontuário (.txt) usados pela API
├── requirements.txt        # Dependências Python
├── test_pipeline.py        # Teste de integração do pipeline completo
├── .env                    # Chaves de API e credenciais (ignorado pelo Git)
├── .gitignore              # Ignora .env, .venv, áudios, saídas clínicas e banco
├── consultas.db            # Banco SQLite local (ignorado pelo Git)
├── transcricoes/           # <id>.txt — roteiros gerados (ignorado pelo Git)
├── prontuarios/            # <id>.json + <id>.txt — prontuários (ignorado pelo Git)
└── README.md               # Este arquivo
```
