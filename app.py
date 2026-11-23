"""Copiloto da Reforma Tributária: MVP da Aula 04 (Grupo 4). Rodar: streamlit run app.py"""

from datetime import datetime
from pathlib import Path

import streamlit as st

from copiloto.enquadramento import (CASOS_DE_TESTE, ROTULOS, IAIndisponivel, classificar_gemini,
                                    classificar_simulado, conferir_resposta, formatar_ncm,
                                    montar_prompt, verificar_entrada)
from copiloto.nfe import ler_nfe
from copiloto.tabela_oficial import conferir, origem

st.set_page_config(page_title="Copiloto da Reforma Tributária", page_icon="🧾", layout="wide")

MODOS = {
    "Simulada (respostas gravadas do Gemini, prompt V2)": "SIMULADA",
    "Manual (copiar o prompt para um chat de IA)": "MANUAL",
    "Integrada (API do Gemini, precisa de chave)": "INTEGRADA",
}
CORES = {"ALIQUOTA_ZERO": "green", "REDUCAO_60": "blue", "PADRAO": "gray",
         "REGIME_ESPECIFICO": "orange", "REVISAO_HUMANA": "red"}

st.session_state.setdefault("historico", [])
st.session_state.setdefault("descricao", "")
st.session_state.setdefault("ncm", "")

st.title("🧾 Copiloto da Reforma Tributária")
st.caption("Grupo 4 · Sistemas Inteligentes II · MVP da Aula 04: enquadramento de produto no IBS/CBS "
           "(LC 214/2025). A IA sugere; o contador decide.")

with st.sidebar:
    st.header("Como a IA entra")
    modo = MODOS[st.radio("Etapa de classificação", list(MODOS))]
    st.divider()
    st.subheader("Casos de teste (Aula 3)")
    for id_, tipo, desc, ncm, esperado in CASOS_DE_TESTE:
        if st.button(f"{id_} · {tipo}: {desc[:28]}", key=f"caso_{id_}", use_container_width=True):
            st.session_state.descricao, st.session_state.ncm = desc, ncm
            st.session_state.pop("resultado", None)
    st.divider()
    st.subheader("Ou a partir de uma NF-e")
    xml = st.file_uploader("XML da NF-e", type="xml")
    if xml is None and st.checkbox("Usar a NF-e sintética de exemplo"):
        xml = Path(__file__).parent / "tests" / "fixtures" / "nfe-sintetica.xml"
    if xml is not None:
        try:
            itens = ler_nfe(xml).itens
            item = st.selectbox("Item da nota", itens, format_func=lambda i: f"{i.numero}. {i.descricao}")
            if st.button("Usar este item", use_container_width=True):
                st.session_state.descricao, st.session_state.ncm = item.descricao, item.ncm
                st.session_state.pop("resultado", None)
        except Exception as erro:  # XML ruim não pode derrubar a tela
            st.error(f"Não consegui ler o XML: {erro}")

# 1. Entrada ---------------------------------------------------------------------------
st.subheader("1 · Produto")
c1, c2 = st.columns([3, 1])
descricao = c1.text_input("Descrição do produto", key="descricao", placeholder="Ex.: Arroz branco tipo 1, pacote 5 kg")
ncm = c2.text_input("NCM", key="ncm", placeholder="1006.30.21")
enviar = st.button("Sugerir enquadramento", type="primary")

if enviar:
    st.session_state.pop("resultado", None)
    # 2. Verificação (antes da IA) -------------------------------------------------------
    verif = verificar_entrada(descricao, ncm)
    st.session_state.verificacao = verif
    if verif.ok and modo != "MANUAL":
        try:
            bruto = (classificar_simulado if modo == "SIMULADA" else classificar_gemini)(verif.entrada)
            st.session_state.resultado, st.session_state.conferencia = conferir(
                conferir_resposta(bruto, modo), verif.entrada.ncm)
        except IAIndisponivel as erro:
            st.session_state.resultado = None
            st.session_state.falha_ia = str(erro)

verif = st.session_state.get("verificacao")
if verif is not None:
    st.subheader("2 · Verificação da entrada")
    for e in verif.erros:
        st.error(e)
    for a in verif.avisos:
        st.warning(a)
    if verif.ok:
        st.success(f"Entrada aceita: “{verif.entrada.descricao}” · NCM {formatar_ncm(verif.entrada.ncm)}")

    if verif.ok:
        st.subheader("3 · Classificação pela IA")
        prompt = montar_prompt(verif.entrada)
        if modo == "MANUAL":
            st.info("Copie o prompt (ícone no canto do quadro), cole num chat de IA e traga a resposta.")
            st.code(prompt, language=None)
            colada = st.text_area("Resposta da IA", height=110,
                                  placeholder="enquadramento: ...\nconfianca: ...\njustificativa: ...")
            if st.button("Conferir resposta"):
                st.session_state.resultado, st.session_state.conferencia = conferir(
                    conferir_resposta(colada, "MANUAL"), verif.entrada.ncm)
        else:
            with st.expander("Ver o prompt enviado (prompt V3)"):
                st.code(prompt, language=None)
            if st.session_state.get("resultado") is None and st.session_state.get("falha_ia") and enviar:
                st.error(f"IA indisponível: {st.session_state.falha_ia}")

    sug = st.session_state.get("resultado")
    conf = st.session_state.get("conferencia")
    if verif.ok and sug is not None and conf is not None:
        st.subheader("4 · Conferência com a tabela oficial da Receita")
        aviso = {"CONFERE": st.success, "DIVERGE": st.error, "ATENCAO": st.warning}.get(conf.situacao, st.info)
        aviso(f"**{conf.situacao}** · {conf.mensagem}")
        if conf.candidatos:
            st.dataframe([{"cClassTrib": c.cclasstrib, "anexo": c.anexo, "redução": f"{c.reducao_pct:.0f}%",
                           "tratamento": c.descricao, "NCM na tabela": c.ncm_prefixo} for c in conf.candidatos],
                         use_container_width=True, hide_index=True)
        o = origem()
        st.caption(f"Fonte: calculadora oficial da Receita (ReceitaFederal/calculadora-rtc-regime-regular, "
                   f"commit {o['commit'][:7]}, vigência em {o['vigencia_em']}). Sem efeito normativo.")

    if verif.ok and sug is not None:
        st.subheader("5 · Sugestão para o contador")
        st.markdown(f"### :{CORES[sug.enquadramento]}[{sug.enquadramento}]")
        st.caption(ROTULOS[sug.enquadramento])
        m1, m2 = st.columns(2)
        m1.metric("Confiança", sug.confianca)
        m2.metric("Origem da sugestão", sug.origem)
        st.write(f"**Justificativa:** {sug.justificativa}")
        for a in sug.alertas:
            st.warning(a)
        if sug.precisa_revisao:
            st.error("Esta sugestão não deve ser usada sem análise do contador.")
        with st.expander("Resposta bruta da IA"):
            st.code(sug.resposta_bruta or "(vazia)", language=None)

        # 5. Decisão humana ---------------------------------------------------------------
        st.subheader("6 · Decisão do contador")
        d1, d2 = st.columns([2, 3])
        decisao = d1.selectbox("Enquadramento final", list(ROTULOS),
                               index=list(ROTULOS).index(sug.enquadramento))
        obs = d2.text_input("Observação (opcional)")
        if st.button("Registrar decisão"):
            st.session_state.historico.append({
                "hora": datetime.now().strftime("%H:%M:%S"),
                "produto": verif.entrada.descricao,
                "NCM": formatar_ncm(verif.entrada.ncm),
                "sugestão": sug.enquadramento,
                "tabela oficial": conf.situacao if conf else "",
                "confiança": sug.confianca,
                "origem": sug.origem,
                "decisão": decisao,
                "alterou": "sim" if decisao != sug.enquadramento else "não",
                "observação": obs,
            })
            st.success("Decisão registrada.")

if st.session_state.historico:
    st.divider()
    st.subheader("Decisões desta sessão")
    st.dataframe(st.session_state.historico, use_container_width=True, hide_index=True)
