# pipeline/01_import_empresas.py
# Etapa 1 — Importa os dados de EMPRESAS da Receita Federal para o DuckDB
#
# Fonte: https://dadosabertos.rfb.gov.br/CNPJ/
# Os arquivos têm nomes como: *EMPRECSV*
# Não possuem cabeçalho e usam encoding latin-1

import duckdb
from pathlib import Path
import sys

# ── Caminhos relativos ao projeto ──────────────────────────────────────────
CSV_DIR = Path("data/rf_cnpj_csv")   # onde ficam os CSVs da Receita Federal
DB_PATH = Path("db/cnpj.duckdb")     # banco DuckDB compartilhado por todos os scripts

def sql_list(files):
    """Formata a lista de arquivos no padrão que o DuckDB aceita."""
    return "[" + ",".join("'" + f.replace("'", "''") + "'" for f in files) + "]"

def main():
    # Busca todos os arquivos de empresas na pasta
    emp_files = sorted([str(p) for p in CSV_DIR.glob("*EMPRECSV*")])

    if not emp_files:
        raise RuntimeError(f"Nenhum arquivo *EMPRECSV* encontrado em {CSV_DIR}")

    print(f"📂 {len(emp_files)} arquivo(s) encontrado(s)")

    # Garante que a pasta do banco existe
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(DB_PATH))
    con.execute("PRAGMA threads=4;")  # ajuste conforme seu CPU


    files_sql = sql_list(emp_files)

    print("⏳ Importando empresas... (pode demorar alguns minutos)")

    con.execute("DROP TABLE IF EXISTS empresas;")
    con.execute(f"""
        CREATE TABLE empresas AS
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

    total = con.execute("SELECT COUNT(*) FROM empresas").fetchone()[0]
    print(f"✅ Empresas importadas: {total:,} registros")

    con.close()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ ERRO: {e}")
        sys.exit(1)