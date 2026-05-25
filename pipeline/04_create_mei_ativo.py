# pipeline/04_create_mei_ativo.py
# Etapa 4 — Constrói a tabela mei_ativo cruzando empresas + estabelecimentos + simples
#
# Lógica:
#   MEI ativo = empresas que estão no Simples com opcaoMEI = 'S'
#               E têm situação cadastral ATIVA nos estabelecimentos
#
# Resultado: tabela mei_ativo com CNPJ, razão social, UF, município e CNAE
# Esta tabela é a base para cruzar com os contratos do PNCP (script 06)
#
# ⚠️ Pré-requisito: scripts 01, 02 e 03 já executados com sucesso
#
# ⚠️ Atenção sobre nomes de colunas:
#   Os arquivos da RFB não têm cabeçalho. O DuckDB gera nomes automáticos
#   que variam conforme o número de colunas de cada arquivo:
#   - empresas e simples   → column0, column1, column2...
#   - estabelecimentos     → column00, column01, column02...

import duckdb
from pathlib import Path
import sys

# ── Caminhos ───────────────────────────────────────────────────────────────
DB_PATH = Path("db/cnpj.duckdb")

# Código de situação cadastral ativa na RFB
# ⚠️ Atenção: o valor vem como '2' sem zero à esquerda
SITUACAO_ATIVA = "2"

# ── Main ───────────────────────────────────────────────────────────────────
def main():
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"❌ Banco não encontrado: {DB_PATH}\n"
            f"   Execute primeiro os scripts 01, 02 e 03."
        )

    con = duckdb.connect(str(DB_PATH))
    con.execute("PRAGMA threads=2;")

    # Verifica se as 3 tabelas de origem existem
    tabelas = ["empresas", "estabelecimentos", "simples"]
    for t in tabelas:
        existe = con.execute(
            f"SELECT COUNT(*) FROM information_schema.tables WHERE table_name = '{t}'"
        ).fetchone()[0]
        if not existe:
            raise RuntimeError(
                f"❌ Tabela '{t}' não encontrada no banco.\n"
                f"   Execute o script correspondente antes deste."
            )

    print("⏳ Construindo tabela mei_ativo...")
    print("   (cruza empresas + estabelecimentos + simples)")

    # ── Mapeamento das colunas por tabela ──────────────────────────────────
    #
    # EMPRESAS (column0, column1...):
    #   column0 = CNPJ_BASICO
    #   column1 = RAZAO_SOCIAL
    #
    # ESTABELECIMENTOS (column00, column01...):
    #   column00 = CNPJ_BASICO
    #   column05 = CNPJ_ORDEM
    #   column06 = CNPJ_DV
    #   column03 = SITUACAO_CADASTRAL (valores: 1=Nula, 2=Ativa, 3=Suspensa, 4=Inapta, 8=Baixada)
    #   column11 = CNAE_FISCAL_PRINCIPAL
    #   column19 = UF
    #   column20 = MUNICIPIO
    #
    # SIMPLES (column0, column1...):
    #   column0 = CNPJ_BASICO
    #   column1 = OPCAO_SIMPLES
    #   column4 = OPCAO_MEI  ← corrigido (era column3)

    con.execute("DROP TABLE IF EXISTS mei_ativo;")
    con.execute(f"""
        CREATE TABLE mei_ativo AS
        SELECT
            -- Monta CNPJ completo de 14 dígitos (basico + ordem + dv)
            lpad(CAST(e.column0    AS VARCHAR), 8, '0') ||
            lpad(right(CAST(est.column05 AS VARCHAR), 4), 4, '0') ||
            lpad(right(CAST(est.column06 AS VARCHAR), 2), 2, '0')  AS CNPJ,


            e.column1                                     AS RAZAO_SOCIAL,
            est.column19                                  AS UF,
            est.column20                                  AS MUNICIPIO,
            est.column11                                  AS CNAE_PRINCIPAL,
            est.column03                                  AS SITUACAO_CADASTRAL,
            'S'                                           AS FLAG_MEI

        FROM simples s
        -- Junta com empresas pelo CNPJ básico (8 dígitos)
        JOIN empresas e
          ON lpad(CAST(s.column0 AS VARCHAR), 8, '0') =
             lpad(CAST(e.column0 AS VARCHAR), 8, '0')
        -- Junta com estabelecimentos pelo CNPJ básico
        JOIN estabelecimentos est
          ON lpad(CAST(s.column0 AS VARCHAR), 8, '0') =
             lpad(CAST(est.column00 AS VARCHAR), 8, '0')

        WHERE
            -- Só MEI (opcaoMEI = 'S') — coluna correta é column4
            upper(trim(s.column4)) = 'S'
            -- Só situação ativa (valor '2' sem zero à esquerda)
            AND trim(est.column03) = '{SITUACAO_ATIVA}';
    """)

    total = con.execute("SELECT COUNT(*) FROM mei_ativo").fetchone()[0]

    # Índice para acelerar o JOIN com os contratos do PNCP (script 06)
    con.execute("CREATE INDEX IF NOT EXISTS idx_mei_ativo_cnpj ON mei_ativo(CNPJ);")

    # Amostra dos dados para conferência
    print("\n📋 Amostra dos primeiros registros:")
    amostra = con.execute("SELECT * FROM mei_ativo LIMIT 5").fetchdf()
    print(amostra.to_string(index=False))

    # Distribuição por UF
    print("\n📊 Top 10 UFs com mais MEIs ativos:")
    top_uf = con.execute("""
        SELECT UF, COUNT(*) AS total
        FROM mei_ativo
        GROUP BY UF
        ORDER BY total DESC
        LIMIT 10
    """).fetchdf()
    print(top_uf.to_string(index=False))

    con.close()

    print(f"\n✅ mei_ativo criada: {total:,} MEIs ativos encontrados")
    print("   Próximo passo: python pipeline/06_pncp_join_mei.py")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        sys.exit(1)