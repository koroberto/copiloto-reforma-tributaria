from decimal import Decimal
from pathlib import Path

import pytest

from copiloto.nfe import ler_nfe

FIXTURE = Path(__file__).parent / "fixtures" / "nfe-sintetica.xml"


def test_le_cabecalho():
    nota = ler_nfe(FIXTURE)
    assert nota.chave.startswith("3526")
    assert nota.uf_origem == "SP" and nota.uf_destino == "MG"
    assert len(nota.itens) == 2


def test_le_itens_e_tributos():
    arroz, furadeira = ler_nfe(FIXTURE).itens
    assert arroz.ncm == "10063021" and arroz.cfop == "6102"
    assert arroz.valor_produto == Decimal("250.00")
    assert arroz.icms == Decimal("30.00") and arroz.ipi == Decimal("0")
    assert furadeira.icms == Decimal("43.20")  # subgrupo ICMS20
    assert furadeira.ipi == Decimal("30.00")
    assert furadeira.pis + furadeira.cofins == Decimal("55.50")


def test_xml_que_nao_e_nfe(tmp_path):
    arquivo = tmp_path / "outro.xml"
    arquivo.write_text("<raiz/>")
    with pytest.raises(ValueError):
        ler_nfe(arquivo)
