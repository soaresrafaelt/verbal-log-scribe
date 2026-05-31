#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Anonimização de PII em transcrições médicas antes do envio para LLMs em nuvem (LGPD)."""

import re
import warnings

# --- PII estruturado ---
_CPF = re.compile(r'\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b')
_TELEFONE = re.compile(r'(?<!\d)\(?\d{2}\)?\s?\d{4,5}-?\d{4}\b')
_EMAIL = re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b')
_CEP = re.compile(r'\b\d{5}-\d{3}\b')
_DATA = re.compile(r'\b\d{2}/\d{2}/\d{4}\b')
_CRM = re.compile(r'\bCRM[/\-]?\s*\d{4,6}\b', re.IGNORECASE)
_RG = re.compile(r'\bRG[:\s]+\d{1,2}\.?\d{3}\.?\d{3}-?[\dXx]?\b', re.IGNORECASE)

_SUBSTITUICOES = [
    (_CPF,      '[CPF]'),
    (_TELEFONE, '[TELEFONE]'),
    (_EMAIL,    '[EMAIL]'),
    (_CEP,      '[CEP]'),
    (_DATA,     '[DATA]'),
    (_CRM,      '[CRM]'),
    (_RG,       '[RG]'),
]

# --- Nomes por contexto (títulos e frases de apresentação comuns em consultas) ---
# O gatilho (título/frase) é case-insensitive via (?i:...); o nome exige inicial maiúscula.
_NOME_CONTEXTO = re.compile(
    r'(?i:(?:Dr\.?|Dra\.?|Doutor(?:a)?|Prof\.?)\s+'  # títulos profissionais
    r'|(?:Sr\.?|Sra\.?|Dona?|senhor(?:a)?)\s+'        # títulos de cortesia
    r'|paciente\s+'                                     # "paciente Maria"
    r'|(?:meu nome [eé]|me chamo|chamo[-\s]me)\s+'    # "meu nome é João"
    r'|(?:o\s+)?nome\s+[eé]\s+'                       # "O nome é João" / "nome é João"
    r'|(?:se\s+chama|chama[-\s]se)\s+'                # "se chama João"
    r'|(?:meu|minha|nosso|nossa)\s+'                  # "meu filho é o Ben"
     r'(?:filho|filha|esposa|esposo|marido|cônjuge|'
     r'pai|mãe|irmão|irmã|avô|avó|sogro|sogra|cunhado|cunhada)\s+'
     r'(?:[eé]\s+|se\s+chama\s+)(?:o\s+|a\s+)?'
    r')'
    r'([A-ZÁÀÂÃÉÈÊÍÌÓÒÔÕÚÙÇ][a-záàâãéèêíìóòôõúùç]+'
    r'(?:\s+[A-ZÁÀÂÃÉÈÊÍÌÓÒÔÕÚÙÇ][a-záàâãéèêíìóòôõúùç]+)*)',
)

# --- NER spaCy (opcional, complementa os casos não cobertos pelo regex) ---
_nlp = None  # None = não tentado; False = tentado e indisponível
_aviso_emitido = False


def _carregar_nlp():
    global _nlp, _aviso_emitido
    if _nlp is not None:
        return _nlp
    try:
        import spacy  # noqa: PLC0415
        _nlp = spacy.load('pt_core_news_sm')
    except (ImportError, OSError):
        if not _aviso_emitido:
            warnings.warn(
                "spaCy ou o modelo 'pt_core_news_sm' não encontrado. "
                "Nomes detectados por contexto ainda serão mascarados, mas NER está desativado. "
                "Para habilitar: pip install spacy && python -m spacy download pt_core_news_sm",
                UserWarning,
                stacklevel=3,
            )
            _aviso_emitido = True
        _nlp = False
    return _nlp


def _mascarar_nomes(texto: str) -> str:
    nomes_descobertos: set[str] = set()

    # 1. Regex contextual — coleta nomes com gatilho explícito
    def _sub_nome(m: re.Match) -> str:
        nome = m.group(1)
        nomes_descobertos.add(nome)
        return m.group(0)[: m.start(1) - m.start()] + '[NOME]'

    texto = _NOME_CONTEXTO.sub(_sub_nome, texto)

    # 2. NER spaCy para nomes sem gatilho explícito
    nlp = _carregar_nlp()
    if nlp:
        doc = nlp(texto)
        for ent in sorted(doc.ents, key=lambda e: e.start_char, reverse=True):
            if ent.label_ == 'PER' and '[NOME]' not in ent.text:
                tokens = ent.text.split()
                # Exige ≥1 token com inicial maiúscula (nomes simples são comuns em consultas)
                if len(tokens) >= 1 and all(t[0].isupper() for t in tokens):
                    nomes_descobertos.add(ent.text)
                    texto = texto[:ent.start_char] + '[NOME]' + texto[ent.end_char:]

    # 3. Segunda passagem: substitui reuso dos nomes já descobertos no restante do texto
    for nome in nomes_descobertos:
        texto = re.sub(
            r'(?<![A-ZÁÀÂÃÉÈÊÍÌÓÒÔÕÚÙÇA-Za-záàâãéèêíìóòôõúùç])' + re.escape(nome) + r'(?![A-ZÁÀÂÃÉÈÊÍÌÓÒÔÕÚÙÇA-Za-záàâãéèêíìóòôõúùç])',
            '[NOME]',
            texto,
        )
    return texto


def anonimizar(texto: str) -> str:
    """Mascara PII sensível antes do envio para LLMs em nuvem (conformidade LGPD)."""
    for padrao, marcador in _SUBSTITUICOES:
        texto = padrao.sub(marcador, texto)
    return _mascarar_nomes(texto)
