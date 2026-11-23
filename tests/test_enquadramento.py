import io
import json
import urllib.error

import pytest

from copiloto import enquadramento as enq
from copiloto.enquadramento import (CASOS_DE_TESTE, Entrada, IAIndisponivel, classificar_gemini,
                                    classificar_simulado, conferir_resposta, montar_prompt,
                                    verificar_entrada)


# ---- verificação da entrada (antes da IA)

def test_descricao_vazia_para_o_fluxo():
    v = verificar_entrada("   ", "")
    assert not v.ok and v.erros == ["Informe a descrição do produto para continuar."]
    assert v.avisos == []


def test_ncm_malformado_para_o_fluxo():
    v = verificar_entrada("Arroz", "1006.30")
    assert not v.ok and "8 dígitos" in v.erros[0]


def test_ncm_com_pontos_e_normalizado():
    v = verificar_entrada("  Arroz   branco ", "1006.30.21")
    assert v.ok and v.entrada == Entrada("Arroz branco", "10063021")


def test_sem_ncm_passa_com_aviso():
    v = verificar_entrada("Produto diverso", "")
    assert v.ok and v.entrada.ncm == "" and v.avisos


def test_prompt_v2_leva_produto_e_ncm_formatado():
    prompt = montar_prompt(Entrada("Arroz", "10063021"))
    assert prompt.endswith('Produto: "Arroz" | NCM: 1006.30.21')
    assert "em REVISAO_HUMANA use sempre baixa" in prompt
    assert "carnes" in prompt.split("REDUCAO_60:")[0]  # V3: carnes são Anexo I (alíquota zero)


# ---- conferência da resposta da IA

def test_resposta_no_formato():
    s = conferir_resposta("enquadramento: REDUCAO_60\nconfianca: alta\njustificativa: Higiene.", "MANUAL")
    assert (s.enquadramento, s.confianca, s.justificativa, s.alertas) == ("REDUCAO_60", "alta", "Higiene.", [])


def test_categoria_inesperada_vira_revisao():
    s = conferir_resposta("enquadramento: ISENTO\nconfianca: alta\njustificativa: x", "MANUAL")
    assert s.enquadramento == "REVISAO_HUMANA" and s.confianca == "baixa"
    assert "Categoria inesperada" in s.alertas[0]


def test_resposta_vazia_vira_revisao():
    s = conferir_resposta("", "INTEGRADA")
    assert s.precisa_revisao and s.alertas


def test_texto_extra_gera_alerta_mas_aproveita_campos():
    texto = ("Claro!\nenquadramento: ALIQUOTA_ZERO\nconfiança: Alta\njustificativa: Arroz.\n"
             "Deseja classificar o próximo produto?")
    s = conferir_resposta(texto, "MANUAL")
    assert s.enquadramento == "ALIQUOTA_ZERO" and s.confianca == "alta"
    assert any("5 linhas" in a for a in s.alertas)


def test_revisao_humana_sempre_com_confianca_baixa():
    s = conferir_resposta("enquadramento: REVISAO_HUMANA\nconfianca: alta\njustificativa: vago", "MANUAL")
    assert s.confianca == "baixa" and s.alertas


# ---- classificação

@pytest.mark.parametrize("id_, tipo, descricao, ncm, esperado", CASOS_DE_TESTE)
def test_casos_da_aula_3_no_modo_simulado(id_, tipo, descricao, ncm, esperado):
    entrada = verificar_entrada(descricao, ncm).entrada
    s = conferir_resposta(classificar_simulado(entrada), "SIMULADA")
    assert s.enquadramento == esperado and s.alertas == []


def test_simulado_fora_dos_casos_avisa():
    with pytest.raises(IAIndisponivel):
        classificar_simulado(Entrada("Furadeira", "84672100"))


def test_integrada_sem_chave_e_ia_indisponivel(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(IAIndisponivel, match="sem chave"):
        classificar_gemini(Entrada("Arroz", "10063021"))


def test_integrada_le_resposta_do_gemini(monkeypatch):
    enviado = {}

    def falso_urlopen(pedido, timeout):
        enviado["corpo"] = json.loads(pedido.data)
        enviado["chave"] = pedido.get_header("X-goog-api-key")
        texto = "enquadramento: ALIQUOTA_ZERO\nconfianca: alta\njustificativa: Arroz."
        return io.BytesIO(json.dumps({"candidates": [{"content": {"parts": [{"text": texto}]}}]}).encode())

    monkeypatch.setattr(enq.urllib.request, "urlopen", falso_urlopen)
    bruto = classificar_gemini(Entrada("Arroz", "10063021"), chave="teste")
    assert conferir_resposta(bruto, "INTEGRADA").enquadramento == "ALIQUOTA_ZERO"
    assert enviado["chave"] == "teste"
    assert "NCM: 1006.30.21" in enviado["corpo"]["contents"][0]["parts"][0]["text"]


def test_integrada_com_erro_de_rede(monkeypatch):
    def falha(*_a, **_k):
        raise urllib.error.URLError("sem rede")

    monkeypatch.setattr(enq.urllib.request, "urlopen", falha)
    with pytest.raises(IAIndisponivel):
        classificar_gemini(Entrada("Arroz", "10063021"), chave="teste")
