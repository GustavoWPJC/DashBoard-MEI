# pipeline/03_import_simples.py
# Etapa 3 — Importa os dados do Simples Nacional / MEI da Receita Federal
#
# Fonte: https://dadosabertos.rfb.gov.br/CNPJ/
# Arquivo com padrão: *SIMPLES*
# Contém: flag de opção pelo Simples e flag de opção pelo MEI (coluna chave: opcaoMEI = 'S')
#
# Esta tabela é a que identifica quais CNPJs são MEI de verdade.

import duckdb
from pathlib import Path
import sys

# ── Caminhos ───────────────────────────────────────────────────────────────
CSV_DIR = Path("data/rf_cnpj_csv")
DB_PATH = Path("db/cnpj.duckdb")

# ── Main ───────────────────────────────────────────────────────────────────
def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Busca o arquivo do Simples (normalmente é apenas 1)
    simples_files = sorted([str(p) for p in CSV_DIR.glob("*SIMPLES*")])

    if not simples_files:
        raise RuntimeError(f"Nenhum arquivo *SIMPLES* encontrado em {CSV_DIR}")

    print(f"📂 {len(simples_files)} arquivo(s) Simples encontrado(s)")

    con = duckdb.connect(str(DB_PATH))
    con.execute("PRAGMA threads=4;")

    # Monta lista de arquivos para o DuckDB ler de uma vez
    files_sql = "[" + ",".join(
        "'" + f.replace("'", "''") + "'" for f in simples_files
    ) + "]"

    print("⏳ Importando Simples Nacional / MEI...")

    con.execute("DROP TABLE IF EXISTS simples;")
    con.execute(f"""
        CREATE TABLE simples AS
        SELECT * FROM read_csv_auto(
            {files_sql},
            sep=';',
            header=false,
            encoding='latin-1',
            union_by_name=true,
            strict_mode=false,
            all_varchar=true,
            ignore_errors=true
        );
    """)

    total = con.execute("SELECT COUNT(*) FROM simples").fetchone()[0]
    print(f"✅ Simples importado: {total:,} registros")

    con.close()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        sys.exit(1)