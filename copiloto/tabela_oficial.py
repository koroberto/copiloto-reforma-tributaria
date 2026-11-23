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
    """Confere a categoria sugerida com a tabela. Redução sem respaldo na tabela vira REVISAO_HUMANA."""
    if not ncm:
        return sugestao, Conferencia("NAO_CONFERIDO", "Sem NCM, não há o que conferir na tabela oficial.")

    cands = candidatos(ncm)
    cat = sugestao.enquadramento
    mesmos = [t for t in cands if t.categoria == cat]

    if cat in ("ALIQUOTA_ZERO", "REDUCAO_60"):
        if mesmos:
            codigos = ", ".join(sorted({t.cclasstrib for t in mesmos}))
            return sugestao, Conferencia(
                "CONFERE", f"A tabela oficial prevê {cat} para este NCM ({_anexos(mesmos)}; cClassTrib {codigos}).", cands)
        msg = (f"A IA sugeriu {cat}, mas a tabela oficial não prevê esse tratamento para o NCM. "
               + (f"Para ele a tabela só prevê: {_anexos(cands)}." if cands else "O NCM não está em nenhum anexo com redução."))
        nova = replace(sugestao, enquadramento="REVISAO_HUMANA", confianca="baixa",
                       alertas=sugestao.alertas + ["Sem respaldo na tabela oficial: encaminhado para revisão."])
        return nova, Conferencia("DIVERGE", msg, cands)

    if cat == "PADRAO":
        if not cands:
            return sugestao, Conferencia("CONFERE", "O NCM não está em nenhum anexo com redução: padrão é coerente.")
        return sugestao, Conferencia(
            "ATENCAO", f"O NCM aparece na tabela oficial ({_anexos(cands)}). Confira se o produto se encaixa "
                       "em algum desses tratamentos antes de aceitar o padrão.", cands)

    if cat == "REGIME_ESPECIFICO":
        return sugestao, Conferencia("NAO_CONFERIDO", "A tabela usada não cobre regimes específicos (ex.: combustíveis).", cands)

    # REVISAO_HUMANA: mostra as possibilidades para ajudar o contador.
    if cands:
        return sugestao, Conferencia("INFORMATIVO", f"Para este NCM a tabela oficial prevê: {_anexos(cands)}.", cands)
    return sugestao, Conferencia("INFORMATIVO", "O NCM não está em nenhum anexo com redução na tabela oficial.")
