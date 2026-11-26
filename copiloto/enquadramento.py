"""Enquadramento de produtos na Reforma Tributária: o caminho principal do MVP (Aula 04).

Fluxo: entrada (descrição + NCM) → verificação → classificação (IA) → conferência da
resposta → sugestão para o contador decidir.

A classificação pode vir de três jeitos, sempre identificados na tela:
- SIMULADA: respostas do Gemini gravadas nos testes T1 a T6 da Aula 03 (prompt V2).
- MANUAL: a pessoa cola o prompt num chat de IA e cola a resposta de volta.
- INTEGRADA: chamada automática à API do Gemini, se houver GEMINI_API_KEY.

Depois da IA, copiloto/tabela_oficial.py confere a categoria com a tabela oficial da Receita.
O processamento de um cadastro inteiro (lote) fica em copiloto/lote.py.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field

CATEGORIAS = ("ALIQUOTA_ZERO", "REDUCAO_60", "PADRAO", "REGIME_ESPECIFICO", "REVISAO_HUMANA")
CONFIANCAS = ("alta", "media", "baixa")

ROTULOS = {
    "ALIQUOTA_ZERO": "Alíquota zero (Cesta Básica Nacional, hortícolas, frutas, ovos)",
    "REDUCAO_60": "Redução de 60% nas alíquotas",
    "PADRAO": "Alíquota padrão, sem redução",
    "REGIME_ESPECIFICO": "Regime específico (ex.: combustíveis)",
    "REVISAO_HUMANA": "Precisa de revisão humana",
}

# Prompt V3 (Aula 04). Mudança em relação à V2 da Aula 03: os exemplos de cada opção foram
# conferidos nos Anexos I, VII, VIII e XV da LC 214/2025, pela base da calculadora oficial da Receita.
# A V2 punha carnes, queijos e massas em REDUCAO_60 (são Anexo I, alíquota zero) e tratava qualquer
# produto de higiene como REDUCAO_60 (o Anexo VIII é uma lista fechada de 7 itens).
REGRAS_V3 = """Você auxilia um escritório contábil a enquadrar produtos fictícios na Reforma Tributária (IBS e CBS, LC 214/2025).
Tarefa: com base na descrição e no NCM do produto, sugira um enquadramento entre as opções abaixo.
Opções:
ALIQUOTA_ZERO: Cesta Básica Nacional (Anexo I: arroz, feijão, leite, manteiga, carnes, peixes, queijos tipo mozarela/minas/prato/coalho/ricota/requeijão/provolone/parmesão, massas não cozidas nem recheadas (1902.1), café, açúcar, farinha de trigo, pão francês, sal, mate), hortícolas, frutas frescas e ovos (Anexo XV) e absorventes e tampões higiênicos (art. 147).
REDUCAO_60: alimentos do Anexo VII (ex.: mel, crustáceos, leite fermentado, óleos vegetais, pão de forma, extrato de tomate, sucos e polpas sem açúcar), somente os 7 itens de higiene e limpeza do Anexo VIII (sabonete, creme dental, escova de dentes, papel higiênico, água sanitária, sabão em barra, fraldas), medicamentos e dispositivos médicos.
PADRAO: demais produtos, sem redução (ex.: shampoo, desodorante e detergente não estão no Anexo VIII).
REGIME_ESPECIFICO: combustíveis e outros bens com regime próprio na lei.
REVISAO_HUMANA: descrição vaga, produto que mistura itens de enquadramentos diferentes, NCM ausente ou NCM que não corresponde à descrição.
Use apenas as informações do produto. Não invente características que não estão na descrição."""

PROMPT_V3 = REGRAS_V3 + """
Responda exatamente em três linhas, sem nenhum texto antes ou depois delas:
enquadramento: [uma das opções]
confianca: [alta, media ou baixa; em REVISAO_HUMANA use sempre baixa]
justificativa: [uma frase curta baseada na descrição e no NCM]
Produto: "{descricao}" | NCM: {ncm}"""


# ---------------------------------------------------------------- 1. entrada e verificação

@dataclass
class Entrada:
    descricao: str
    ncm: str  # 8 dígitos, ou "" quando não informado


@dataclass
class Verificacao:
    ok: bool
    entrada: Entrada | None = None
    erros: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def verificar_entrada(descricao: str | None, ncm: str | None) -> Verificacao:
    """Confere a entrada antes de chamar a IA. Descrição vazia ou NCM malformado param o fluxo."""
    descricao = " ".join((descricao or "").split())
    ncm_bruto = (ncm or "").strip()
    ncm_digitos = re.sub(r"[.\-\s]", "", ncm_bruto)
    erros, avisos = [], []

    if not descricao:
        erros.append("Informe a descrição do produto para continuar.")
    elif len(descricao) < 3:
        erros.append("A descrição está curta demais. Escreva o nome do produto como aparece no cadastro.")

    if ncm_digitos and not re.fullmatch(r"\d{8}", ncm_digitos):
        erros.append("O NCM deve ter 8 dígitos (ex.: 1006.30.21). Corrija ou deixe em branco.")
    elif not ncm_digitos and descricao:
        avisos.append("Sem NCM: a sugestão tende a ser REVISAO_HUMANA.")

    if erros:
        return Verificacao(ok=False, erros=erros, avisos=avisos)
    return Verificacao(ok=True, entrada=Entrada(descricao, ncm_digitos), avisos=avisos)


def formatar_ncm(ncm: str) -> str:
    return f"{ncm[:4]}.{ncm[4:6]}.{ncm[6:]}" if len(ncm) == 8 else "(vazio)"


def montar_prompt(entrada: Entrada) -> str:
    return PROMPT_V3.format(descricao=entrada.descricao, ncm=formatar_ncm(entrada.ncm))


# ---------------------------------------------------------------- 2. conferência da resposta

@dataclass
class Sugestao:
    enquadramento: str
    confianca: str
    justificativa: str
    origem: str  # SIMULADA, MANUAL ou INTEGRADA
    alertas: list[str] = field(default_factory=list)
    resposta_bruta: str = ""

    @property
    def precisa_revisao(self) -> bool:
        return self.enquadramento == "REVISAO_HUMANA"


def _campo(texto: str, nome: str) -> str | None:
    achado = re.search(rf"^\s*\**{nome}\**\s*:\s*(.+?)\s*$", texto, re.IGNORECASE | re.MULTILINE)
    return achado.group(1).strip().strip("*").strip() if achado else None


def _sem_acento(texto: str) -> str:
    return texto.translate(str.maketrans("áàâãéêíóôõúç", "aaaaeeiooouc"))


def conferir_resposta(texto: str | None, origem: str) -> Sugestao:
    """A aplicação só aceita uma categoria da lista. Qualquer outra coisa vira REVISAO_HUMANA."""
    texto = (texto or "").strip()
    if not texto:
        return Sugestao("REVISAO_HUMANA", "baixa", "A IA não devolveu resposta.", origem,
                        ["Resposta vazia: o caso foi encaminhado para revisão."], texto)

    alertas = []
    enquadramento = (_campo(texto, "enquadramento") or "").upper().replace(" ", "_")
    confianca = _sem_acento((_campo(texto, "confian[cç]a") or "").lower())
    justificativa = _campo(texto, "justificativa") or ""

    linhas = [l for l in texto.splitlines() if l.strip()]
    if len(linhas) != 3:
        alertas.append(f"A resposta veio com {len(linhas)} linhas em vez de 3; só os campos foram aproveitados.")

    if enquadramento not in CATEGORIAS:
        alertas.append(f"Categoria inesperada ({enquadramento or 'nenhuma'}): encaminhado para revisão.")
        return Sugestao("REVISAO_HUMANA", "baixa", justificativa or "Resposta fora do formato combinado.",
                        origem, alertas, texto)

    if confianca not in CONFIANCAS:
        alertas.append(f"Confiança inválida ({confianca or 'vazia'}): considerada baixa.")
        confianca = "baixa"
    if enquadramento == "REVISAO_HUMANA" and confianca != "baixa":
        alertas.append("REVISAO_HUMANA sempre leva confiança baixa (regra do prompt).")
        confianca = "baixa"
    if not justificativa:
        alertas.append("A IA não justificou: confira antes de aceitar.")

    return Sugestao(enquadramento, confianca, justificativa, origem, alertas, texto)


# ---------------------------------------------------------------- 3. classificação

class IAIndisponivel(Exception):
    """A sugestão não foi obtida (sem chave, sem rede, erro da API)."""


# Respostas reais do Gemini aos casos T1 a T6 da Aula 03 (prompt V2, 16/11/2026).
RESPOSTAS_GRAVADAS = {
    ("arroz branco tipo 1, pacote 5 kg", "10063021"):
        "enquadramento: ALIQUOTA_ZERO\nconfianca: alta\njustificativa: O produto é arroz beneficiado "
        "(NCM 1006.30.21), item expressamente incluído na Cesta Básica Nacional de Alimentos.",
    ("smartphone 128 gb, tela 6,5\"", "85171300"):
        "enquadramento: PADRAO\nconfianca: alta\njustificativa: O smartphone descrito e o NCM 8517.13.00 "
        "correspondem a aparelho eletrônico de telecomunicações, item sujeito à tributação padrão sem "
        "previsão de redução ou regime específico.",
    ("sabonete em barra 90 g", "34011190"):
        "enquadramento: REDUCAO_60\nconfianca: alta\njustificativa: Sabonete em barra (NCM 3401.11.90) é um "
        "produto de higiene pessoal, categoria contemplada com redução de 60% nas alíquotas.",
    ("kit café da manhã (café torrado, biscoito e geleia)", "21011110"):
        "enquadramento: REVISAO_HUMANA\nconfianca: baixa\njustificativa: O kit mistura itens distintos com "
        "possíveis enquadramentos tributários diferentes (café, biscoito e geleia) sob um único NCM "
        "referente apenas a extratos ou cafés solúveis.",
    ("produto diverso", ""):
        "enquadramento: REVISAO_HUMANA\nconfianca: baixa\njustificativa: A descrição \"Produto diverso\" é "
        "excessivamente vaga e o NCM está ausente, impossibilitando a classificação tributária.",
    ("shampoo anticaspa 400 ml", "10063021"):
        "enquadramento: REVISAO_HUMANA\nconfianca: baixa\njustificativa: O NCM 1006.30.21 refere-se a arroz "
        "semibranqueado ou branqueado, o que não corresponde à descrição de shampoo anticaspa.",
}

CASOS_DE_TESTE = [  # (id, tipo, descrição, NCM, esperado)
    ("T1", "Claro", "Arroz branco tipo 1, pacote 5 kg", "1006.30.21", "ALIQUOTA_ZERO"),
    ("T2", "Claro", 'Smartphone 128 GB, tela 6,5"', "8517.13.00", "PADRAO"),
    ("T3", "Claro", "Sabonete em barra 90 g", "3401.11.90", "REDUCAO_60"),
    ("T4", "Ambíguo", "Kit café da manhã (café torrado, biscoito e geleia)", "2101.11.10", "REVISAO_HUMANA"),
    ("T5", "Insuficiente", "Produto diverso", "", "REVISAO_HUMANA"),
    ("T6", "Inesperado", "Shampoo anticaspa 400 ml", "1006.30.21", "REVISAO_HUMANA"),
]


def classificar_simulado(entrada: Entrada) -> str:
    """Devolve a resposta gravada do caso de teste. Produto fora dos casos: não há simulação."""
    chave = (entrada.descricao.lower(), entrada.ncm)
    if chave not in RESPOSTAS_GRAVADAS:
        raise IAIndisponivel("Não há resposta simulada para este produto. Use um dos casos T1 a T6, "
                             "o modo manual ou o integrado.")
    return RESPOSTAS_GRAVADAS[chave]


GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"


def classificar_gemini(entrada: Entrada, chave: str | None = None, modelo: str | None = None,
                       timeout: float = 30) -> str:
    """Integração automática (opcional). Sem chave ou com erro, levanta IAIndisponivel."""
    return chamar_gemini(montar_prompt(entrada), chave, modelo, timeout)


def chamar_gemini(prompt: str, chave: str | None = None, modelo: str | None = None,
                  timeout: float = 30) -> str:
    """Envia um prompt ao Gemini e devolve o texto. Sem chave ou com erro, levanta IAIndisponivel."""
    chave = chave or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not chave:
        raise IAIndisponivel("Integração sem chave: defina GEMINI_API_KEY ou use o modo manual.")
    modelo = modelo or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    corpo = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0},
    }).encode()
    pedido = urllib.request.Request(GEMINI_URL.format(modelo=modelo), data=corpo, method="POST",
                                    headers={"Content-Type": "application/json", "x-goog-api-key": chave})
    try:
        with urllib.request.urlopen(pedido, timeout=timeout) as resposta:
            dados = json.load(resposta)
        return "".join(p.get("text", "") for p in dados["candidates"][0]["content"]["parts"])
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, ValueError) as erro:
        raise IAIndisponivel(f"A sugestão não foi obtida ({type(erro).__name__}).") from erro
