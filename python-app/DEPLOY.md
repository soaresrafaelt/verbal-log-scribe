# Manual de Deploy e Operação — Verbal Log Scribe

> **Versão:** POC local (macOS Apple Silicon)
> **Para DevOps:** as seções marcadas com `[MIGRAÇÃO]` detalham o que precisa mudar ao mover para AWS ou outro provedor de nuvem.

---

## Índice

1. [Visão geral do sistema](#1-visão-geral-do-sistema)
2. [Pré-requisitos](#2-pré-requisitos)
3. [Instalação](#3-instalação)
4. [Configuração](#4-configuração)
5. [Primeiro boot (download do modelo)](#5-primeiro-boot-download-do-modelo)
6. [Subindo o serviço](#6-subindo-o-serviço)
7. [Verificando a saúde do serviço](#7-verificando-a-saúde-do-serviço)
8. [Referência da API](#8-referência-da-api)
9. [Formato do template de prontuário](#9-formato-do-template-de-prontuário)
10. [Persistência de dados](#10-persistência-de-dados)
11. [Rodando os testes](#11-rodando-os-testes)
12. [Uso via CLI (sem API)](#12-uso-via-cli-sem-api)
13. [Variáveis de ambiente — referência completa](#13-variáveis-de-ambiente--referência-completa)
14. [Notas de privacidade (LGPD)](#14-notas-de-privacidade-lgpd)
15. [Guia de migração para AWS](#15-guia-de-migração-para-aws)
16. [Solução de problemas](#16-solução-de-problemas)

---

## 1. Visão geral do sistema

O serviço recebe um arquivo de áudio de consulta médica mais um template de prontuário e executa o pipeline abaixo de forma totalmente **local** (exceto a chamada ao LLM, que recebe texto anonimizado):

```
[Cliente]
   │
   │  POST /consulta  (áudio + template)
   ▼
[API — FastAPI/uvicorn]
   │
   ├─► transcrever.py
   │     mlx-whisper (Apple Silicon, offline)
   │     glossario.py (correção fuzzy, offline)
   │
   ├─► anonimizar.py
   │     Regex: CPF, telefone, e-mail, CEP, data, CRM, RG
   │     NER spaCy: nomes de pessoas (opcional)
   │
   ├─► estruturar.py ──► LLM API (Gemini / OpenAI / Anthropic)
   │     Envia: transcrição anonimizada + seções do template
   │     Recebe: prontuário preenchido (JSON com Structured Outputs)
   │
   └─► Persistência
         transcricoes/<id>.txt   (texto original, não anonimizado)
         prontuarios/<id>.json   (prontuário estruturado)
         prontuarios/<id>.txt    (template preenchido em texto legível)
         consultas.db            (SQLite — registro indexado por id)
   │
   │  HTTP 201 + {id, transcricao, prontuario, timing}
   ▼
[Cliente]
```

**ID de cada consulta:** `AAAA-MM-DD_HH-MM-SS_xxxx` (timestamp + 4 hex aleatórios).
Exemplo: `2026-05-31_14-30-00_a3f7`

---

## 2. Pré-requisitos

### Hardware

| Requisito | Valor |
|-----------|-------|
| Processador | Apple Silicon (M2, M3 ou M4) |
| RAM mínima | 8 GB (recomendado 16 GB) |
| Espaço em disco | ~2 GB para o modelo Whisper + dados da aplicação |

> **[MIGRAÇÃO]** O componente `mlx-whisper` é exclusivo do Apple Silicon (framework MLX da Apple). Em qualquer outra plataforma (AWS EC2, Linux x86), o módulo de transcrição precisa ser substituído — ver seção 15.

### Sistema operacional

- macOS 13 (Ventura) ou superior com Apple Silicon

### Dependências de sistema

```bash
# Homebrew (se não tiver instalado):
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# FFmpeg (decodifica áudio) + Python 3.12:
brew install ffmpeg python@3.12
```

Verificar versões após a instalação:

```bash
ffmpeg -version | head -1   # deve mostrar "ffmpeg version 7.x" ou superior
python3.12 --version        # deve mostrar "Python 3.12.x"
```

### Contas e chaves de API

Você precisa de chave em **ao menos um** dos provedores abaixo:

| Provedor | Uso | Observação |
|----------|-----|------------|
| **Google Gemini** | LLM (prioridade 1) | Tier gratuito disponível |
| **OpenAI** | LLM (prioridade 2) | Pago por uso |
| **Anthropic** | LLM (prioridade 3) | Pago por uso |
| **Hugging Face** | Download do modelo Whisper (1 vez) | Conta gratuita |

---

## 3. Instalação

Execute os comandos abaixo a partir do diretório `python-app/`:

```bash
# Clone (se ainda não fez):
git clone <url-do-repositorio>
cd verbal-log-scribe/python-app

# Cria o ambiente virtual isolado:
python3.12 -m venv .venv
source .venv/bin/activate

# Atualiza o pip e instala todas as dependências:
pip install --upgrade pip
pip install -r requirements.txt

# Instala o modelo spaCy para mascaramento de nomes por NER (opcional, mas recomendado):
python -m spacy download pt_core_news_sm
```

> Se o modelo spaCy não for instalado, o sistema continua funcionando — CPF, telefone, e-mail, CEP, datas, CRM e RG continuam sendo mascarados. Apenas o mascaramento de nomes de pessoas via NER fica desativado, e um aviso é emitido nos logs.

---

## 4. Configuração

Crie o arquivo `.env` dentro de `python-app/` (ele é ignorado pelo Git):

```bash
cp .env.exemplo .env   # se existir um exemplo
# ou crie do zero:
nano .env
```

Conteúdo do `.env`:

```dotenv
# ── LLM: configure ao menos um provedor ──────────────────────────────
# Prioridade de detecção automática: GEMINI > OPENAI > ANTHROPIC

GEMINI_API_KEY=AIzaSy...          # Google AI Studio → https://aistudio.google.com/
OPENAI_API_KEY=sk-proj-...        # OpenAI Platform → https://platform.openai.com/
ANTHROPIC_API_KEY=sk-ant-...      # Anthropic Console → https://console.anthropic.com/

# ── API HTTP Basic Auth (obrigatório para usar o servidor) ────────────
API_USER=admin
API_PASSWORD=senha-forte-aqui

# ── Hugging Face (download do modelo Whisper na 1ª execução) ─────────
HF_TOKEN=hf_...                   # https://huggingface.co/settings/tokens
```

> **[MIGRAÇÃO]** Em produção (AWS, GCP, etc.), nunca coloque o `.env` no sistema de arquivos do servidor. Use AWS Secrets Manager, Parameter Store ou variáveis de ambiente injetadas pelo orquestrador de containers (ECS task definition, Kubernetes Secret).

---

## 5. Primeiro boot (download do modelo)

Na primeira execução, o mlx-whisper baixa o modelo `whisper-large-v3-turbo` (~800 MB) do Hugging Face. O download ocorre automaticamente ao receber a primeira requisição, ou pode ser antecipado com:

```bash
source .venv/bin/activate
python -c "
import mlx_whisper
mlx_whisper.transcribe('audios/consulta_teste.wav',
    path_or_hf_repo='mlx-community/whisper-large-v3-turbo',
    language='pt', verbose=False)
print('Modelo pronto.')
"
```

Isso garante que o modelo esteja em cache antes de subir o servidor em produção, evitando timeout na primeira requisição real.

O modelo fica em cache em `~/.cache/huggingface/hub/` e não precisa ser baixado novamente.

---

## 6. Subindo o serviço

### Desenvolvimento (com reload automático)

```bash
source .venv/bin/activate
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

### Produção (sem reload, com múltiplos workers)

```bash
source .venv/bin/activate
uvicorn api:app --host 0.0.0.0 --port 8000 --workers 2
```

> **Atenção sobre workers:** cada worker carrega o modelo Whisper em memória (~1 GB). Com 2 workers em uma máquina de 16 GB, o uso de RAM será ~2 GB apenas para os modelos. Não use mais workers do que a RAM permitir.

### Como serviço do sistema (launchd no macOS)

Crie `/Library/LaunchDaemons/br.com.verbal-log-scribe.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>br.com.verbal-log-scribe</string>
    <key>ProgramArguments</key>
    <array>
        <string>/caminho/para/python-app/.venv/bin/uvicorn</string>
        <string>api:app</string>
        <string>--host</string><string>0.0.0.0</string>
        <string>--port</string><string>8000</string>
        <string>--workers</string><string>2</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/caminho/para/python-app</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/var/log/verbal-log-scribe.log</string>
    <key>StandardErrorPath</key>
    <string>/var/log/verbal-log-scribe-error.log</string>
</dict>
</plist>
```

```bash
sudo launchctl load /Library/LaunchDaemons/br.com.verbal-log-scribe.plist
sudo launchctl start br.com.verbal-log-scribe
```

> **[MIGRAÇÃO]** Em Linux (AWS EC2, containers), use `systemd` ou o entrypoint do container Docker. Ver seção 15.

---

## 7. Verificando a saúde do serviço

```bash
# Documentação interativa (confirma que o servidor está no ar):
curl http://localhost:8000/docs

# Ping leve (retorna 422 pois não enviou corpo — mas confirma que a API responde):
curl -u admin:senha -X POST http://localhost:8000/consulta
# Esperado: HTTP 422 com detalhe sobre campo ausente

# Teste de autenticação errada:
curl -u errado:errado http://localhost:8000/consulta/qualquer-id
# Esperado: HTTP 401
```

A documentação interativa (Swagger UI) fica disponível em:
`http://localhost:8000/docs`

---

## 8. Referência da API

### Autenticação

Todas as rotas usam **HTTP Basic Authentication**.
Credenciais configuradas em `API_USER` e `API_PASSWORD` no `.env`.

Exemplo com curl:
```bash
curl -u "$API_USER:$API_PASSWORD" ...
```

### POST /consulta

Processa uma consulta médica completa.

**Content-Type:** `multipart/form-data`

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `audio` | arquivo | Sim | Áudio da consulta. Extensões aceitas: `.wav`, `.mp3`, `.m4a`, `.ogg`, `.flac` |
| `template` | arquivo | Sim | Template de prontuário em texto (`.txt`). Ver seção 9. |

**Resposta de sucesso — HTTP 201:**

```json
{
  "id": "2026-05-31_14-30-00_a3f7",
  "transcricao": "[00:00:00] Bom dia. Por favor, me conte...\n[00:00:06] Bom dia, doutora...",
  "prontuario": {
    "Subjetivo": "Cefaleia intensa há 15 dias, em aperto, com irradiação occipito-frontal.",
    "Exame físico": "PA: 150x95 mmHg.",
    "Análise": "Suspeita de HAS. Provável cefaleia hipertensiva.",
    "Prescrição": "Losartana 50 mg 1x/dia pela manhã. Solicita hemograma, colesterol, glicemia, ECG."
  },
  "timing": {
    "transcricao_s": 21.05,
    "estruturacao_s": 23.52,
    "total_s": 44.57
  }
}
```

**Respostas de erro:**

| Código | Causa |
|--------|-------|
| 401 | Credenciais inválidas |
| 422 | Formato de áudio não suportado, arquivo vazio ou template vazio |
| 503 | Falha na API do LLM (chave inválida, quota esgotada, etc.) |
| 500 | Erro interno inesperado |

**Exemplo com curl:**

```bash
curl -u admin:senha \
  -X POST http://localhost:8000/consulta \
  -F "audio=@/caminho/para/consulta.wav" \
  -F "template=@templates/topicos_pronto_atendimento.txt"
```

**Exemplo com Python (requests):**

```python
import requests

with open("consulta.wav", "rb") as f_audio, open("template.txt", "rb") as f_tpl:
    resp = requests.post(
        "http://localhost:8000/consulta",
        files={
            "audio":    ("consulta.wav", f_audio, "audio/wav"),
            "template": ("template.txt", f_tpl,   "text/plain"),
        },
        auth=("admin", "senha"),
        timeout=300,   # transcrição + LLM pode levar até ~2 min para áudios longos
    )

dados = resp.json()
print(dados["prontuario"])
```

---

### GET /consulta/{id}

Recupera uma consulta já processada pelo seu ID.

**Resposta de sucesso — HTTP 200:**

```json
{
  "id": "2026-05-31_14-30-00_a3f7",
  "criado_em": "2026-05-31T14:30:32.810123",
  "transcricao": "[00:00:00] Bom dia...",
  "prontuario": { "Subjetivo": "...", "Análise": "..." },
  "template_preenchido": "Pronto atendimento\n\nSubjetivo:\nCefaleia intensa...",
  "timing": { "transcricao_s": 21.05, "estruturacao_s": 23.52, "total_s": 44.57 }
}
```

**Respostas de erro:**

| Código | Causa |
|--------|-------|
| 401 | Credenciais inválidas |
| 404 | ID não encontrado no banco |

---

## 9. Formato do template de prontuário

O template é um arquivo `.txt` onde cada **linha terminada em `:`** define uma seção do prontuário. O LLM preenche cada seção com base no que foi verbalizado na consulta.

**Exemplo** (`templates/topicos_pronto_atendimento.txt`):

```
Pronto atendimento

História mórbida pregressa:
Medicações de uso contínuo:
Alergias:

Subjetivo:

Exame físico:

Análise:

Prescrição:
```

**Regras:**
- Linhas terminadas em `:` → seções do prontuário (nome da seção é o texto antes dos `:`).
- Linhas sem `:` → ignoradas pelo processador de seções (podem ser usadas como cabeçalhos ou separadores visuais).
- Nomes de seções com espaços e acentos são suportados.
- A ordem das seções é preservada no retorno.

Para criar um template SOAP, basta usar:

```
SOAP

Subjetivo:
Objetivo:
Avaliação:
Plano:
```

---

## 10. Persistência de dados

### Estrutura de diretórios

```
python-app/
├── transcricoes/
│   └── 2026-05-31_14-30-00_a3f7.txt   ← transcrição original (não anonimizada)
├── prontuarios/
│   ├── 2026-05-31_14-30-00_a3f7.json  ← prontuário estruturado (JSON)
│   └── 2026-05-31_14-30-00_a3f7.txt   ← template preenchido (texto legível)
└── consultas.db                         ← banco SQLite com todos os registros
```

### Banco SQLite — tabela `consultas`

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | TEXT PK | Identificador único da consulta |
| `criado_em` | TEXT | Timestamp ISO 8601 da criação |
| `transcricao` | TEXT | Texto bruto da transcrição |
| `prontuario` | TEXT | JSON com campos preenchidos pelo LLM |
| `template_preenchido` | TEXT | Template com seções preenchidas em texto plano |
| `timing` | TEXT | JSON com tempos de cada etapa (segundos) |

**Consultar diretamente com sqlite3:**

```bash
sqlite3 consultas.db "SELECT id, criado_em FROM consultas ORDER BY criado_em DESC LIMIT 10;"
```

> **[MIGRAÇÃO]** Para produção, substituir o SQLite por PostgreSQL (AWS RDS) ou outro banco gerenciado. O mapeamento de colunas é direto; basta trocar as chamadas `sqlite3.connect()` no `api.py` por um ORM (SQLAlchemy + psycopg2) ou um driver equivalente.

---

## 11. Rodando os testes

O teste de integração (`test_pipeline.py`) executa o pipeline completo:
1. Sobe o servidor na porta 8001
2. Envia o áudio de teste com autenticação real
3. Verifica HTTP 201, presença dos campos, arquivos salvos e consistência do GET

**Pré-condições:**
- `.env` configurado com pelo menos uma chave de LLM e `API_USER`/`API_PASSWORD`
- `audios/consulta_teste.wav` presente
- `templates/topicos_pronto_atendimento.txt` presente

```bash
source .venv/bin/activate
python test_pipeline.py
```

Saída esperada (todos os 15 checks devem aparecer com `✓ [PASSOU]`):

```
============================================================
  Resultado final
============================================================
  Todos os testes PASSARAM.
```

O tempo total esperado é de **30 a 90 segundos**, dependendo do tamanho do áudio e da latência do LLM.

---

## 12. Uso via CLI (sem API)

O pipeline também pode ser executado passo a passo via linha de comando, sem subir o servidor:

```bash
source .venv/bin/activate

# Passo 1: Transcrever o áudio
python transcrever.py /caminho/para/consulta.wav
# Saída: transcricoes/consulta.txt

# Passo 2: Estruturar em prontuário (usa o arquivo mais recente da pasta)
python estruturar.py
# Saída: prontuarios/consulta.json + prontuarios/consulta.txt

# Ou especificando o arquivo:
python estruturar.py transcricoes/consulta.txt
```

---

## 13. Variáveis de ambiente — referência completa

| Variável | Obrigatória | Descrição |
|----------|-------------|-----------|
| `GEMINI_API_KEY` | Uma das três | Chave da Google Gemini API. Prioridade 1. |
| `OPENAI_API_KEY` | Uma das três | Chave da OpenAI API. Prioridade 2. |
| `ANTHROPIC_API_KEY` | Uma das três | Chave da Anthropic API. Prioridade 3. |
| `API_USER` | Sim (para API) | Usuário para autenticação HTTP Basic. |
| `API_PASSWORD` | Sim (para API) | Senha para autenticação HTTP Basic. |
| `HF_TOKEN` | Sim (1ª execução) | Token do Hugging Face para download do modelo Whisper. Pode ser removido após o primeiro boot. |

Todas as variáveis são lidas via `python-dotenv` do arquivo `.env` na raiz de `python-app/`. Variáveis de ambiente do sistema operacional também são lidas (e têm prioridade sobre o `.env`).

---

## 14. Notas de privacidade (LGPD)

Este serviço processa **dados sensíveis de saúde**. As decisões de arquitetura que garantem conformidade são:

1. **Transcrição 100% offline:** o áudio nunca sai da máquina. O `mlx-whisper` roda localmente no Neural Engine do Apple Silicon.

2. **Anonimização antes da nuvem:** o módulo `anonimizar.py` mascara CPF, telefone, e-mail, CEP, datas, CRM, RG e nomes de pessoas (via regex + NER spaCy) antes de qualquer texto chegar à API do LLM.

3. **Texto original fica local:** `transcricoes/<id>.txt` armazena a transcrição **original** (não anonimizada) apenas na máquina local. Nunca é enviada para serviços externos.

4. **Dados clínicos ignorados pelo Git:** `.gitignore` exclui `transcricoes/`, `prontuarios/`, `consultas.db` e `.env`.

> **[MIGRAÇÃO]** Ao mover para nuvem, o áudio e a transcrição não anonimizada **nunca** devem ser enviados a serviços de terceiros. Isso implica que o componente de transcrição deve continuar rodando em infraestrutura própria (bare-metal ou VM dedicada com GPU), não em serviços gerenciados de STT como Google Speech-to-Text ou AWS Transcribe.

---

## 15. Guia de migração para AWS

Esta seção mapeia cada componente atual para seu equivalente em AWS (ou outra nuvem), indicando o que precisa ser reescrito ou substituído.

### Mapa de componentes

| Componente atual | Equivalente AWS | Nível de esforço |
|------------------|-----------------|------------------|
| `mlx-whisper` (Apple Silicon) | Whisper open-source em EC2 com GPU (g4dn, g5) | **Alto** — requer reescrita do `transcrever.py` |
| `uvicorn api:app` (processo local) | Container Docker no ECS Fargate ou EC2 | **Médio** |
| `consultas.db` (SQLite) | Amazon RDS (PostgreSQL) | **Médio** |
| `transcricoes/` e `prontuarios/` (disco local) | Amazon S3 + EFS ou RDS para blobs | **Médio** |
| `.env` (arquivo local) | AWS Secrets Manager ou Parameter Store | **Baixo** |
| Autenticação HTTP Basic | Amazon Cognito ou API Gateway + Authorizer | **Médio** |
| Logs de aplicação | Amazon CloudWatch Logs | **Baixo** |

### Passo a passo para containerização (Docker)

**1. Criar `Dockerfile`:**

```dockerfile
FROM python:3.12-slim

# Instalar ffmpeg
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m spacy download pt_core_news_sm

COPY . .

# Pré-baixar o modelo Whisper durante o build (evita cold start)
# Requer HF_TOKEN como build arg ou secret
ARG HF_TOKEN
RUN python -c "
import os; os.environ['HF_TOKEN'] = '${HF_TOKEN}'
import mlx_whisper
" || true   # falha silenciosa se não tiver GPU Apple Silicon no CI

EXPOSE 8000
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

**2. Build e execução local:**

```bash
docker build -t verbal-log-scribe .
docker run -p 8000:8000 --env-file .env verbal-log-scribe
```

> **Atenção:** `mlx-whisper` usa o framework MLX, que só compila e roda em Apple Silicon. Em containers x86 (AWS Fargate, EC2 padrão), o `transcrever.py` precisa ser reescrito usando `openai-whisper` (CPU, mais lento) ou `faster-whisper` (CPU/GPU via CTranslate2).

### Substituindo o `transcrever.py` para rodar em x86/GPU

Troque a função `transcrever_audio` em `transcrever.py`:

```python
# Versão para x86/GPU (substitui mlx_whisper)
def transcrever_audio(caminho_audio: str, progresso=print):
    import faster_whisper  # pip install faster-whisper
    model = faster_whisper.WhisperModel(
        "large-v3",
        device="cuda",          # "cpu" se não houver GPU
        compute_type="float16", # "int8" para CPU
    )
    progresso("Transcrevendo o áudio...")
    segments_raw, _ = model.transcribe(caminho_audio, language="pt")

    NO_SPEECH_THRESHOLD = 0.6
    segmentos = []
    for seg in segments_raw:
        if seg.text.strip() and seg.no_speech_prob < NO_SPEECH_THRESHOLD:
            segmentos.append({"inicio": seg.start, "texto": seg.text.strip()})

    return _cortar_alucinacoes(segmentos)
```

Adicionar ao `requirements.txt` (versão Linux/x86):
```
faster-whisper>=1.0.0
```

Remover do `requirements.txt`:
```
mlx-whisper
```

### Substituindo o SQLite por PostgreSQL

No `api.py`, substituir as chamadas `sqlite3.connect()` por uma conexão gerenciada via SQLAlchemy:

```python
# pip install sqlalchemy psycopg2-binary
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL")  # ex.: postgresql://user:pass@host:5432/db
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# Inicialização:
with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS consultas (
            id TEXT PRIMARY KEY,
            criado_em TEXT NOT NULL,
            transcricao TEXT NOT NULL,
            prontuario TEXT NOT NULL,
            template_preenchido TEXT NOT NULL,
            timing TEXT NOT NULL
        )
    """))
    conn.commit()
```

### Substituindo o armazenamento de arquivos por S3

Os arquivos `transcricoes/<id>.txt`, `prontuarios/<id>.json` e `prontuarios/<id>.txt` são salvos em disco no `api.py`. Para usar S3:

```python
# pip install boto3
import boto3

s3 = boto3.client("s3")
BUCKET = os.getenv("S3_BUCKET")

# Salvar transcrição:
s3.put_object(Bucket=BUCKET, Key=f"transcricoes/{consulta_id}.txt", Body=transcricao.encode())

# Salvar prontuário JSON:
s3.put_object(
    Bucket=BUCKET,
    Key=f"prontuarios/{consulta_id}.json",
    Body=json.dumps(prontuario, ensure_ascii=False).encode(),
    ContentType="application/json",
)
```

> **Atenção LGPD:** o bucket S3 com transcrições não anonimizadas deve ter criptografia em repouso (SSE-S3 ou SSE-KMS), acesso privado (Block Public Access ativado) e política de retenção conforme a política de privacidade do produto.

### Variáveis de ambiente no AWS (Secrets Manager)

```bash
# Criar secret:
aws secretsmanager create-secret \
  --name verbal-log-scribe/prod \
  --secret-string '{
    "GEMINI_API_KEY": "...",
    "API_USER": "...",
    "API_PASSWORD": "...",
    "DATABASE_URL": "postgresql://...",
    "S3_BUCKET": "..."
  }'

# Injetar no ECS Task Definition via secretsOptions ou como variáveis de ambiente.
```

---

## 16. Solução de problemas

### Servidor não responde

```bash
# Verificar se o processo está rodando:
lsof -i :8000

# Verificar logs:
tail -f /var/log/verbal-log-scribe-error.log
```

### HTTP 503 — "Erro na API do Gemini"

- Verifique se `GEMINI_API_KEY` está correto no `.env`.
- Verifique se a quota diária/mensal não foi esgotada no Google AI Studio.
- Se o erro for `additionalProperties` no schema, o cliente `google-generativeai` está desatualizado — atualize com `pip install --upgrade google-generativeai`.

### HTTP 422 — "Formato de áudio não suportado"

O arquivo enviado não tem extensão reconhecida (`.wav`, `.mp3`, `.m4a`, `.ogg`, `.flac`). Certifique-se de que o `filename` do upload inclui a extensão correta.

### Transcrição retorna string vazia ou "Nenhuma fala reconhecida"

- Verifique se o `ffmpeg` está instalado: `ffmpeg -version`
- Verifique a qualidade do áudio: volume baixo, muito ruído de fundo ou fala em idioma diferente do PT-BR podem resultar em transcrições vazias.
- Teste com o arquivo `audios/consulta_teste.wav` para isolar se o problema é no áudio ou no código.

### Modelo Whisper não encontrado na primeira execução

- Verifique se `HF_TOKEN` está configurado no `.env`.
- Verifique conexão com a internet na primeira execução.
- O modelo fica em cache em `~/.cache/huggingface/hub/`. Verifique se há espaço em disco.

### spaCy — aviso "pt_core_news_sm não encontrado"

O aviso é informativo — o sistema continua funcionando. Para ativar o NER:

```bash
source .venv/bin/activate
python -m spacy download pt_core_news_sm
```

### Banco de dados corrompido

```bash
# Verificar integridade:
sqlite3 consultas.db "PRAGMA integrity_check;"

# Fazer backup antes de qualquer operação destrutiva:
cp consultas.db consultas.db.bak

# Recriar a tabela (perde dados):
sqlite3 consultas.db "DROP TABLE IF EXISTS consultas;"
# O banco será recriado automaticamente ao subir o servidor.
```
