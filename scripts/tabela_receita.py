"""Extrai da calculadora oficial da Receita a tabela "NCM → tratamento com redução de alíquota".

Fonte: github.com/ReceitaFederal/calculadora-rtc-regime-regular (licença MIT, Portaria Cotec nº 342/2026).
O banco da calculadora é gerado pelas migrações SQL do Flyway; aqui elas são aplicadas direto no SQLite,
em memória, sem precisar de Java.

Uso:
    git clone --depth 1 https://github.com/ReceitaFederal/calculadora-rtc-regime-regular.git /tmp/rfb
    python scripts/tabela_receita.py /tmp/rfb            # grava dados/receita/*.csv e origem.json
"""

import csv
import glob
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path

DESTINO = Path(__file__).resolve().parent.parent / "dados" / "receita"
CBS = 2  # TBTO_ID da CBS; o percentual de redução é o mesmo para CBS e IBS nesses tratamentos


def montar_banco(clone: Path) -> sqlite3.Connection:
    sql_dir = clone / "flyway" / "sql"
    arquivos = [sql_dir / "criacao" / "B0001__sistema_tributario_completo.sql"]
    arquivos += sorted((Path(p) for p in glob.glob(str(sql_dir / "manutencao" / "V*.sql"))),
                       key=lambda p: int(p.name[1:5]))
    con = sqlite3.connect(":memory:", isolation_level=None)
    for arquivo in arquivos:
        # As migrações reescrevem tabelas em ordem que o Flyway tolera; a integridade é conferida no fim.
        sql = re.sub(r"(?im)^\s*PRAGMA\s+foreign_keys\s*=\s*ON\s*;", "", arquivo.read_text(encoding="utf-8"))
        con.execute("PRAGMA foreign_keys=OFF")
        con.executescript(sql)
    violacoes = con.execute("PRAGMA foreign_key_check").fetchall()
    if violacoes:
        raise SystemExit(f"Base inconsistente: {len(violacoes)} violações de chave estrangeira")
    return con, len(arquivos)


def main(clone: str) -> None:
    clone = Path(clone)
    con, n_migracoes = montar_banco(clone)
    hoje = date.today().isoformat()
    vigente = "({c}_INICIO_VIGENCIA <= :hoje AND ({c}_FIM_VIGENCIA IS NULL OR {c}_FIM_VIGENCIA >= :hoje))"

    linhas = con.execute(f"""
        SELECT n.NCMA_ID, n.NCMA_NCM_CD, ct.CLTR_CD, ct.CLTR_DESCRICAO, a.ANXO_NUMERO, p.PERE_VALOR
        FROM NCM_APLICAVEL n
        JOIN CLASSIFICACAO_TRIBUTARIA ct ON ct.CLTR_ID = n.NCMA_CLTR_ID
        JOIN PERCENTUAL_REDUCAO p ON p.PERE_CLTR_ID = ct.CLTR_ID AND p.PERE_TBTO_ID = {CBS}
        LEFT JOIN ANEXO a ON a.ANXO_ID = n.NCMA_ANXO_ID
        WHERE {vigente.format(c='n.NCMA')} AND {vigente.format(c='p.PERE')}
        ORDER BY n.NCMA_NCM_CD, ct.CLTR_CD""", {"hoje": hoje}).fetchall()
    ids = {l[0] for l in linhas}
    excecoes = [e for e in con.execute(f"""
        SELECT ENCM_NCMA_ID, ENCM_NCM_CD FROM EXCECAO_NCM_APLICAVEL e
        WHERE {vigente.format(c='e.ENCM')} ORDER BY 1, 2""", {"hoje": hoje}) if e[0] in ids]

    DESTINO.mkdir(parents=True, exist_ok=True)
    with open(DESTINO / "ncm_tratamento.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ncma_id", "ncm_prefixo", "cclasstrib", "descricao", "anexo", "reducao_pct"])
        w.writerows(linhas)
    with open(DESTINO / "ncm_excecao.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ncma_id", "ncm_prefixo_excluido"])
        w.writerows(excecoes)

    commit = subprocess.run(["git", "-C", str(clone), "log", "-1", "--format=%H %cI"],
                            capture_output=True, text=True).stdout.split()
    (DESTINO / "origem.json").write_text(json.dumps({
        "repositorio": "https://github.com/ReceitaFederal/calculadora-rtc-regime-regular",
        "commit": commit[0] if commit else None,
        "data_commit": commit[1] if len(commit) > 1 else None,
        "migracoes_aplicadas": n_migracoes,
        "vigencia_em": hoje,
        "linhas_ncm": len(linhas),
        "linhas_excecao": len(excecoes),
        "licenca": "MIT",
        "aviso": "Código e dados sem efeito normativo (Portaria Cotec nº 342/2026). Conferir a LC 214/2025.",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(linhas)} linhas, {len(excecoes)} exceções → {DESTINO}")


if __name__ == "__main__":
    if len(sys.argv) != 2 or not os.path.isdir(sys.argv[1]):
        raise SystemExit(__doc__)
    main(sys.argv[1])
