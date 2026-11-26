"""Conferência da sugestão da IA com a tabela oficial da Receita (NCM por anexo da LC 214/2025).

A tabela vem da calculadora oficial (dados/receita/, gerada por scripts/tabela_receita.py). Ela diz
quais NCMs PODEM ter redução de alíquota e em qual anexo. Ela não decide sozinha: o mesmo NCM pode
estar num anexo só para um uso específico (ex.: celular como dispositivo de acessibilidade).
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path

from copiloto.enquadramento import Sugestao

PASTA = Path(__file__).resolve().parent.parent / "dados" / "receita"
CATEGORIA_POR_REDUCAO = {100.0: "ALIQUOTA_ZERO", 60.0: "REDUCAO_60"}
CCLASSTRIB_PADRAO = ("000001", "Situações tributadas integralmente pelo IBS e CBS.")

# Tratamentos que dependem de quem compra ou da operação, e não só do produto. No recorte do MVP
# (distribuidora vendendo para empresas e consumidores) eles não são atribuídos automaticamente.
DEPENDE_DA_OPERACAO = {
    "200005": "dispositivo médico vendido a órgão público ou entidade de saúde imune",
    "200008": "dispositivo de acessibilidade comprado por órgão público",
    "200011": "nutrição enteral ou parenteral comprada por órgão público",
    "200038": "insumo agropecuário vendido a produtor rural",
    "515001": "insumo agropecuário com diferimento",
    "200039": "produção artística, cultural ou de eventos",
    "200043": "bens e serviços de soberania vendidos à administração pública",
    "200044": "segurança da informação e cibernética",
}

# NCMs em que vale um tratamento que a calculadora não liga a NCM (cClassTrib definido pelo produto,
# não pela lista de NCM): a tabela sozinha não basta, então esses itens sempre passam pelo contador.
FORA_DA_TABELA = {
    "9619": "absorventes e tampões higiênicos têm alíquota zero (art. 147, cClassTrib 200013) e dividem o NCM "
            "com as fraldas (Anexo VIII); a tabela por NCM não separa os dois",
    "30": "medicamentos registrados na Anvisa (cClassTrib 200009 ou 200032) não estão na tabela por NCM",
}


def fora_da_tabela(ncm: str) -> str | None:
    """Aviso quando o NCM pode ter um tratamento que a tabela por NCM não mostra."""
    return next((aviso for prefixo, aviso in FORA_DA_TABELA.items() if ncm.startswith(prefixo)), None) if ncm else None


@dataclass(frozen=True)
class Tratamento:
    cclasstrib: str
    descricao: str
    anexo: str
    reducao_pct: float
    ncm_prefixo: str

    @property
    def categoria(self) -> str | None:
        return CATEGORIA_POR_REDUCAO.get(self.reducao_pct)

    @property
    def depende_da_operacao(self) -> bool:
        return self.cclasstrib in DEPENDE_DA_OPERACAO


@dataclass
class Conferencia:
    situacao: str  # CONFERE, DIVERGE, ATENCAO, INFORMATIVO, NAO_CONFERIDO
    mensagem: str
    candidatos: list[Tratamento] = field(default_factory=list)


@lru_cache(maxsize=1)
def _carregar(pasta: Path = PASTA):
    with open(pasta / "ncm_tratamento.csv", encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))
    excecoes: dict[str, list[str]] = {}
    with open(pasta / "ncm_excecao.csv", encoding="utf-8") as f:
        for e in csv.DictReader(f):
            excecoes.setdefault(e["ncma_id"], []).append(e["ncm_prefixo_excluido"])
    return linhas, excecoes


def origem() -> dict:
    return json.loads((PASTA / "origem.json").read_text(encoding="utf-8"))


def candidatos(ncm: str) -> list[Tratamento]:
    """Tratamentos com redução previstos para o NCM (prefixo da tabela, descontadas as exceções)."""
    if not ncm:
        return []
    linhas, excecoes = _carregar()
    aplicaveis = [l for l in linhas if ncm.startswith(l["ncm_prefixo"])]
    # A base repete a mesma regra (prefixo + cClassTrib + anexo) em linhas diferentes, cada uma com
    # parte das exceções (ex.: 0207 no Anexo I exclui 0207.43.00 numa linha e 0207.53.00 na outra).
    # As exceções valem para a regra inteira.
    excluidos: dict[tuple, list[str]] = {}
    for l in aplicaveis:
        chave = (l["ncm_prefixo"], l["cclasstrib"], l["anexo"])
        excluidos.setdefault(chave, []).extend(excecoes.get(l["ncma_id"], []))
    vistos, achados = set(), []
    for l in aplicaveis:
        if any(ncm.startswith(x) for x in excluidos[(l["ncm_prefixo"], l["cclasstrib"], l["anexo"])]):
            continue
        t = Tratamento(l["cclasstrib"], l["descricao"], l["anexo"] or "-", float(l["reducao_pct"]), l["ncm_prefixo"])
        if (t.cclasstrib, t.anexo) not in vistos:
            vistos.add((t.cclasstrib, t.anexo))
            achados.append(t)
    return achados


def _anexos(ts: list[Tratamento]) -> str:
    return ", ".join(sorted({f"Anexo {t.anexo}" for t in ts}))


def conferir(sugestao: Sugestao, ncm: str) -> tuple[Sugestao, Conferencia]:
    """Confere a categoria sugerida com a tabela. Redução sem respaldo na tabela vira REVISAO_HUMANA.

    Tratamentos que dependem de quem compra (ex.: órgão público, produtor rural) não confirmam
    sozinhos uma redução: no recorte do MVP a distribuidora vende para empresas e consumidores.
    """
    if not ncm:
        return sugestao, Conferencia("NAO_CONFERIDO", "Sem NCM, não há o que conferir na tabela oficial.")

    cands = candidatos(ncm)
    do_produto = [t for t in cands if not t.depende_da_operacao]
    cat = sugestao.enquadramento
    mesmos = [t for t in do_produto if t.categoria == cat]

    if cat in ("ALIQUOTA_ZERO", "REDUCAO_60"):
        if mesmos:
            codigos = ", ".join(sorted({t.cclasstrib for t in mesmos}))
            return sugestao, Conferencia(
                "CONFERE", f"A tabela oficial prevê {cat} para este NCM ({_anexos(mesmos)}; cClassTrib {codigos}).", cands)
        condicionais = [t for t in cands if t.categoria == cat]
        if condicionais:
            msg = (f"A IA sugeriu {cat}, mas para este NCM a tabela oficial só prevê esse tratamento numa operação "
                   f"específica ({'; '.join(sorted({DEPENDE_DA_OPERACAO[t.cclasstrib] for t in condicionais}))}).")
        else:
            msg = (f"A IA sugeriu {cat}, mas a tabela oficial não prevê esse tratamento para o NCM. "
                   + (f"Para ele a tabela só prevê: {_anexos(cands)}." if cands else "O NCM não está em nenhum anexo com redução."))
        nova = replace(sugestao, enquadramento="REVISAO_HUMANA", confianca="baixa",
                       alertas=sugestao.alertas + ["Sem respaldo na tabela oficial: encaminhado para revisão."])
        return nova, Conferencia("DIVERGE", msg, cands)

    if cat == "PADRAO":
        if not do_produto:
            extra = (f" Tratamentos que dependem do comprador ({_anexos(cands)}) não foram considerados."
                     if cands else "")
            return sugestao, Conferencia("CONFERE", "O NCM não está em nenhum anexo com redução para o produto: "
                                                    "padrão é coerente." + extra, cands)
        return sugestao, Conferencia(
            "ATENCAO", f"O NCM aparece na tabela oficial ({_anexos(do_produto)}). Confira se o produto se encaixa "
                       "em algum desses tratamentos antes de aceitar o padrão.", cands)

    if cat == "REGIME_ESPECIFICO":
        return sugestao, Conferencia("NAO_CONFERIDO", "A tabela usada não cobre regimes específicos (ex.: combustíveis).", cands)

    # REVISAO_HUMANA: mostra as possibilidades para ajudar o contador.
    if cands:
        return sugestao, Conferencia("INFORMATIVO", f"Para este NCM a tabela oficial prevê: {_anexos(cands)}.", cands)
    return sugestao, Conferencia("INFORMATIVO", "O NCM não está em nenhum anexo com redução na tabela oficial.")
