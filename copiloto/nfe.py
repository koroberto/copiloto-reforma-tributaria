"""Leitura do XML da NF-e (modelo 55): itens com NCM, CFOP, valores e tributos."""

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

NS = {"nfe": "http://www.portalfiscal.inf.br/nfe"}


@dataclass
class ItemNFe:
    numero: int
    codigo: str
    descricao: str
    ncm: str
    cfop: str
    quantidade: Decimal
    valor_produto: Decimal
    icms: Decimal
    ipi: Decimal
    pis: Decimal
    cofins: Decimal


@dataclass
class NFe:
    chave: str
    data_emissao: str
    emitente_cnpj: str
    uf_origem: str
    uf_destino: str
    itens: list[ItemNFe]


def _texto(no, caminho: str, padrao: str = "") -> str:
    achado = no.find(caminho, NS) if no is not None else None
    return achado.text.strip() if achado is not None and achado.text else padrao


def _decimal(no, caminho: str) -> Decimal:
    return Decimal(_texto(no, caminho, "0"))


def _valor_tributo(imposto, grupo: str, campo: str) -> Decimal:
    """Soma o campo em qualquer subgrupo (ex.: ICMS00, ICMS20, PISAliq, IPITrib)."""
    bloco = imposto.find(f"nfe:{grupo}", NS) if imposto is not None else None
    if bloco is None:
        return Decimal("0")
    return sum((Decimal(v.text) for v in bloco.iter(f"{{{NS['nfe']}}}{campo}") if v.text), Decimal("0"))


def ler_nfe(origem: str | Path) -> NFe:
    """Lê um arquivo XML de NF-e (com ou sem o envelope nfeProc)."""
    raiz = ET.parse(origem).getroot()
    inf = raiz.find(".//nfe:infNFe", NS)
    if inf is None:
        raise ValueError(f"{origem}: não é um XML de NF-e (infNFe não encontrado)")

    itens = []
    for det in inf.findall("nfe:det", NS):
        prod = det.find("nfe:prod", NS)
        imposto = det.find("nfe:imposto", NS)
        itens.append(ItemNFe(
            numero=int(det.get("nItem", "0")),
            codigo=_texto(prod, "nfe:cProd"),
            descricao=_texto(prod, "nfe:xProd"),
            ncm=_texto(prod, "nfe:NCM"),
            cfop=_texto(prod, "nfe:CFOP"),
            quantidade=_decimal(prod, "nfe:qCom"),
            valor_produto=_decimal(prod, "nfe:vProd"),
            icms=_valor_tributo(imposto, "ICMS", "vICMS"),
            ipi=_valor_tributo(imposto, "IPI", "vIPI"),
            pis=_valor_tributo(imposto, "PIS", "vPIS"),
            cofins=_valor_tributo(imposto, "COFINS", "vCOFINS"),
        ))

    return NFe(
        chave=inf.get("Id", "").removeprefix("NFe"),
        data_emissao=_texto(inf, "nfe:ide/nfe:dhEmi"),
        emitente_cnpj=_texto(inf, "nfe:emit/nfe:CNPJ"),
        uf_origem=_texto(inf, "nfe:emit/nfe:enderEmit/nfe:UF"),
        uf_destino=_texto(inf, "nfe:dest/nfe:enderDest/nfe:UF"),
        itens=itens,
    )
