#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Glossario de termos tecnicos medicos (PT-BR) usado em duas frentes:

  1. CORRECAO pos-transcricao: a transcricao automatica costuma errar a grafia
     de termos clinicos (ex.: "dispineia" -> "dispneia"). Comparamos cada
     palavra com o glossario por similaridade (difflib, biblioteca padrao) e
     corrigimos os casos bem proximos. E conservador de proposito: so troca
     quando a semelhanca e alta, para nao corromper o texto comum.

  2. CATEGORIZACAO: detecta quais termos do glossario aparecem na transcricao e
     os agrupa por categoria (sintomas, medicamentos, exames...), ajudando a
     classificar do que medico e paciente falaram.

Tudo offline e sem dependencias novas (so 'difflib', 're', 'unicodedata', 'json'
da biblioteca padrao). O glossario fica em 'glossario.json' (editavel; NAO contem
dados de paciente, pode ser versionado).
"""

import difflib
import json
import os
import re
import unicodedata

DIR_BASE = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_GLOSSARIO = os.path.join(DIR_BASE, "glossario.json")

# Limiares da correcao (conservadores: melhor nao corrigir do que corrigir errado).
MIN_SIMILARIDADE = 0.86  # 0..1; quao parecida a palavra precisa ser de um termo
MIN_TAMANHO = 5          # so tenta correcao "fuzzy" em palavras com 5+ letras

# Rotulos amigaveis das categorias (chave do JSON -> texto exibido ao usuario).
CATEGORIAS_ROTULOS = {
    "sintomas": "Sintomas e queixas",
    "doencas_condicoes": "Doencas e condicoes",
    "medicamentos": "Medicamentos",
    "exames": "Exames",
    "procedimentos_condutas": "Procedimentos e condutas",
    "anatomia": "Anatomia",
    "sinais_vitais": "Sinais vitais e medidas",
}

# Palavra = sequencia de letras (inclui acentuadas). Pontuacao/numeros/espacos
# ficam de fora e sao preservados durante a correcao.
_PADRAO_PALAVRA = re.compile(r"[A-Za-zÀ-ÿ]{2,}")

# Caches preenchidos na 1a chamada (o JSON e lido uma unica vez).
_glossario = None        # dict categoria -> lista de termos
_termos_simples = None    # dict termo-normalizado -> termo canonico (so 1 palavra)


def _normalizar(texto: str) -> str:
    """Minusculas e sem acentos, para comparar/buscar sem depender de grafia."""
    nfkd = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def carregar_glossario() -> dict:
    """Le 'glossario.json' (uma vez) e devolve {categoria: [termos]}.

    Ignora chaves de metadados (as que comecam com '_', como '_sobre').
    """
    global _glossario
    if _glossario is None:
        try:
            with open(ARQUIVO_GLOSSARIO, "r", encoding="utf-8") as arq:
                dados = json.load(arq)
        except (FileNotFoundError, json.JSONDecodeError):
            dados = {}
        _glossario = {
            cat: termos for cat, termos in dados.items()
            if not cat.startswith("_") and isinstance(termos, list)
        }
    return _glossario


def _mapa_termos_simples() -> dict:
    """Mapa termo-normalizado -> termo canonico, so para termos de UMA palavra.

    Termos compostos ("dor toracica", "raio-x") nao entram na correcao palavra a
    palavra; eles continuam valendo na categorizacao.
    """
    global _termos_simples
    if _termos_simples is None:
        _termos_simples = {}
        for termos in carregar_glossario().values():
            for termo in termos:
                if " " in termo or "-" in termo:
                    continue
                _termos_simples[_normalizar(termo)] = termo
    return _termos_simples


def _ajustar_caixa(canonico: str, original: str) -> str:
    """Aplica ao termo corrigido a capitalizacao da palavra original."""
    if original.isupper():
        return canonico.upper()
    if original[:1].isupper():
        return canonico[:1].upper() + canonico[1:]
    return canonico


def corrigir_texto(texto: str):
    """Corrige a grafia de termos medicos no texto, de forma conservadora.

    Devolve (texto_corrigido, correcoes), onde 'correcoes' e a lista de pares
    (original, corrigido) que foram efetivamente trocados. Pontuacao, numeros,
    espacos e quebras de linha sao preservados.
    """
    termos = _mapa_termos_simples()
    correcoes = []

    def trocar(m):
        palavra = m.group(0)
        norm = _normalizar(palavra)
        canonico = termos.get(norm)  # grafia exata (acerta so acentuacao, p.ex.)
        if canonico is None:
            # Palavra desconhecida: tenta o termo mais parecido (so se for longa).
            if len(norm) < MIN_TAMANHO:
                return palavra
            candidatos = difflib.get_close_matches(
                norm, termos.keys(), n=1, cutoff=MIN_SIMILARIDADE
            )
            if not candidatos:
                return palavra
            canonico = termos[candidatos[0]]
        ajustado = _ajustar_caixa(canonico, palavra)
        if ajustado != palavra:
            correcoes.append((palavra, ajustado))
        return ajustado

    return _PADRAO_PALAVRA.sub(trocar, texto), correcoes


def categorizar_texto(texto: str) -> dict:
    """Detecta os termos do glossario presentes no texto, agrupados por categoria.

    Devolve {categoria: [termos encontrados]} (apenas categorias com ocorrencias),
    comparando sem distinguir maiusculas/acentos. Termos compostos tambem contam.
    """
    norm_texto = _normalizar(texto)
    resultado = {}
    for categoria, termos in carregar_glossario().items():
        achados = set()
        for termo in termos:
            padrao = r"\b" + re.escape(_normalizar(termo)) + r"\b"
            if re.search(padrao, norm_texto):
                achados.add(termo)
        if achados:
            resultado[categoria] = sorted(achados)
    return resultado


def formatar_categorias(categorias: dict) -> str:
    """Versao em texto da categorizacao, para o CLI."""
    if not categorias:
        return "Nenhum termo do glossario foi identificado."
    linhas = []
    for categoria, termos in categorias.items():
        rotulo = CATEGORIAS_ROTULOS.get(categoria, categoria)
        linhas.append(f"  {rotulo}: {', '.join(termos)}")
    return "\n".join(linhas)
