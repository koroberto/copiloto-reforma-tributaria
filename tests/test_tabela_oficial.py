import pytest

from copiloto.enquadramento import conferir_resposta
from copiloto.tabela_oficial import candidatos, conferir, origem


def sugestao(cat, conf="alta"):
    return conferir_resposta(f"enquadramento: {cat}\nconfianca: {conf}\njustificativa: teste", "MANUAL")


def test_origem_registra_o_commit_da_receita():
    o = origem()
    assert o["repositorio"].endswith("calculadora-rtc-regime-regular") and len(o["commit"]) == 40


def test_arroz_esta_no_anexo_i():
    assert ("200003", "I") in {(t.cclasstrib, t.anexo) for t in candidatos("10063021")}


def test_excecao_tira_o_ncm_do_anexo():
    # 0207.43.00 (fígados gordos de pato) é exceção às carnes de aves do Anexo I.
    assert "I" in {t.anexo for t in candidatos("02071400")}
    assert "I" not in {t.anexo for t in candidatos("02074300")}


@pytest.mark.parametrize("ncm, cat", [("10063021", "ALIQUOTA_ZERO"), ("02013000", "ALIQUOTA_ZERO"),
                                      ("34011190", "REDUCAO_60"), ("04090000", "REDUCAO_60")])
def test_confere(ncm, cat):
    nova, c = conferir(sugestao(cat), ncm)
    assert c.situacao == "CONFERE" and nova.enquadramento == cat


@pytest.mark.parametrize("ncm, cat", [
    ("02013000", "REDUCAO_60"),     # carne bovina: Anexo I, não 60% (erro da V2)
    ("33051000", "REDUCAO_60"),     # shampoo: fora da lista fechada do Anexo VIII
    ("33051000", "ALIQUOTA_ZERO"),  # shampoo: não está em anexo nenhum
])
def test_reducao_sem_respaldo_vira_revisao(ncm, cat):
    nova, c = conferir(sugestao(cat), ncm)
    assert c.situacao == "DIVERGE"
    assert nova.enquadramento == "REVISAO_HUMANA" and nova.confianca == "baixa"


def test_padrao_com_ncm_em_anexo_pede_atencao():
    nova, c = conferir(sugestao("PADRAO"), "85171300")  # smartphone: Anexo V (acessibilidade)
    assert c.situacao == "ATENCAO" and nova.enquadramento == "PADRAO"
    assert {t.anexo for t in c.candidatos} == {"V"}


def test_padrao_sem_anexo_confere():
    assert conferir(sugestao("PADRAO"), "33051000")[1].situacao == "CONFERE"


def test_sem_ncm_nao_confere():
    assert conferir(sugestao("REVISAO_HUMANA", "baixa"), "")[1].situacao == "NAO_CONFERIDO"
