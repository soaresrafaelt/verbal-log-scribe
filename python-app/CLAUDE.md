# CLAUDE.md

Guia para o Claude Code trabalhar neste repositório. Leia antes de editar.

## O que é

Backend API (FastAPI) que transcreve consultas médicas (2 pessoas, PT-BR, 1 microfone) e estrutura
o texto em prontuário via LLM API. **Mantenha simples** — é uma POC, não produção.

## Restrição inegociável: privacidade (LGPD)

São dados de saúde sensíveis. **Transcrição e estruturação rodam localmente e offline.**
Nunca introduza código que envie áudio ou transcrição para serviços de nuvem além das APIs
de LLM já previstas (Gemini, OpenAI, Anthropic). O único acesso à rede permitido além das
APIs de LLM é o download dos pesos do Whisper na primeira execução.

**Anonimização antes do envio à LLM:** o módulo `anonimizar.py` mascara PII (CPF, telefone,
e-mail, CEP, datas, CRM, RG e nomes de pessoas) **antes** de qualquer texto chegar à API.
O arquivo local `transcricoes/<id>.txt` mantém o texto original — apenas o prompt enviado
à nuvem é anonimizado. Nomes são detectados via NER (spaCy `pt_core_news_sm`); se o modelo
não estiver instalado, os demais campos ainda são mascarados e um aviso é emitido.

## Hardware alvo

macOS Apple Silicon (M4, M3, M2), **sem GPU NVIDIA/CUDA**. Sempre use CPU:
- mlx-whisper: otimizado para Neural Engine do Apple Silicon (rodando automaticamente).
- **Nunca** adicione dependências de CUDA.

## Arquitetura

Pipeline: `audio + template → transcrição → correção glossário → anonimização → LLM → prontuário persistido`.

```
POST /consulta
  audio (WAV/MP3/M4A/OGG/FLAC) + template (.txt)
       │
       ├── Valida extensão, tamanho e template não-vazio (HTTP 422 se inválido)
       │
       ▼
  transcrever.py → gerar_roteiro_do_audio()
    - mlx-whisper (transcrição offline, Apple Silicon)
    - glossario.py (correção difflib, offline)
       │
       ├── Persiste transcricoes/<id>.txt  ← texto original, sem mascaramento
       │
       ▼
  anonimizar.py → anonimizar()            ← mascara PII antes de sair da máquina
    - Regex: CPF, telefone, e-mail, CEP, data, CRM, RG
    - NER spaCy pt_core_news_sm: nomes de pessoas → [NOME]
       │
       ▼
  estruturar.py → estruturar_com_template()
    - Detecta provedor (GEMINI > OPENAI > ANTHROPIC)
    - Envia transcrição anonimizada + seções do template para a LLM
       │
       ▼
  Persiste:
    prontuarios/<id>.json + <id>.txt
    consultas.db (SQLite) ← registro completo indexado por id
       │
       ▼
  Retorna: {id, transcricao, prontuario, timing}

GET /consulta/{id}
  ← Lê consultas.db e retorna {id, criado_em, transcricao, prontuario, template_preenchido, timing}
  ← HTTP 404 se id não existir
```

**Formato do id:** `%Y-%m-%d_%H-%M-%S_<4 hex aleatórios>` — ex.: `2026-05-31_14-30-00_a3f7`.
Garante unicidade mesmo em requisições simultâneas.

**Organização de arquivos por consulta:**
- `transcricoes/<id>.txt` — roteiro gerado pelo Whisper + glossário (texto original, não anonimizado)
- `prontuarios/<id>.json` — prontuário estruturado pela LLM
- `prontuarios/<id>.txt` — template preenchido em texto legível
- `consultas.db` — banco SQLite com todos os registros (campo `prontuario` e `timing` armazenados como JSON)

Todas as pastas/arquivos de dados estão no `.gitignore` (dados clínicos sensíveis).

**Módulos:**
- `api.py` — servidor FastAPI. Ponto de entrada principal. Autenticação HTTP Basic. Inicializa o banco SQLite.
- `transcrever.py` — transcrição via mlx-whisper + correção de glossário. Também funciona como CLI.
- `estruturar.py` — estruturação via LLM com template dinâmico. Também funciona como CLI.
  - `_chamar_llm_raw(provedor, sistema, usuario)` — função central; todos os provedores passam por aqui.
  - `estruturar_com_template(transcricao, template)` — usada pela API.
  - `estruturar_transcricao(transcricao)` — usada pelo CLI (campos fixos).
- `anonimizar.py` — mascara PII (regex + spaCy NER). Chamado por `estruturar.py` antes de qualquer envio à LLM.
- `glossario.py` + `glossario.json` — terminologia médica PT-BR. Só stdlib (`difflib`), offline.

Caminhos são montados por helpers: `transcrever.caminho_roteiro(slug)`,
`estruturar.caminho_prontuario(slug, ext)`. As pastas vêm de `DIR_TRANSCRICOES`/`DIR_PRONTUARIOS`.

## Banco de dados

`consultas.db` — SQLite local, tabela `consultas` com colunas:
`id, criado_em, transcricao, prontuario (JSON), template_preenchido, timing (JSON)`.
Inicializado automaticamente ao subir o servidor. Ignorado pelo `.gitignore`.

## Convenções de código

- **Comentários e mensagens ao usuário em português.**
- Mensagens de progresso amigáveis ("Transcrevendo...", "Estruturando...").
- Trate erros comuns com mensagens claras: arquivo não encontrado, chave de API ausente/inválida,
  formato de áudio não suportado, falha de conexão com a API.
- Configurações no topo de `transcrever.py` (constantes `MODELO_WHISPER`, `IDIOMA`).

## Comandos

```bash
# Ativar ambiente
source .venv/bin/activate

# Iniciar servidor API
uvicorn api:app --reload
# Disponível em http://localhost:8000
# Docs interativas: http://localhost:8000/docs

# CLI: Transcrever áudio
python transcrever.py /caminho/para/consulta.wav
# Saída: transcricoes/consulta.txt

# CLI: Estruturar em prontuário
python estruturar.py transcricoes/consulta.txt
# Saída: prontuarios/consulta.json + prontuarios/consulta.txt

# Checar sintaxe
python -m py_compile transcrever.py estruturar.py glossario.py api.py anonimizar.py

# Instalar modelo spaCy para mascaramento de nomes (uma vez)
python -m spacy download pt_core_news_sm
```

## Segredos

As chaves de API ficam em `.env`, lido via `python-dotenv`.
**Nunca** coloque as chaves no código, em logs ou em mensagens.

```
GEMINI_API_KEY=...       # prioridade 1
OPENAI_API_KEY=...       # prioridade 2
ANTHROPIC_API_KEY=...    # prioridade 3
API_USER=...             # autenticação HTTP Basic da API
API_PASSWORD=...         # autenticação HTTP Basic da API
HF_TOKEN=hf_...          # token Hugging Face (download do modelo Whisper)
```

`.env`, `.venv/`, `transcricoes/`, `prontuarios/` e `consultas.db` são ignorados pelo `.gitignore`.
