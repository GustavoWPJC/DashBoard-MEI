# pipeline/02_import_estabelecimentos.py
# Etapa 2 — Importa os dados de ESTABELECIMENTOS da Receita Federal para o DuckDB
#
# Fonte: https://dadosabertos.rfb.gov.br/CNPJ/
# Arquivos com padrão: *ESTABELE*
# Contém: UF, município, situação cadastral, CNAE principal
#
# ⚠️ Atenção: os arquivos de estabelecimentos são os maiores da RFB
# (~10 arquivos de vários GBs). O script insere um a um para não estourar memória.
# A codificação pode variar — o script tenta latin-1, utf-16 e utf-8 automaticamente.

import duckdb
from pathlib import Path
import sys
import time

# ── Caminhos ───────────────────────────────────────────────────────────────
CSV_DIR = Path("data/rf_cnpj_csv")
DB_PATH = Path("db/cnpj.duckdb")

# Linhas de até 128MB (arquivos da RFB podem ter linhas muito longas)
MAX_LINE_BYTES = 134_217_728

ENCODINGS = ["latin-1", "utf-16", "utf-8"]  # ordem de tentativa

# ── Helpers ────────────────────────────────────────────────────────────────
def make_query(file_path: str, enc: str) -> str:
    """Monta o SELECT do DuckDB para um arquivo CSV sem header."""
    f = file_path.replace("'", "''")
    return f"""
        SELECT * FROM read_csv_auto(
            '{f}',
            sep=';',
            header=false,
            encoding='{enc}',
            union_by_name=true,
            strict_mode=false,
            all_varchar=true,
            ignore_errors=true,
            max_line_size={MAX_LINE_BYTES}
        )
    """

def criar_tabela(primeiro_arquivo: str):
    """
    Cria a tabela 'estabelecimentos' com o primeiro arquivo.
    Tenta cada encoding até um funcionar.
    """
    for enc in ENCODINGS:
        con = None
        try:
            con = duckdb.connect(str(DB_PATH))
            con.execute("PRAGMA threads=4;")
            con.execute("DROP TABLE IF EXISTS estabelecimentos;")
            con.execute(f"CREATE TABLE estabelecimentos AS {make_query(primeiro_arquivo, enc)};")
            con.close()
            print(f"   ✅ Tabela criada | {Path(primeiro_arquivo).name} | enc={enc}")
            return
        except Exception as e:
            if con:
                try: con.close()
                except: pass
            print(f"   ⚠️  Falhou (enc={enc}): {e}")
            time.sleep(0.3)
    raise RuntimeError("❌ Não foi possível criar a tabela estabelecimentos.")

def inserir_arquivo(file_path: str):
    """
    Insere um arquivo adicional na tabela já existente.
    Tenta cada encoding até um funcionar.
    """
    for enc in ENCODINGS:
        con = None
        try:
            con = duckdb.connect(str(DB_PATH))
            con.execute("PRAGMA threads=4;")
            con.execute(f"INSERT INTO estabelecimentos {make_query(file_path, enc)};")
            con.close()
            print(f"   ✅ Inserido | {Path(file_path).name} | enc={enc}")
            return
        except Exception as e:
            if con:
                try: con.close()
                except: pass
            print(f"   ⚠️  Falhou insert (enc={enc}): {e}")
            time.sleep(0.3)
    raise RuntimeError(f"❌ Não foi possível inserir: {file_path}")

# ── Main ───────────────────────────────────────────────────────────────────
def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    est_files = sorted([str(p) for p in CSV_DIR.glob("*ESTABELE*")])

    if not est_files:
        raise RuntimeError(f"Nenhum arquivo *ESTABELE* encontrado em {CSV_DIR}")

    print(f"📂 {len(est_files)} arquivo(s) de estabelecimentos encontrado(s)")

    # Cria a tabela com o primeiro arquivo
    print(f"\n⏳ Criando tabela com o primeiro arquivo...")
    criar_tabela(est_files[0])

    # Insere os demais
    for i, f in enumerate(est_files[1:], 2):
        print(f"\n⏳ Inserindo arquivo {i}/{len(est_files)}...")
        inserir_arquivo(f)

    # Contagem final
    con = duckdb.connect(str(DB_PATH))
    total = con.execute("SELECT COUNT(*) FROM estabelecimentos").fetchone()[0]
    con.close()

    print(f"\n✅ Estabelecimentos importados: {total:,} registros")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        sys.exit(1)