"""Testes do lote. O número no nome do teste é o requisito de docs/requisitos-ears.md."""

import csv
import io
from pathlib import Path

import pytest

from copiloto import lote
from copiloto.enquadramento import IAIndisponivel, conferir_resposta
from copiloto.lote import (AUTOMATICO, REVISAR, ItemLote, aplicar_decisao, aplicar_linhas, classificar_lote,
                           decidir, escolher_cclasstrib, exportar_csv, ler_planilha, ler_resposta_lote, ler_xmls,
                           montar_prompt_lote, preparar, resumo)
from copiloto.nfe import ler_nfe
from copiloto.tabela_oficial import Tratamento, conferir
from tests.test_tabela_oficial import sugestao

FIXTURES = Path(__file__).parent / "fixtures"


def exemplo_classificado():
    itens = preparar(ler_planilha(lote.CADASTRO_EXEMPLO.read_bytes(), lote.CADASTRO_EXEMPLO.name))
    assert classificar_lote(itens, "SIMULADA") == []
    return itens, {i.id: i for i in itens}


def item_com_resposta(descricao, ncm, resposta):
    """Um item verificado, com a resposta da IA já conferida, e a decisão automática ou fila."""
    item = preparar([{"descricao": descricao, "ncm": ncm}])[0]
    item.sugestao = conferir_resposta(resposta, "MANUAL")
    decidir(item)
    return item


def exportado(itens):
    return list(csv.reader(io.StringIO(exportar_csv(itens).decode("utf-8-sig")), delimiter=";"))


# ---- entrada

def test_REQ01_planilha_com_cabecalho_do_erp_em_qualquer_ordem():
    texto = "Linha de título do relatório\nNCM;Descrição do produto;Cód. Produto\n1006.30.21;Arroz 5 kg;A1\n;;\n"
    assert ler_planilha(texto.encode("cp1252"), "cadastro.csv") == [
        {"codigo": "A1", "descricao": "Arroz 5 kg", "ncm": "1006.30.21"}]


def test_REQ01_planilha_com_virgula_utf8_e_linha_curta():
    texto = "codigo,produto,ncm\n7,Café torrado 500 g,0901.21.00\n8,Açúcar 1 kg\n"
    assert ler_planilha(texto.encode("utf-8-sig"), "x.csv") == [
        {"codigo": "7", "descricao": "Café torrado 500 g", "ncm": "0901.21.00"},
        {"codigo": "8", "descricao": "Açúcar 1 kg", "ncm": ""}]


def test_REQ02_planilha_sem_descricao_avisa():
    with pytest.raises(ValueError, match="descrição"):
        ler_planilha(b"codigo;ncm\n1;10063021\n", "x.csv")


def test_REQ01_REQ06_xlsx_com_ncm_numerico_recupera_o_zero(tmp_path):
    from openpyxl import Workbook
    wb = Workbook()
    wb.active.append(["Código", "Descrição", "NCM"])
    wb.active.append([10, "Leite UHT 1 L", 4012010])        # o Excel guardou o NCM como número
    wb.active.append([11, "Arroz 5 kg", 10063021.0])        # e às vezes como número decimal
    wb.active.append([12, None, None])
    arquivo = tmp_path / "cadastro.xlsx"
    wb.save(arquivo)
    linhas = ler_planilha(arquivo.read_bytes(), "cadastro.xlsx")
    assert [l["ncm"] for l in linhas] == ["4012010", "10063021", ""]
    leite = preparar(linhas)[0]
    assert leite.ncm == "04012010" and "zero à esquerda" in leite.observacao
    assert (leite.descricao, leite.ncm_informado) == ("Leite UHT 1 L", "4012010")


def test_REQ03_REQ04_xmls_sem_repetir_produto_e_xml_ruim_nao_para_o_lote():
    nota = (FIXTURES / "nfe-sintetica.xml").read_bytes()
    itens_da_nota = ler_nfe(FIXTURES / "nfe-sintetica.xml").itens
    linhas, falhas = ler_xmls([("ruim.xml", b"<nao-e-nfe/>"), ("a.xml", nota), ("b.xml", nota)])
    assert len(falhas) == 1 and falhas[0].startswith("ruim.xml")
    assert len(linhas) == len(itens_da_nota)
    assert linhas[0] == {"codigo": itens_da_nota[0].codigo, "descricao": itens_da_nota[0].descricao,
                         "ncm": itens_da_nota[0].ncm}


def test_REQ05_verificacao_de_cada_item():
    itens = preparar([{"descricao": "", "ncm": "10063021"}, {"descricao": "Escova", "ncm": "9603.21"},
                      {"descricao": "Arroz", "ncm": "1006.30.21"}])
    assert [bool(i.entrada) for i in itens] == [False, False, True]
    assert "8 dígitos" in itens[1].erros[0]
    decidir(itens[1])
    assert itens[1].status == REVISAR and itens[1].motivo.startswith("Entrada com problema:")


# ---- IA

def test_REQ07_prompt_do_lote_so_leva_itens_validos():
    itens = preparar([{"descricao": "Arroz", "ncm": "10063021"}, {"descricao": "", "ncm": ""}])
    prompt = montar_prompt_lote(itens)
    assert '1. "Arroz" | NCM: 1006.30.21' in prompt and "2." not in prompt.split("Produtos:")[1]
    assert "uma linha por produto" in prompt


def test_REQ08_REQ09_resposta_em_tabela_markdown_com_falta_e_categoria_estranha():
    texto = ("| nº | enquadramento | confiança | justificativa |\n|---|---|---|---|\n"
             "| 1 | ALIQUOTA_ZERO | alta | Arroz. |\n| 2 | ISENTO | alta | x |\n| 2 | PADRAO | alta | repetido |")
    sugs, avisos = ler_resposta_lote(texto, {1, 2, 3}, "MANUAL")
    assert sugs[1].enquadramento == "ALIQUOTA_ZERO"
    assert sugs[2].enquadramento == "REVISAO_HUMANA" and sugs[2].confianca == "baixa"
    assert any("repetido" in a for a in avisos) and any("não respondeu 1" in a for a in avisos)


def test_REQ10_integrada_por_blocos_e_bloco_com_falha(monkeypatch):
    monkeypatch.setattr(lote, "TAMANHO_BLOCO", 1)
    itens = preparar([{"descricao": "Arroz", "ncm": "10063021"}, {"descricao": "Shampoo", "ncm": "33051000"}])
    chamadas = []

    def falsa(prompt):
        chamadas.append(prompt)
        if "Shampoo" in prompt:
            raise IAIndisponivel("sem rede")
        return "1 | ALIQUOTA_ZERO | alta | Arroz da cesta básica."

    avisos = classificar_lote(itens, "INTEGRADA", chamar=falsa)
    assert len(chamadas) == 2 and any("sem rede" in a for a in avisos)
    assert itens[0].status == AUTOMATICO and itens[1].status == REVISAR


@pytest.mark.parametrize("ncm, motivo", [("10063021", "Sem sugestão da IA. A tabela oficial prevê para o NCM: "
                                                     "Anexo I, Anexo IX."),
                                         ("33051000", "Sem sugestão da IA.")])
def test_REQ10_sem_sugestao_vai_para_a_fila_com_os_anexos_possiveis(ncm, motivo):
    item = preparar([{"descricao": "Produto", "ncm": ncm}])[0]
    decidir(item)
    assert item.status == REVISAR and item.motivo == motivo


# ---- conferência e aprovação automática

def test_REQ11_reducao_que_so_vale_para_produtor_rural_nao_confirma():
    # Arroz aparece no Anexo IX (insumo agropecuário, 60%), mas isso depende de quem compra.
    nova, c = conferir(sugestao("REDUCAO_60"), "10063021")
    assert c.situacao == "DIVERGE" and nova.enquadramento == "REVISAO_HUMANA"
    assert "produtor rural" in c.mensagem


def test_REQ12_exemplo_aprova_27_e_manda_7_para_a_fila():
    itens, _ = exemplo_classificado()
    assert resumo(itens) == {"itens": 34, "automáticos": 27, "revisados": 0, "pendentes": 7}


@pytest.mark.parametrize("n, cclasstrib", [(1, "200003"), (6, "200034"), (9, "200035"), (15, "200014"),
                                           (24, "000001")])
def test_REQ12_automaticos_saem_com_o_cclasstrib(n, cclasstrib):
    _, por_id = exemplo_classificado()
    item = por_id[n]
    assert (item.status, item.cclasstrib, item.decidido_por) == (AUTOMATICO, cclasstrib, "automático")
    assert item.motivo == "Tabela oficial e IA de acordo."


@pytest.mark.parametrize("descricao, ncm, resposta, motivo", [
    ("Arroz 5 kg", "10063021", "enquadramento: ALIQUOTA_ZERO\nconfianca: media\njustificativa: Arroz.",
     "A IA ficou com confiança media."),
    ("Arroz 5 kg", "10063021", "enquadramento: ALIQUOTA_ZERO\nconfianca: alta",
     "A resposta veio com 2 linhas em vez de 3; só os campos foram aproveitados. A IA não justificou: "
     "confira antes de aceitar."),
    ("Gasolina comum", "27101259", "enquadramento: REGIME_ESPECIFICO\nconfianca: alta\njustificativa: Combustível.",
     "Regime específico: a tabela usada não cobre; confira e informe o cClassTrib."),
])
def test_REQ12_sem_os_quatro_sinais_nao_aprova_sozinho(descricao, ncm, resposta, motivo):
    item = item_com_resposta(descricao, ncm, resposta)
    assert item.status == REVISAR and item.motivo == motivo and item.decisao == ""


def test_REQ13_ncm_com_tratamento_fora_da_tabela_vai_para_a_fila():
    _, por_id = exemplo_classificado()
    assert por_id[13].motivo.startswith("Confira o produto: absorventes")   # fralda: a IA e a tabela concordam
    absorvente = por_id[14]                                                  # a IA disse zero; a tabela só tem o Anexo VIII
    assert absorvente.motivo.startswith("A IA sugeriu ALIQUOTA_ZERO") and " Atenção: absorventes" in absorvente.motivo
    # REVISAO_HUMANA pedida pela própria IA não ganha o aviso, que é só para divergência com a tabela
    vago = item_com_resposta("Kit higiene", "96190000", "enquadramento: REVISAO_HUMANA\nconfianca: baixa\n"
                                                         "justificativa: Kit misto.")
    assert vago.motivo == "A IA pediu revisão: Kit misto."


def test_REQ14_ia_disse_padrao_mas_o_ncm_esta_num_anexo():
    _, por_id = exemplo_classificado()
    assert por_id[7].status == REVISAR and "Anexo I" in por_id[7].motivo     # margarina
    assert "não corresponde" in por_id[31].motivo                            # shampoo com NCM de arroz


# ---- decisão do contador e saída

def _t(codigo, reducao, anexo="VII"):
    return Tratamento(codigo, f"tratamento {codigo}", anexo, reducao, "0000")


@pytest.mark.parametrize("categoria, cands, esperado", [
    ("PADRAO", [], ("000001", "")),
    ("REGIME_ESPECIFICO", [_t("200034", 60.0)], ("", "")),
    ("REDUCAO_60", [_t("200034", 60.0), _t("200038", 60.0, "IX")], ("200034", "")),
    ("REDUCAO_60", [_t("200034", 60.0), _t("200035", 60.0, "VIII")],
     ("", "Mais de um cClassTrib possível (200034, 200035): escolha o que se aplica.")),
    ("REDUCAO_60", [_t("200038", 60.0, "IX")],
     ("", "O tratamento só vale numa operação específica: insumo agropecuário vendido a produtor rural.")),
    ("ALIQUOTA_ZERO", [_t("200034", 60.0)], ("", "A tabela oficial não tem cClassTrib para esta categoria neste NCM.")),
])
def test_REQ15_cclasstrib_so_e_preenchido_quando_ha_um_so(categoria, cands, esperado):
    assert escolher_cclasstrib(categoria, cands) == esperado


def test_REQ15_REQ16_REQ19_contador_resolve_a_fila_e_a_planilha_sai():
    itens, por_id = exemplo_classificado()
    erros = aplicar_linhas([
        {"nº": 34, "aceitar sugestão": True},                       # sem sugestão: erro, e a fila segue
        {"nº": 7, "decisão": "ALIQUOTA_ZERO"},                       # margarina: cClassTrib pela tabela
        {"nº": 13, "aceitar sugestão": True, "decisão": "REDUCAO_60",
         "observação": "fralda infantil, Anexo VIII"},             # a decisão escrita vale sobre o "aceitar"
        {"nº": 14, "decisão": "ALIQUOTA_ZERO"},                     # absorvente sem código: erro
        {"nº": 31, "aceitar sugestão": True},                       # REVISAO_HUMANA não se aceita
        {"nº": 32, "decisão": "PADRAO", "cClassTrib": "200003"},     # código incoerente
        {"nº": 33, "observação": "perguntar ao cliente o que é"},   # sem decisão: segue pendente
    ], por_id)
    assert erros == [
        "Item 34: não há sugestão da IA para aceitar; escolha a decisão.",
        "Item 14: Informe o cClassTrib (6 dígitos) para a redução.",
        "Item 31: a sugestão da IA foi REVISAO_HUMANA; escolha a decisão.",
        "Item 32: Para PADRAO o cClassTrib é 000001.",
    ]
    assert por_id[7].cclasstrib == "200003" and por_id[7].decidido_por == "contador"
    assert (por_id[13].decisao, por_id[13].cclasstrib, por_id[13].observacao) == (
        "REDUCAO_60", "200035", "fralda infantil, Anexo VIII")
    for n in (14, 31, 32, 33, 34):
        assert (por_id[n].decisao, por_id[n].cclasstrib, por_id[n].decidido_por) == ("", "", "")
    assert por_id[33].observacao == "perguntar ao cliente o que é"
    assert exportado(itens)[33][7] == "pendente"

    aplicar_linhas([{"nº": 14, "decisão": "ALIQUOTA_ZERO", "cClassTrib": "200013"},
                    {"nº": 31, "decisão": "PADRAO", "observação": "NCM corrigido para 3305.10.00 no ERP"},
                    {"nº": 32, "decisão": "PADRAO"}, {"nº": 33, "decisão": "PADRAO"},
                    {"nº": 34, "decisão": "REDUCAO_60", "cClassTrib": "200035"}], por_id)
    assert resumo(itens)["pendentes"] == 0

    linhas = exportado(itens)
    assert linhas[0] == ["codigo", "descricao", "ncm", "enquadramento", "cclasstrib", "descricao_cclasstrib", "anexo",
                         "decidido_por", "sugestao_ia", "confianca_ia", "tabela_oficial", "motivo_revisao",
                         "observacao"]
    absorvente = next(l for l in linhas if l[0] == "1014")
    assert absorvente[3:5] == ["ALIQUOTA_ZERO", "200013"] and absorvente[7] == "contador"
    shampoo = next(l for l in linhas if l[0] == "1031")
    assert shampoo[4] == "000001" and shampoo[12] == "NCM corrigido para 3305.10.00 no ERP"
    arroz = next(l for l in linhas if l[0] == "1001")
    assert arroz == ["1001", "ARROZ BRANCO TIPO 1 5KG", "1006.30.21", "ALIQUOTA_ZERO", "200003",
                     "Vendas de produtos destinados à alimentação humana (Anexo I)", "I", "automático",
                     "ALIQUOTA_ZERO", "alta", "CONFERE", "", ""]


def test_REQ16_decisao_recusada_nao_apaga_a_observacao():
    item = ItemLote(1, "", "Fralda", "96190000", observacao="anotação anterior")
    assert aplicar_decisao(item, "PADRAO", "200035") == "Para PADRAO o cClassTrib é 000001."
    assert item.observacao == "anotação anterior" and item.decisao == ""
    assert aplicar_decisao(item, "PADRAO") is None and item.observacao == "anotação anterior"


def test_REQ17_automatico_alterado_passa_a_ser_do_contador():
    _, por_id = exemplo_classificado()
    aplicar_linhas([{"nº": 1, "decisão": "ALIQUOTA_ZERO", "cClassTrib": "200003"},
                    {"nº": 24, "decisão": "REDUCAO_60", "cClassTrib": "200035"}], por_id)
    assert por_id[1].decidido_por == "automático" and por_id[24].decidido_por == "contador"


def test_REQ18_pendentes_contam_ate_a_fila_zerar():
    itens, por_id = exemplo_classificado()
    aplicar_linhas([{"nº": 13, "aceitar sugestão": True}], por_id)
    assert resumo(itens) == {"itens": 34, "automáticos": 27, "revisados": 1, "pendentes": 6}

