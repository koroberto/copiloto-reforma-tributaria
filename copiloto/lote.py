"""Processamento de um cadastro inteiro (lote): o uso do dia a dia do contador.

Fluxo: planilha do cadastro ou XMLs de NF-e → verificação de cada item → IA num prompt só (ou uma
chamada por bloco) → conferência com a tabela oficial → aprovação automática quando a tabela e a IA
concordam → fila de revisão do contador só com o resto → planilha com o cClassTrib de cada produto.

Regra da aprovação automática: categoria da IA confirmada pela tabela oficial (CONFERE), confiança
alta, resposta sem alertas e um único cClassTrib possível. Todo o resto vai para a fila.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from copiloto.enquadramento import (REGRAS_V3, Entrada, IAIndisponivel, Sugestao, chamar_gemini,
                                    classificar_simulado, conferir_resposta, formatar_ncm,
                                    verificar_entrada)
from copiloto.nfe import ler_nfe
from copiloto.tabela_oficial import (CCLASSTRIB_PADRAO, DEPENDE_DA_OPERACAO, Conferencia, Tratamento,
                                     candidatos, conferir, fora_da_tabela)

AUTOMATICO, REVISAR = "AUTOMATICO", "REVISAR"
DECISOES = ("ALIQUOTA_ZERO", "REDUCAO_60", "PADRAO", "REGIME_ESPECIFICO")  # o contador não "decide revisão"
TAMANHO_BLOCO = 40  # itens por chamada no modo integrado

EXEMPLOS = Path(__file__).resolve().parent.parent / "exemplos"
CADASTRO_EXEMPLO = EXEMPLOS / "cadastro-distribuidora-ficticia.csv"
RESPOSTA_EXEMPLO = EXEMPLOS / "resposta-gemini-cadastro-exemplo.txt"

FORMATO_LOTE = """
Você vai receber uma lista numerada de produtos. Responda com uma linha por produto, na mesma ordem, sem nenhum texto antes ou depois, sem tabela e sem markdown, neste formato:
número | enquadramento | confianca | justificativa
- enquadramento: uma das opções acima
- confianca: alta, media ou baixa; em REVISAO_HUMANA use sempre baixa
- justificativa: uma frase curta baseada na descrição e no NCM
Produtos:
{produtos}"""


@dataclass
class ItemLote:
    id: int
    codigo: str
    descricao: str
    ncm_informado: str
    entrada: Entrada | None = None
    erros: list[str] = field(default_factory=list)
    observacao: str = ""
    sugestao: Sugestao | None = None
    conferencia: Conferencia | None = None
    status: str = REVISAR
    motivo: str = ""
    # decisão final (automática ou do contador); vazia enquanto o item está na fila
    decisao: str = ""
    cclasstrib: str = ""
    decidido_por: str = ""

    @property
    def ncm(self) -> str:
        return self.entrada.ncm if self.entrada else ""

    @property
    def candidatos(self) -> list[Tratamento]:
        return self.conferencia.candidatos if self.conferencia else candidatos(self.ncm)


# ---------------------------------------------------------------- 1. leitura do cadastro

COLUNAS = {
    "codigo": ("codigo", "cod", "sku", "cprod", "codigo do produto", "cod produto", "referencia", "ref"),
    "descricao": ("descricao", "produto", "nome", "descricao do produto", "nome do produto", "xprod"),
    "ncm": ("ncm", "codigo ncm", "ncm/sh", "classificacao fiscal"),
}


def _chave(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9/ ]", " ", texto).split())


def _decodificar(conteudo: bytes) -> str:
    try:
        return conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        return conteudo.decode("cp1252")  # exportação comum de ERP no Windows


def _linhas_xlsx(conteudo: bytes) -> list[list[str]]:
    from openpyxl import load_workbook

    planilha = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True).worksheets[0]
    linhas = []
    for linha in planilha.iter_rows(values_only=True):
        linhas.append(["" if v is None else str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)
                       for v in linha])
    return linhas


def ler_planilha(conteudo: bytes, nome: str) -> list[dict]:
    """Lê o cadastro exportado do ERP (CSV ou XLSX). Acha as colunas pelo nome, em qualquer ordem."""
    if nome.lower().endswith((".xlsx", ".xlsm")):
        linhas = _linhas_xlsx(conteudo)
    else:
        texto = _decodificar(conteudo)
        # O separador é o que mais aparece no começo do arquivo. (O csv.Sniffer erra quando alguma linha
        # vem com menos colunas, o que é comum em exportação de ERP.)
        inicio = "\n".join(texto.splitlines()[:10])
        separador = max(";,\t", key=inicio.count)
        linhas = list(csv.reader(io.StringIO(texto), delimiter=separador))

    for pos, cabecalho in enumerate(linhas[:10]):
        nomes = [_chave(c) for c in cabecalho]
        indice = {campo: next((i for i, n in enumerate(nomes) if n in apelidos), None)
                  for campo, apelidos in COLUNAS.items()}
        if indice["descricao"] is not None:
            break
    else:
        raise ValueError("Não achei a coluna de descrição do produto. Use um cabeçalho como "
                         "\"codigo;descricao;ncm\".")

    def valor(linha, campo):
        i = indice[campo]
        return linha[i].strip() if i is not None and i < len(linha) and linha[i] else ""

    itens = []
    for linha in linhas[pos + 1:]:
        item = {campo: valor(linha, campo) for campo in COLUNAS}
        if any(item.values()):
            itens.append(item)
    return itens


def ler_xmls(arquivos: list[tuple[str, bytes]]) -> tuple[list[dict], list[str]]:
    """Itens das NF-e, sem repetir o mesmo produto. XML ruim não para o lote: vira uma falha listada."""
    itens, vistos, falhas = [], set(), []
    for nome, conteudo in arquivos:
        try:
            nota = ler_nfe(io.BytesIO(conteudo))
        except Exception as erro:  # noqa: BLE001 - qualquer XML ruim vira mensagem
            falhas.append(f"{nome}: {erro}")
            continue
        for it in nota.itens:
            chave = (it.codigo or it.descricao.lower(), it.ncm)
            if chave not in vistos:
                vistos.add(chave)
                itens.append({"codigo": it.codigo, "descricao": it.descricao, "ncm": it.ncm})
    return itens, falhas


def preparar(linhas: list[dict]) -> list[ItemLote]:
    """Verifica cada item antes da IA (a mesma verificação do fluxo de um produto)."""
    itens = []
    for n, linha in enumerate(linhas, start=1):
        ncm, obs = linha.get("ncm", ""), ""
        digitos = re.sub(r"[.\-\s]", "", ncm)
        if re.fullmatch(r"\d{7}", digitos):
            ncm, obs = "0" + digitos, "NCM com 7 dígitos: completado com zero à esquerda (o Excel costuma tirar)."
        v = verificar_entrada(linha.get("descricao", ""), ncm)
        itens.append(ItemLote(n, linha.get("codigo", ""), linha.get("descricao", ""), linha.get("ncm", ""),
                              v.entrada, v.erros, obs))
    return itens


# ---------------------------------------------------------------- 2. IA em lote

def montar_prompt_lote(itens: list[ItemLote]) -> str:
    produtos = "\n".join(f'{i.id}. "{i.entrada.descricao}" | NCM: {formatar_ncm(i.entrada.ncm)}'
                         for i in itens if i.entrada)
    return REGRAS_V3 + FORMATO_LOTE.format(produtos=produtos)


_LINHA = re.compile(r"^\s*\|?\s*\**\s*(\d+)\s*[.)]?\s*\**\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(.+?)\s*\|?\s*$")


def ler_resposta_lote(texto: str, ids: set[int], origem: str) -> tuple[dict[int, Sugestao], list[str]]:
    """Uma linha por produto. Cada linha passa pela mesma conferência do fluxo de um produto."""
    achados: dict[int, Sugestao] = {}
    avisos = []
    for linha in (texto or "").splitlines():
        m = _LINHA.match(linha)
        if not m:
            continue
        n = int(m[1])
        if n not in ids or n in achados:
            avisos.append(f"Linha ignorada (item {n} {'repetido' if n in achados else 'fora da lista'}).")
            continue
        s = conferir_resposta(f"enquadramento: {m[2]}\nconfianca: {m[3]}\njustificativa: {m[4]}", origem)
        s.resposta_bruta = linha.strip()
        achados[n] = s
    faltando = sorted(ids - achados.keys())
    if faltando:
        lista = ", ".join(map(str, faltando[:15])) + (f" e mais {len(faltando) - 15}" if len(faltando) > 15 else "")
        avisos.append(f"A IA não respondeu {len(faltando)} item(ns) ({lista}). Eles foram para a fila.")
    return achados, avisos


def _gravadas_do_exemplo() -> dict[tuple[str, str], Sugestao]:
    """Resposta real do Gemini ao cadastro de exemplo, gravada para a demonstração (modo simulado)."""
    if not (CADASTRO_EXEMPLO.exists() and RESPOSTA_EXEMPLO.exists()):
        return {}
    itens = preparar(ler_planilha(CADASTRO_EXEMPLO.read_bytes(), CADASTRO_EXEMPLO.name))
    sugs, _ = ler_resposta_lote(RESPOSTA_EXEMPLO.read_text(encoding="utf-8"),
                                {i.id for i in itens if i.entrada}, "SIMULADA")
    return {(i.entrada.descricao.lower(), i.ncm): sugs[i.id] for i in itens if i.id in sugs}


def classificar_lote(itens: list[ItemLote], modo: str, resposta_manual: str | None = None,
                     chamar=chamar_gemini) -> list[str]:
    """Preenche a sugestão de cada item e decide o que é automático e o que vai para a fila."""
    validos = [i for i in itens if i.entrada]
    avisos: list[str] = []
    if modo == "SIMULADA":
        gravadas = _gravadas_do_exemplo()
        for i in validos:
            try:
                i.sugestao = conferir_resposta(classificar_simulado(i.entrada), "SIMULADA")
            except IAIndisponivel:
                i.sugestao = gravadas.get((i.entrada.descricao.lower(), i.ncm))
        sem = sum(1 for i in validos if i.sugestao is None)
        if sem:
            avisos.append(f"{sem} item(ns) sem resposta simulada (só há gravação para o cadastro de exemplo e "
                          "os casos T1 a T6). Eles foram para a fila; use o modo manual ou o integrado.")
    elif modo == "MANUAL":
        sugs, avisos = ler_resposta_lote(resposta_manual or "", {i.id for i in validos}, "MANUAL")
        for i in validos:
            i.sugestao = sugs.get(i.id)
    else:  # INTEGRADA: um bloco por chamada; um bloco que falha não derruba o lote
        for ini in range(0, len(validos), TAMANHO_BLOCO):
            bloco = validos[ini:ini + TAMANHO_BLOCO]
            try:
                texto = chamar(montar_prompt_lote(bloco))
            except IAIndisponivel as erro:
                avisos.append(f"IA indisponível nos itens {bloco[0].id} a {bloco[-1].id}: {erro}")
                continue
            sugs, av = ler_resposta_lote(texto, {i.id for i in bloco}, "INTEGRADA")
            avisos += av
            for i in bloco:
                i.sugestao = sugs.get(i.id)
    for i in itens:
        decidir(i)
    return avisos


# ---------------------------------------------------------------- 3. decisão automática ou fila

def escolher_cclasstrib(categoria: str, cands: list[Tratamento]) -> tuple[str, str]:
    """Código cClassTrib da categoria para o NCM. Devolve (código, motivo quando não dá para escolher)."""
    if categoria == "PADRAO":
        return CCLASSTRIB_PADRAO[0], ""
    if categoria not in ("ALIQUOTA_ZERO", "REDUCAO_60"):
        return "", ""
    mesmos = [t for t in cands if t.categoria == categoria]
    codigos = sorted({t.cclasstrib for t in mesmos if not t.depende_da_operacao})
    if len(codigos) == 1:
        return codigos[0], ""
    if len(codigos) > 1:
        return "", f"Mais de um cClassTrib possível ({', '.join(codigos)}): escolha o que se aplica."
    if mesmos:
        return "", "O tratamento só vale numa operação específica: " + "; ".join(
            sorted({DEPENDE_DA_OPERACAO[t.cclasstrib] for t in mesmos})) + "."
    return "", "A tabela oficial não tem cClassTrib para esta categoria neste NCM."


def decidir(item: ItemLote) -> None:
    item.status, item.motivo, item.decisao, item.cclasstrib, item.decidido_por = REVISAR, "", "", "", ""
    if item.erros:
        item.motivo = "Entrada com problema: " + " ".join(item.erros)
        return
    if item.sugestao is None:
        cands = candidatos(item.ncm)
        item.motivo = "Sem sugestão da IA." + (
            f" A tabela oficial prevê para o NCM: {', '.join(sorted({f'Anexo {t.anexo}' for t in cands}))}."
            if cands else "")
        return

    item.sugestao, item.conferencia = conferir(item.sugestao, item.ncm)
    s, c = item.sugestao, item.conferencia
    codigo, motivo_codigo = escolher_cclasstrib(s.enquadramento, c.candidatos)

    if s.enquadramento == "REVISAO_HUMANA":
        item.motivo = (c.mensagem if c.situacao == "DIVERGE" else "A IA pediu revisão: " + s.justificativa)
        if c.situacao == "DIVERGE" and fora_da_tabela(item.ncm):
            item.motivo += " Atenção: " + fora_da_tabela(item.ncm) + "."
    elif s.enquadramento == "REGIME_ESPECIFICO":
        item.motivo = "Regime específico: a tabela usada não cobre; confira e informe o cClassTrib."
    elif c.situacao != "CONFERE":
        item.motivo = c.mensagem
    elif fora_da_tabela(item.ncm):
        item.motivo = "Confira o produto: " + fora_da_tabela(item.ncm) + "."
    elif s.confianca != "alta":
        item.motivo = f"A IA ficou com confiança {s.confianca}."
    elif s.alertas:
        item.motivo = " ".join(s.alertas)
    elif not codigo:
        item.motivo = motivo_codigo
    else:
        item.status, item.decisao, item.cclasstrib, item.decidido_por = AUTOMATICO, s.enquadramento, codigo, "automático"
        item.motivo = "Tabela oficial e IA de acordo."


def aplicar_decisao(item: ItemLote, decisao: str, cclasstrib: str = "", observacao: str | None = None) -> str | None:
    """Decisão do contador para um item. Devolve uma mensagem de erro, ou None se a decisão valeu."""
    if observacao is not None:
        item.observacao = observacao
    if decisao not in DECISOES:
        item.decisao = item.cclasstrib = item.decidido_por = ""
        return "Escolha o enquadramento."
    cclasstrib = (cclasstrib or "").strip() or escolher_cclasstrib(decisao, item.candidatos)[0]
    if decisao in ("ALIQUOTA_ZERO", "REDUCAO_60") and not re.fullmatch(r"\d{6}", cclasstrib):
        item.decisao = item.cclasstrib = item.decidido_por = ""
        return "Informe o cClassTrib (6 dígitos) para a redução."
    if decisao == "PADRAO" and cclasstrib != CCLASSTRIB_PADRAO[0]:
        item.decisao = item.cclasstrib = item.decidido_por = ""
        return f"Para PADRAO o cClassTrib é {CCLASSTRIB_PADRAO[0]}."
    automatico = item.status == AUTOMATICO and decisao == item.sugestao.enquadramento and \
        cclasstrib == escolher_cclasstrib(decisao, item.candidatos)[0]
    item.decisao, item.cclasstrib = decisao, cclasstrib
    item.decidido_por = "automático" if automatico else "contador"
    return None


def aplicar_linhas(linhas: list[dict], por_id: dict[int, ItemLote]) -> list[str]:
    """Aplica as linhas da tabela de revisão (colunas nº, aceitar sugestão, decisão, cClassTrib, observação).

    "Aceitar sugestão" vale como decisão quando a decisão está em branco. Linha sem decisão deixa o item pendente.
    Devolve os erros por item.
    """
    erros = []
    for linha in linhas:
        item = por_id[linha["nº"]]
        decisao = linha.get("decisão") or ""
        obs = linha.get("observação") or ""
        aceitar = bool(linha.get("aceitar sugestão"))
        if not decisao and aceitar and item.sugestao:
            decisao = item.sugestao.enquadramento
        if not decisao:
            item.decisao = item.cclasstrib = item.decidido_por = ""
            item.observacao = obs
            if aceitar:
                erros.append(f"Item {item.id}: não há sugestão da IA para aceitar; escolha a decisão.")
            continue
        if decisao not in DECISOES:
            item.decisao = item.cclasstrib = item.decidido_por = ""
            item.observacao = obs
            erros.append(f"Item {item.id}: a sugestão da IA foi {decisao}; escolha a decisão.")
            continue
        erro = aplicar_decisao(item, decisao, linha.get("cClassTrib") or "", obs)
        if erro:
            erros.append(f"Item {item.id}: {erro}")
    return erros


# ---------------------------------------------------------------- 4. saída

def descricao_cclasstrib(item: ItemLote) -> tuple[str, str]:
    """(descrição do cClassTrib, anexo) para a planilha."""
    if item.cclasstrib == CCLASSTRIB_PADRAO[0]:
        return CCLASSTRIB_PADRAO[1], ""
    for t in item.candidatos:
        if t.cclasstrib == item.cclasstrib:
            return t.descricao, t.anexo
    return "", ""


def resumo(itens: list[ItemLote]) -> dict[str, int]:
    return {
        "itens": len(itens),
        "automáticos": sum(1 for i in itens if i.decidido_por == "automático"),
        "revisados": sum(1 for i in itens if i.decidido_por == "contador"),
        "pendentes": sum(1 for i in itens if not i.decisao),
    }


def exportar_csv(itens: list[ItemLote]) -> bytes:
    """Planilha para o cliente cadastrar no ERP (ponto e vírgula e BOM: abre direto no Excel)."""
    saida = io.StringIO()
    w = csv.writer(saida, delimiter=";")
    w.writerow(["codigo", "descricao", "ncm", "enquadramento", "cclasstrib", "descricao_cclasstrib", "anexo",
                "decidido_por", "sugestao_ia", "confianca_ia", "tabela_oficial", "motivo_revisao", "observacao"])
    for i in itens:
        desc, anexo = descricao_cclasstrib(i)
        w.writerow([i.codigo, i.descricao, formatar_ncm(i.ncm) if i.ncm else i.ncm_informado, i.decisao,
                    i.cclasstrib, desc, anexo, i.decidido_por or "pendente",
                    i.sugestao.enquadramento if i.sugestao else "", i.sugestao.confianca if i.sugestao else "",
                    i.conferencia.situacao if i.conferencia else "", "" if i.status == AUTOMATICO else i.motivo,
                    i.observacao])
    return saida.getvalue().encode("utf-8-sig")
