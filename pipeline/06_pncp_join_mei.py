# pipeline/06_pncp_join_mei.py
# Etapa 6 — Cruza os contratos do PNCP com a base de MEI ativo e gera os KPIs
#
# Pré-requisitos:
#   - db/cnpj.duckdb com a tabela mei_ativo (gerada pelo script 04)
#   - data/pncp_contratos_6m.jsonl (gerado pelo script 05)
#
# O que este script faz:
#   1. Carrega o JSONL no DuckDB (staging)
#   2. Carrega a tabela de descrição dos CNAEs
#   3. Normaliza o CNPJ do fornecedor
#   4. Filtra só contratos da esfera Federal (esferaId = 'F')
#   5. Cruza com a tabela mei_ativo pelo CNPJ
#   6. Gera 5 tabelas de KPIs prontas para os gráficos

from pathlib import Path
import duckdb

# ── Caminhos ───────────────────────────────────────────────────────────────
DB_PATH    = Path("db/cnpj.duckdb")
JSONL_PATH = Path("data/pncp_contratos_6m.jsonl")
CSV_DIR    = Path("data/rf_cnpj_csv")

def main():
    # Verificações iniciais
    if not JSONL_PATH.exists():
        raise FileNotFoundError(
            f"❌ Arquivo JSONL não encontrado: {JSONL_PATH}\n"
            f"   Execute primeiro: python pipeline/05_pncp_coleta_contratos.py"
        )
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"❌ Banco DuckDB não encontrado: {DB_PATH}\n"
            f"   Execute primeiro os scripts 01 a 04."
        )

    con = duckdb.connect(str(DB_PATH))
    con.execute("PRAGMA threads=4;")

    jsonl = str(JSONL_PATH).replace("'", "''")

    # ── ETAPA 1: Carrega o JSONL como tabela staging ───────────────────────
    print("⏳ Carregando JSONL no DuckDB...")
    con.execute("DROP TABLE IF EXISTS pncp_contratos_raw;")
    con.execute(f"""
        CREATE TABLE pncp_contratos_raw AS
        SELECT * FROM read_json_auto('{jsonl}');
    """)
    cnt_raw = con.execute("SELECT COUNT(*) FROM pncp_contratos_raw").fetchone()[0]
    print(f"   ✅ {cnt_raw:,} contratos carregados (raw)")

    # ── ETAPA 2: Carrega tabela de CNAEs ──────────────────────────────────
    # Traduz código numérico → descrição da atividade econômica
    # Ex: 4712100 → "Comércio varejista de mercadorias em geral"
    cnaes_files = sorted([str(p) for p in CSV_DIR.glob("*Cnaes*") if not str(p).endswith(".zip")])

    if cnaes_files:
        print("⏳ Carregando tabela de CNAEs...")
        con.execute("DROP TABLE IF EXISTS cnaes;")
        files_sql = "[" + ",".join("'" + f.replace("'", "''") + "'" for f in cnaes_files) + "]"
        con.execute(f"""
            CREATE TABLE cnaes AS
            SELECT
                column0 AS codigo,
                column1 AS descricao
            FROM read_csv_auto(
                {files_sql},
                sep=';',
                header=false,
                encoding='latin-1',
                all_varchar=true,
                ignore_errors=true
            );
        """)
        total_cnaes = con.execute("SELECT COUNT(*) FROM cnaes").fetchone()[0]
        print(f"   ✅ {total_cnaes:,} CNAEs carregados")
    else:
        print("   ⚠️  Arquivo Cnaes não encontrado — gráficos usarão código numérico")
        con.execute("DROP TABLE IF EXISTS cnaes;")
        con.execute("CREATE TABLE cnaes (codigo VARCHAR, descricao VARCHAR);")

    # ── ETAPA 3: Normaliza o CNPJ do fornecedor ───────────────────────────
    # Só considera PJ com CNPJ de exatamente 14 dígitos
    # MEI é sempre Pessoa Jurídica — CPFs e registros inválidos são ignorados
    print("⏳ Normalizando CNPJs dos fornecedores...")
    con.execute("ALTER TABLE pncp_contratos_raw ADD COLUMN IF NOT EXISTS fornecedor_cnpj VARCHAR;")
    con.execute("""
        UPDATE pncp_contratos_raw
        SET fornecedor_cnpj =
            CASE
                WHEN upper(tipoPessoa) = 'PJ'
                AND length(regexp_replace(COALESCE(niFornecedor,''), '[^0-9]', '', 'g')) = 14
                THEN regexp_replace(COALESCE(niFornecedor,''), '[^0-9]', '', 'g')
                ELSE NULL
            END;
    """)

    # ── ETAPA 4: Filtra apenas esfera Federal ─────────────────────────────
    # esferaId: F=Federal, E=Estadual, M=Municipal, D=Distrital
    print("⏳ Filtrando contratos federais...")
    con.execute("DROP TABLE IF EXISTS pncp_contratos_federal_6m;")
    con.execute("""
        CREATE TABLE pncp_contratos_federal_6m AS
        SELECT *
        FROM pncp_contratos_raw
        WHERE orgaoEntidade.esferaId = 'F';
    """)
    cnt_fed = con.execute("SELECT COUNT(*) FROM pncp_contratos_federal_6m").fetchone()[0]
    print(f"   ✅ {cnt_fed:,} contratos federais")

    # ── ETAPA 5: Cruza com a tabela mei_ativo ─────────────────────────────
    # Só entram contratos cujo CNPJ do fornecedor existe na base de MEI ativo
    print("⏳ Cruzando com base de MEI ativo...")
    con.execute("DROP TABLE IF EXISTS pncp_mei_federal_6m;")
    con.execute("""
        CREATE TABLE pncp_mei_federal_6m AS
        SELECT
            p.*,
            m.RAZAO_SOCIAL   AS mei_razao_social,
            m.UF             AS mei_uf,
            m.MUNICIPIO      AS mei_municipio,
            m.CNAE_PRINCIPAL AS mei_cnae,
            -- Já traz a descrição do CNAE para evitar JOIN repetido nos KPIs
            COALESCE(c.descricao, m.CNAE_PRINCIPAL) AS mei_cnae_descricao
        FROM pncp_contratos_federal_6m p
        JOIN mei_ativo m
          ON p.fornecedor_cnpj = m.CNPJ
        LEFT JOIN cnaes c
          ON m.CNAE_PRINCIPAL = c.codigo
        WHERE p.fornecedor_cnpj IS NOT NULL;
    """)
    cnt_mei = con.execute("SELECT COUNT(*) FROM pncp_mei_federal_6m").fetchone()[0]
    print(f"   ✅ {cnt_mei:,} contratos firmados com MEI")

    # Índices para acelerar as consultas dos KPIs
    con.execute("CREATE INDEX IF NOT EXISTS idx_raw_cnpj     ON pncp_contratos_raw(fornecedor_cnpj);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_fed_cnpj     ON pncp_contratos_federal_6m(fornecedor_cnpj);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_mei_fed_cnpj ON pncp_mei_federal_6m(fornecedor_cnpj);")

    # ── ETAPA 6: Geração dos KPIs ─────────────────────────────────────────
    print("\n⏳ Gerando KPIs...")

    # KPI 1 — Participação geral (% de contratos e % de valor)
    # Responde: "Qual a fatia do MEI nas compras federais?"
    con.execute("DROP TABLE IF EXISTS kpi_mei_participacao_federal_6m;")
    con.execute("""
        CREATE TABLE kpi_mei_participacao_federal_6m AS
        WITH base AS (
            SELECT
                COUNT(*)                       AS contratos_total,
                SUM(COALESCE(valorGlobal, 0))  AS valor_total
            FROM pncp_contratos_federal_6m
        ),
        mei AS (
            SELECT
                COUNT(*)                       AS contratos_mei,
                SUM(COALESCE(valorGlobal, 0))  AS valor_mei
            FROM pncp_mei_federal_6m
        )
        SELECT
            mei.contratos_mei,
            base.contratos_total,
            CASE WHEN base.contratos_total = 0 THEN 0
                 ELSE (mei.contratos_mei::DOUBLE / base.contratos_total)
            END AS share_contratos,
            mei.valor_mei,
            base.valor_total,
            CASE WHEN base.valor_total = 0 THEN 0
                 ELSE (mei.valor_mei::DOUBLE / base.valor_total)
            END AS share_valor
        FROM base, mei;
    """)

    # KPI 2 — Top UF dos MEIs vendedores
    # Responde: "Quais estados têm mais MEIs contratados pelo governo federal?"
    con.execute("DROP TABLE IF EXISTS kpi_mei_top_uf_federal_6m;")
    con.execute("""
        CREATE TABLE kpi_mei_top_uf_federal_6m AS
        SELECT
            mei_uf          AS uf,
            COUNT(*)        AS qtd_contratos,
            SUM(COALESCE(valorGlobal, 0)) AS valor_total
        FROM pncp_mei_federal_6m
        GROUP BY 1
        ORDER BY valor_total DESC;
    """)

    # KPI 3 — Top CNAE dos MEIs com descrição
    # Responde: "Quais atividades econômicas (concorrentes) mais vendem para o governo?"
    con.execute("DROP TABLE IF EXISTS kpi_mei_top_cnae_federal_6m;")
    con.execute("""
        CREATE TABLE kpi_mei_top_cnae_federal_6m AS
        SELECT
            mei_cnae            AS cnae_codigo,
            mei_cnae_descricao  AS cnae_descricao,
            COUNT(*)            AS qtd_contratos,
            SUM(COALESCE(valorGlobal, 0)) AS valor_total
        FROM pncp_mei_federal_6m
        GROUP BY 1, 2
        ORDER BY valor_total DESC
        LIMIT 50;
    """)

    # KPI 4 — Top órgãos que mais compram de MEI
    # Responde: "Quem são os maiores compradores federais de MEI?"
    con.execute("DROP TABLE IF EXISTS kpi_mei_top_orgaos_federal_6m;")
    con.execute("""
        CREATE TABLE kpi_mei_top_orgaos_federal_6m AS
        SELECT
            orgaoEntidade.cnpj        AS orgao_cnpj,
            orgaoEntidade.razaoSocial AS orgao_razao,
            COUNT(*)                  AS qtd_contratos,
            SUM(COALESCE(valorGlobal, 0)) AS valor_total
        FROM pncp_mei_federal_6m
        GROUP BY 1, 2
        ORDER BY valor_total DESC
        LIMIT 50;
    """)

    # KPI 5 — Série temporal diária
    # Responde: "Como evoluiu a participação do MEI ao longo dos 6 meses?"
    con.execute("DROP TABLE IF EXISTS kpi_mei_serie_diaria_federal_6m;")
    con.execute("""
        CREATE TABLE kpi_mei_serie_diaria_federal_6m AS
        SELECT
            CAST(substr(CAST(dataPublicacaoPncp AS VARCHAR), 1, 10) AS DATE) AS dia,
            COUNT(*)        AS qtd_contratos,
            SUM(COALESCE(valorGlobal, 0)) AS valor_total
        FROM pncp_mei_federal_6m
        GROUP BY 1
        ORDER BY 1;
    """)

    # ── Resumo final ───────────────────────────────────────────────────────
    print("\n" + "="*50)
    print("📊 RESUMO DO CRUZAMENTO")
    print("="*50)
    print(f"  Contratos raw (total):      {cnt_raw:>10,}")
    print(f"  Contratos federais:         {cnt_fed:>10,}")
    print(f"  Contratos com MEI:          {cnt_mei:>10,}")

    kpi = con.execute("SELECT * FROM kpi_mei_participacao_federal_6m").fetchdf()
    share_q   = kpi['share_contratos'].iloc[0] * 100
    share_v   = kpi['share_valor'].iloc[0] * 100
    valor_mei = kpi['valor_mei'].iloc[0] / 1_000_000

    print(f"\n  Participação MEI (qtd):     {share_q:.2f}%")
    print(f"  Participação MEI (valor):   {share_v:.2f}%")
    print(f"  Valor total MEI:            R$ {valor_mei:.1f} milhões")
    print("="*50)

    con.close()
    print("\n✅ KPIs gerados! Próximo passo: python analysis/07_plot_kpis.py")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        raise