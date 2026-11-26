"""Copiloto da Reforma Tributária: MVP do Grupo 4 (Sistemas Inteligentes II). Rodar: streamlit run app.py

Duas abas:
- Cadastro do cliente (lote): o uso do dia a dia. O contador envia o cadastro ou os XMLs, a tabela
  oficial e a IA aprovam sozinhas o que concordam, e ele revisa só a fila.
- Um produto, passo a passo: o fluxo detalhado da Aula 04, para ver cada etapa.
"""

from datetime import datetime
from pathlib import Path

import streamlit as st

from copiloto import lote as lt
from copiloto.enquadramento import (CASOS_DE_TESTE, ROTULOS, IAIndisponivel, classificar_gemini,
                                    classificar_simulado, conferir_resposta, formatar_ncm,
                                    montar_prompt, verificar_entrada)
from copiloto.nfe import ler_nfe
from copiloto.tabela_oficial import conferir, origem

st.set_page_config(page_title="Copiloto da Reforma Tributária", page_icon="🧾", layout="wide")

MODOS = {
    "Simulada (respostas gravadas do Gemini)": "SIMULADA",
    "Manual (copiar o prompt para um chat de IA)": "MANUAL",
    "Integrada (API do Gemini, precisa de chave)": "INTEGRADA",
}
CORES = {"ALIQUOTA_ZERO": "green", "REDUCAO_60": "blue", "PADRAO": "gray",
         "REGIME_ESPECIFICO": "orange", "REVISAO_HUMANA": "red"}

st.session_state.setdefault("historico", [])
st.session_state.setdefault("descricao", "")
st.session_state.setdefault("ncm", "")
st.session_state.setdefault("lote_versao", 0)

st.title("🧾 Copiloto da Reforma Tributária")
st.caption("Grupo 4 · Sistemas Inteligentes II · Enquadramento dos produtos no IBS/CBS (LC 214/2025) com o "
           "cClassTrib. A tabela oficial da Receita e a IA sugerem; o contador decide.")

with st.sidebar:
    st.header("Como a IA entra")
    modo = MODOS[st.radio("Etapa de classificação", list(MODOS))]
    st.caption("Simulada: respostas reais do Gemini gravadas para o cadastro de exemplo e os casos T1 a T6. "
               "Manual: você cola o prompt num chat de IA. Integrada: chamada automática com GEMINI_API_KEY.")
    with st.expander("O que entra e o que sai de cada integração"):
        st.markdown("- **IA (Gemini):** entra a descrição e o NCM de cada produto; sai uma sugestão de "
                    "enquadramento com confiança e justificativa. Quem responde pela decisão é o contador.\n"
                    "- **Tabela oficial da Receita:** arquivo local extraído da calculadora oficial; o sistema "
                    "consulta, não envia nada.\n"
                    "- **ERP do cliente:** ainda **manual**: o contador exporta o cadastro (CSV/Excel) ou os XMLs "
                    "e envia aqui. O conector direto (Omie) é a próxima etapa.")
    o = origem()
    st.divider()
    st.caption(f"Tabela oficial: ReceitaFederal/calculadora-rtc-regime-regular, commit {o['commit'][:7]} "
               f"({o['data_commit'][:10]}). Sem efeito normativo.")

aba_lote, aba_produto = st.tabs(["📦 Cadastro do cliente (lote)", "🔎 Um produto, passo a passo"])


# =========================================================================== LOTE
def _carregar_lote(arquivos, usar_exemplo):
    linhas, falhas = [], []
    if arquivos:
        xmls = [(a.name, a.getvalue()) for a in arquivos if a.name.lower().endswith(".xml")]
        for a in arquivos:
            if a.name.lower().endswith(".xml"):
                continue
            try:
                linhas += lt.ler_planilha(a.getvalue(), a.name)
            except Exception as erro:  # noqa: BLE001 - planilha ruim vira mensagem, o resto segue
                falhas.append(f"{a.name}: {erro}")
        if xmls:
            de_xml, f = lt.ler_xmls(xmls)
            linhas += de_xml
            falhas += f
    elif usar_exemplo:
        linhas = lt.ler_planilha(lt.CADASTRO_EXEMPLO.read_bytes(), lt.CADASTRO_EXEMPLO.name)
    return linhas, falhas


def _classificar(itens, modo, resposta=None):
    with st.spinner("Analisando o cadastro: verificação, IA e tabela oficial..."):
        st.session_state.lote_avisos = lt.classificar_lote(itens, modo, resposta)
    st.session_state.lote_classificado = True
    st.session_state.lote_versao += 1


def _linha_fila(i):
    """Uma linha da tabela de revisão. As colunas que o contador mexe vêm primeiro."""
    s = i.sugestao
    return {
        "nº": i.id, "produto": i.descricao,
        "NCM": formatar_ncm(i.ncm) if i.ncm else (i.ncm_informado or "(vazio)"),
        "sugestão da IA": s.enquadramento if s else "",
        "aceitar sugestão": False, "decisão": i.decisao or None, "cClassTrib": i.cclasstrib,
        "por que está na fila": i.motivo,
        "confiança": s.confianca if s else "",
        "tabela oficial": i.conferencia.situacao if i.conferencia else "",
        "observação": i.observacao, "código": i.codigo,
    }


COLUNAS_EDITAVEIS = {
    "aceitar sugestão": st.column_config.CheckboxColumn(help="Marque para aceitar a sugestão da IA sem escolher"),
    "decisão": st.column_config.SelectboxColumn(options=list(lt.DECISOES), help="Enquadramento final"),
    "cClassTrib": st.column_config.TextColumn(help="Em branco: o sistema preenche pela tabela oficial"),
    "observação": st.column_config.TextColumn(),
    "produto": st.column_config.TextColumn(width="medium"),
    "por que está na fila": st.column_config.TextColumn(width="large"),
}


with aba_lote:
    st.markdown("Envie o **cadastro de produtos** exportado do ERP (CSV ou Excel, com as colunas código, descrição "
                "e NCM) ou os **XMLs das notas**. O que a tabela oficial e a IA confirmam é aprovado sozinho; "
                "você revisa só a fila e baixa a planilha com o cClassTrib de cada produto.")
    c1, c2 = st.columns([3, 2])
    arquivos = c1.file_uploader("Cadastro (CSV/XLSX) ou XMLs de NF-e", type=["csv", "xlsx", "xml"],
                                accept_multiple_files=True)
    usar_exemplo = c2.checkbox("Usar o cadastro de exemplo (distribuidora fictícia, 34 produtos)",
                               value=True, disabled=bool(arquivos))
    with c2:
        st.download_button("Baixar o modelo da planilha", lt.CADASTRO_EXEMPLO.read_bytes(),
                           file_name="cadastro-exemplo.csv", mime="text/csv")

    if st.button("Sugerir enquadramento do cadastro", type="primary"):
        linhas, falhas = _carregar_lote(arquivos, usar_exemplo)
        itens = lt.preparar(linhas)
        st.session_state.lote = itens
        st.session_state.lote_falhas = falhas
        st.session_state.lote_avisos = []
        st.session_state.lote_classificado = False
        st.session_state.lote_versao += 1
        if itens and modo != "MANUAL":
            _classificar(itens, modo)

    itens = st.session_state.get("lote")
    for f in st.session_state.get("lote_falhas", []):
        st.error(f"Arquivo não lido: {f}")

    if itens is not None and not itens:
        st.warning("Nenhum produto encontrado nos arquivos enviados.")

    if itens and modo == "MANUAL" and not st.session_state.get("lote_classificado"):
        st.subheader("Classificação pela IA (modo manual)")
        validos = sum(1 for i in itens if i.entrada)
        st.info(f"{len(itens)} produtos lidos; {validos} vão para a IA (os demais já foram barrados na verificação). "
                "Copie o prompt (ícone no canto do quadro), cole num chat de IA e cole a resposta abaixo.")
        st.code(lt.montar_prompt_lote(itens), language=None)
        resposta = st.text_area("Resposta da IA (uma linha por produto)", height=200,
                                placeholder="1 | ALIQUOTA_ZERO | alta | ...")
        if st.button("Conferir respostas"):
            _classificar(itens, "MANUAL", resposta)
            st.rerun()

    if itens and st.session_state.get("lote_classificado"):
        por_id = {i.id: i for i in itens}
        v = st.session_state.lote_versao
        fila = [i for i in itens if i.status == lt.REVISAR]
        automaticos = [i for i in itens if i.status == lt.AUTOMATICO]

        for a in st.session_state.get("lote_avisos", []):
            st.warning(a)

        # Fila de revisão ------------------------------------------------------------------
        st.subheader(f"Fila de revisão · {len(fila)} item(ns)")
        erros = []
        if fila:
            st.caption("Para cada item, marque **aceitar sugestão** ou escolha a **decisão**. "
                       "O cClassTrib em branco é preenchido pela tabela oficial.")
            editado = st.data_editor(
                [_linha_fila(i) for i in fila], key=f"fila_{v}", hide_index=True, width="stretch",
                column_config=COLUNAS_EDITAVEIS,
                disabled=["nº", "código", "produto", "NCM", "sugestão da IA", "confiança", "tabela oficial",
                          "por que está na fila"])
            erros += lt.aplicar_linhas(editado, por_id)
        else:
            st.success("Nada na fila: tudo foi confirmado pela tabela oficial e pela IA.")

        # Aprovados automaticamente ----------------------------------------------------------
        with st.expander(f"Aprovados automaticamente · {len(automaticos)} item(ns) (abra para conferir ou mudar)"):
            st.caption("Tabela oficial e IA de acordo, com confiança alta e um único cClassTrib. "
                       "Para mudar, troque a decisão ou o cClassTrib: o item passa a constar como decidido pelo contador.")
            if automaticos:
                linhas_auto = [{**_linha_fila(i), "decisão": i.sugestao.enquadramento,
                                "cClassTrib": lt.escolher_cclasstrib(i.sugestao.enquadramento, i.candidatos)[0]}
                               for i in automaticos]
                for linha in linhas_auto:
                    linha.pop("por que está na fila")
                    linha.pop("aceitar sugestão")
                editado_auto = st.data_editor(
                    linhas_auto, key=f"auto_{v}", hide_index=True, width="stretch",
                    column_config=COLUNAS_EDITAVEIS,
                    disabled=["nº", "código", "produto", "NCM", "sugestão da IA", "confiança", "tabela oficial"])
                erros += lt.aplicar_linhas(editado_auto, por_id)

        for e in erros:
            st.error(e)

        # Resultado e exportação -------------------------------------------------------------
        r = lt.resumo(itens)
        st.subheader("Resultado")
        m = st.columns(4)
        m[0].metric("Produtos", r["itens"])
        m[1].metric("Aprovados automaticamente", r["automáticos"])
        m[2].metric("Decididos pelo contador", r["revisados"])
        m[3].metric("Pendentes", r["pendentes"])
        if r["itens"]:
            st.progress((r["itens"] - r["pendentes"]) / r["itens"],
                        text=f"{r['itens'] - r['pendentes']} de {r['itens']} produtos com enquadramento e cClassTrib")
        st.download_button("Baixar a planilha com o cClassTrib", lt.exportar_csv(itens),
                           file_name="enquadramento-cclasstrib.csv", mime="text/csv", type="primary",
                           disabled=r["pendentes"] > 0)
        if r["pendentes"]:
            st.caption(f"A planilha libera quando a fila zerar (faltam {r['pendentes']}). "
                       "Nenhum enquadramento sai sem passar pela tabela oficial e IA de acordo, ou pelo contador.")
        with st.expander("Ver a planilha que será exportada"):
            st.dataframe([{"código": i.codigo, "produto": i.descricao, "NCM": formatar_ncm(i.ncm) if i.ncm else "",
                           "enquadramento": i.decisao, "cClassTrib": i.cclasstrib,
                           "tratamento": lt.descricao_cclasstrib(i)[0], "decidido por": i.decidido_por or "pendente"}
                          for i in itens], width="stretch", hide_index=True)


# =========================================================================== UM PRODUTO
with aba_produto:
    with st.expander("Carregar um caso de teste (Aula 3) ou um item de NF-e"):
        colunas = st.columns(3)
        for n, (id_, tipo, desc, ncm_caso, esperado) in enumerate(CASOS_DE_TESTE):
            if colunas[n % 3].button(f"{id_} · {tipo}: {desc[:28]}", key=f"caso_{id_}", width="stretch"):
                st.session_state.descricao, st.session_state.ncm = desc, ncm_caso
                st.session_state.pop("resultado", None)
        xml = st.file_uploader("XML da NF-e", type="xml", key="xml_um")
        if xml is None and st.checkbox("Usar a NF-e sintética de exemplo"):
            xml = Path(__file__).parent / "tests" / "fixtures" / "nfe-sintetica.xml"
        if xml is not None:
            try:
                itens_nfe = ler_nfe(xml).itens
                item = st.selectbox("Item da nota", itens_nfe, format_func=lambda i: f"{i.numero}. {i.descricao}")
                if st.button("Usar este item", width="stretch"):
                    st.session_state.descricao, st.session_state.ncm = item.descricao, item.ncm
                    st.session_state.pop("resultado", None)
            except Exception as erro:  # noqa: BLE001 - XML ruim não pode derrubar a tela
                st.error(f"Não consegui ler o XML: {erro}")

    # 1. Entrada -----------------------------------------------------------------------
    st.subheader("1 · Produto")
    c1, c2 = st.columns([3, 1])
    descricao = c1.text_input("Descrição do produto (obrigatório)", key="descricao",
                              placeholder="Ex.: Arroz branco tipo 1, pacote 5 kg",
                              help="Escreva como está no cadastro do cliente. Exemplo fictício: Feijão carioca 1 kg.")
    ncm = c2.text_input("NCM (recomendado)", key="ncm", placeholder="1006.30.21",
                        help="8 dígitos, com ou sem pontos. Sem NCM, o caso tende a ir para a revisão do contador.")
    enviar = st.button("Sugerir enquadramento", type="primary")

    if enviar:
        st.session_state.pop("resultado", None)
        # 2. Verificação (antes da IA) ---------------------------------------------------
        verif = verificar_entrada(descricao, ncm)
        st.session_state.verificacao = verif
        if verif.ok and modo != "MANUAL":
            try:
                with st.spinner("Analisando o produto..."):
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
                    st.error(f"IA indisponível: {st.session_state.falha_ia}. Nada foi sugerido. "
                             "Tente de novo ou use o modo Manual na barra lateral.")

        sug = st.session_state.get("resultado")
        conf = st.session_state.get("conferencia")
        if verif.ok and sug is not None and conf is not None:
            st.subheader("4 · Conferência com a tabela oficial da Receita")
            aviso = {"CONFERE": st.success, "DIVERGE": st.error, "ATENCAO": st.warning}.get(conf.situacao, st.info)
            aviso(f"**{conf.situacao}** · {conf.mensagem}")
            if conf.candidatos:
                st.dataframe([{"cClassTrib": c.cclasstrib, "anexo": c.anexo, "redução": f"{c.reducao_pct:.0f}%",
                               "tratamento": c.descricao, "NCM na tabela": c.ncm_prefixo} for c in conf.candidatos],
                             width="stretch", hide_index=True)
            st.caption(f"Fonte: calculadora oficial da Receita (ReceitaFederal/calculadora-rtc-regime-regular, "
                       f"commit {o['commit'][:7]}, vigência em {o['vigencia_em']}). Sem efeito normativo.")

        if verif.ok and sug is not None:
            st.subheader("5 · Sugestão para o contador")
            st.markdown(f"### :{CORES[sug.enquadramento]}[{sug.enquadramento}]")
            st.caption(ROTULOS[sug.enquadramento])
            st.info("Situação: **sugestão da IA, aguardando conferência do contador**. Ainda não é decisão.")
            m1, m2 = st.columns(2)
            m1.metric("Confiança", sug.confianca)
            m2.metric("Origem da sugestão", sug.origem)
            st.write(f"**Justificativa:** {sug.justificativa}")
            for a in sug.alertas:
                st.warning(a)
            if sug.precisa_revisao:
                st.warning("Caso que pede análise do contador (não é erro do sistema): a IA ou a tabela oficial "
                           "não deram segurança para sugerir um enquadramento. Escolha a decisão abaixo.")
            with st.expander("Resposta bruta da IA"):
                st.code(sug.resposta_bruta or "(vazia)", language=None)

            # 6. Decisão humana -----------------------------------------------------------
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
                st.success(f"Decisão confirmada pelo contador: {decisao}.")

    if st.session_state.historico:
        st.divider()
        st.subheader("Decisões desta sessão")
        st.dataframe(st.session_state.historico, width="stretch", hide_index=True)
