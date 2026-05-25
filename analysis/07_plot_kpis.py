# analysis/07_plot_kpis.py
# Etapa 7 — Gera gráficos PNG e relatório HTML a partir dos KPIs do DuckDB
#
# Pré-requisito: rodar os scripts 01 a 06 antes
#
# Saídas:
#   out_charts/*.png                  → gráficos individuais
#   dashboard/relatorio_mei_pncp.html → relatório completo

from pathlib import Path
from datetime import date
import duckdb
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# ── Caminhos ───────────────────────────────────────────────────────────────
DB_PATH   = Path("db/cnpj.duckdb")
OUT_DIR   = Path("out_charts")
HTML_PATH = Path("dashboard/relatorio_mei_pncp.html")

# ── Estilo visual ──────────────────────────────────────────────────────────
COR_PRINCIPAL = "#1a6eb5"   # azul governo
COR_DESTAQUE  = "#e8a020"   # laranja destaque
COR_FUNDO     = "#f7f9fc"
FONTE_TITULO  = 14
FONTE_EIXO    = 11

plt.rcParams.update({
    "figure.facecolor": COR_FUNDO,
    "axes.facecolor":   COR_FUNDO,
    "axes.spines.top":  False,
    "axes.spines.right":False,
    "font.family":      "DejaVu Sans",
})

# ── Formatadores ───────────────────────────────────────────────────────────
def fmt_pct(x: float) -> str:
    x = float(x or 0)
    pct = x * 100
    if pct < 0.01:
        return f"{pct:.4f}%"
    if pct < 0.1:
        return f"{pct:.3f}%"
    return f"{pct:.2f}%"

def fmt_brl(x: float) -> str:
    x = float(x or 0)
    if x >= 1e9:
        return f"R$ {x/1e9:.2f} bi"
    if x >= 1e6:
        return f"R$ {x/1e6:.2f} mi"
    if x >= 1e3:
        return f"R$ {x/1e3:.1f} mil"
    return f"R$ {x:.2f}"

def grafico_vazio(caminho: Path, mensagem: str) -> Path:
    """Gera um gráfico placeholder quando não há dados."""
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.text(0.5, 0.5, mensagem,
            ha="center", va="center", fontsize=13,
            color="#888", transform=ax.transAxes)
    ax.axis("off")
    plt.savefig(caminho, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"   ⚠️  {caminho} (sem dados)")
    return caminho

# ── Gráfico 1: Participação geral (pizza dupla) ────────────────────────────
def grafico_participacao(k: dict):
    # Garante que os valores nunca são NaN
    share_contratos = float(k.get("share_contratos") or 0)
    share_valor     = float(k.get("share_valor") or 0)
    contratos_total = int(k.get("contratos_total") or 0)
    contratos_mei   = int(k.get("contratos_mei") or 0)
    valor_total     = float(k.get("valor_total") or 0)
    valor_mei       = float(k.get("valor_mei") or 0)

    caminho = OUT_DIR / "01_participacao_mei.png"

    # Se não há dados, gera gráfico placeholder
    if share_contratos == 0 and share_valor == 0:
        return grafico_vazio(caminho, "Nenhum contrato MEI encontrado no período")

    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    fig.suptitle("Participação do MEI nas Compras Federais — últimos 6 meses",
                 fontsize=FONTE_TITULO + 1, fontweight="bold", y=1.02)

    for ax, share, total_lbl, mei_lbl, titulo in [
        (axes[0], share_contratos,
         f"{contratos_total:,} contratos",
         f"{contratos_mei:,} com MEI",
         "Por Quantidade de Contratos"),
        (axes[1], share_valor,
         fmt_brl(valor_total),
         fmt_brl(valor_mei),
         "Por Valor Financeiro"),
    ]:
        # Garante que a fatia nunca é exatamente 0 ou 1 (quebraria o pie)
        share = max(0.0001, min(0.9999, share))
        valores = [share, 1 - share]
        cores   = [COR_DESTAQUE, COR_PRINCIPAL]
        labels  = [f"MEI\n{fmt_pct(share)}", "Outros"]
        wedges, texts = ax.pie(
            valores, labels=labels, colors=cores,
            startangle=90, wedgeprops={"edgecolor": "white", "linewidth": 2}
        )
        texts[0].set_fontsize(12)
        texts[0].set_fontweight("bold")
        ax.set_title(titulo, fontsize=FONTE_TITULO, pad=12)
        ax.annotate(f"Total: {total_lbl}\nMEI: {mei_lbl}",
                    xy=(0, -1.35), ha="center", fontsize=9, color="#444")

    plt.tight_layout()
    plt.savefig(caminho, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"   ✅ {caminho}")
    return caminho

# ── Gráfico 2: Top 10 UF ──────────────────────────────────────────────────
def grafico_top_uf(df: pd.DataFrame):
    caminho = OUT_DIR / "02_top_uf.png"

    if df.empty:
        return grafico_vazio(caminho, "Sem dados de UF disponíveis")

    df = df.head(10).sort_values("valor_total")
    fig, ax = plt.subplots(figsize=(10, 6))

    bars = ax.barh(df["uf"], df["valor_total"] / 1e6,
                   color=COR_PRINCIPAL, edgecolor="white")

    for bar, val in zip(bars, df["valor_total"]):
        ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height() / 2,
                fmt_brl(val), va="center", fontsize=9, color="#333")

    ax.set_title("Top 10 Estados com MEIs Contratados pelo Governo Federal",
                 fontsize=FONTE_TITULO, fontweight="bold")
    ax.set_xlabel("Valor Total Contratado (em milhões de R$)", fontsize=FONTE_EIXO)
    ax.set_ylabel("Estado (UF)", fontsize=FONTE_EIXO)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"R$ {x:.0f}mi"))
    plt.tight_layout()

    plt.savefig(caminho, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"   ✅ {caminho}")
    return caminho

# ── Gráfico 3: Série temporal diária ──────────────────────────────────────
def grafico_serie_diaria(df: pd.DataFrame):
    caminho = OUT_DIR / "03_serie_diaria.png"

    if df.empty:
        return grafico_vazio(caminho, "Sem dados de série temporal disponíveis")

    fig, ax = plt.subplots(figsize=(12, 5))

    ax.fill_between(df["dia"], df["valor_total"] / 1e6,
                    alpha=0.3, color=COR_PRINCIPAL)
    ax.plot(df["dia"], df["valor_total"] / 1e6,
            color=COR_PRINCIPAL, linewidth=1.5)

    ax.set_title("Evolução Diária dos Contratos MEI no Governo Federal",
                 fontsize=FONTE_TITULO, fontweight="bold")
    ax.set_xlabel("Data de Publicação", fontsize=FONTE_EIXO)
    ax.set_ylabel("Valor Total (em milhões de R$)", fontsize=FONTE_EIXO)
    plt.xticks(rotation=45, ha="right", fontsize=9)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"R$ {x:.0f}mi"))
    plt.tight_layout()

    plt.savefig(caminho, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"   ✅ {caminho}")
    return caminho

# ── Gráfico 4: Top 15 CNAE com descrição ──────────────────────────────────
def grafico_top_cnae(df: pd.DataFrame):
    caminho = OUT_DIR / "04_top_cnae.png"

    if df.empty:
        return grafico_vazio(caminho, "Sem dados de CNAE disponíveis")

    df = df.head(15).copy()

    # Usa a descrição se disponível, senão usa o código
    df["label"] = df.apply(
        lambda r: (
            str(r["cnae_descricao"])[:50]
            if pd.notna(r.get("cnae_descricao")) and str(r.get("cnae_descricao")).strip()
            else str(r["cnae_codigo"])
        ),
        axis=1
    )

    df = df.sort_values("valor_total")
    fig, ax = plt.subplots(figsize=(13, 8))

    bars = ax.barh(df["label"], df["valor_total"] / 1e6,
                   color=COR_PRINCIPAL, edgecolor="white")

    for bar, val in zip(bars, df["valor_total"]):
        ax.text(bar.get_width() + 0.05, bar.get_y() + bar.get_height() / 2,
                fmt_brl(val), va="center", fontsize=8, color="#333")

    ax.set_title("Top 15 Atividades Econômicas (CNAE) dos MEIs Contratados",
                 fontsize=FONTE_TITULO, fontweight="bold")
    ax.set_xlabel("Valor Total Contratado (em milhões de R$)", fontsize=FONTE_EIXO)
    ax.set_ylabel("Atividade Econômica", fontsize=FONTE_EIXO)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"R$ {x:.0f}mi"))
    plt.tight_layout()

    plt.savefig(caminho, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"   ✅ {caminho}")
    return caminho

# ── Gráfico 5: Top 15 Órgãos compradores ─────────────────────────────────
def grafico_top_orgaos(df: pd.DataFrame):
    caminho = OUT_DIR / "05_top_orgaos.png"

    if df.empty:
        return grafico_vazio(caminho, "Sem dados de órgãos disponíveis")

    df = df.head(15).copy()
    df["orgao_razao"] = df["orgao_razao"].astype(str).str.strip().str[:60]
    df = df.sort_values("valor_total")

    fig, ax = plt.subplots(figsize=(13, 8))

    bars = ax.barh(df["orgao_razao"], df["valor_total"] / 1e6,
                   color=COR_DESTAQUE, edgecolor="white")

    for bar, val in zip(bars, df["valor_total"]):
        ax.text(bar.get_width() + 0.05, bar.get_y() + bar.get_height() / 2,
                fmt_brl(val), va="center", fontsize=8, color="#333")

    ax.set_title("Top 15 Órgãos Federais que Mais Compraram de MEIs",
                 fontsize=FONTE_TITULO, fontweight="bold")
    ax.set_xlabel("Valor Total Pago a MEIs (em milhões de R$)", fontsize=FONTE_EIXO)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"R$ {x:.0f}mi"))
    plt.tight_layout()

    plt.savefig(caminho, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"   ✅ {caminho}")
    return caminho

# ── Relatório HTML ─────────────────────────────────────────────────────────
def gerar_html(k: dict, caminhos: list):
    hoje = date.today().strftime("%d/%m/%Y")

    # Garante valores seguros para o HTML
    share_contratos = float(k.get("share_contratos") or 0)
    share_valor     = float(k.get("share_valor") or 0)
    contratos_mei   = int(k.get("contratos_mei") or 0)
    contratos_total = int(k.get("contratos_total") or 0)
    valor_mei       = float(k.get("valor_mei") or 0)
    valor_total     = float(k.get("valor_total") or 0)

    imgs_html = ""
    titulos = [
        ("Participação Geral do MEI",     "Como o MEI se posiciona no total de compras federais."),
        ("Distribuição por Estado (UF)",  "Quais estados concentram mais MEIs contratados."),
        ("Evolução Temporal Diária",      "Como os contratos com MEI evoluíram ao longo do período."),
        ("Perfil Econômico — Top CNAE",   "Quais atividades econômicas (seus concorrentes diretos) mais vendem."),
        ("Principais Órgãos Compradores", "Quem são os maiores compradores federais de MEIs."),
    ]
    for caminho, (titulo, descricao) in zip(caminhos, titulos):
        nome_img = Path(caminho).name
        imgs_html += f"""
        <section>
            <h2>{titulo}</h2>
            <p>{descricao}</p>
            <img src="../out_charts/{nome_img}" alt="{titulo}"/>
        </section>"""

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Panorama MEI — Compras Federais</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f0f4f8; color: #222; }}
    header {{
      background: #1a6eb5; color: white;
      padding: 32px 40px; text-align: center;
    }}
    header h1 {{ font-size: 26px; margin-bottom: 8px; }}
    header p  {{ font-size: 14px; opacity: 0.85; }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px; padding: 32px 40px 0;
    }}
    .card {{
      background: white; border-radius: 12px;
      padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);
      border-left: 5px solid #1a6eb5;
    }}
    .card .label {{ font-size: 12px; color: #666; margin-bottom: 6px; }}
    .card .valor {{ font-size: 28px; font-weight: 700; color: #1a6eb5; }}
    .card .sub   {{ font-size: 11px; color: #888; margin-top: 4px; }}
    main {{ padding: 32px 40px; }}
    section {{
      background: white; border-radius: 12px;
      padding: 24px; margin-bottom: 24px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }}
    section h2 {{ font-size: 16px; color: #1a6eb5; margin-bottom: 6px; }}
    section p  {{ font-size: 13px; color: #555; margin-bottom: 14px; }}
    section img {{ width: 100%; border-radius: 8px; border: 1px solid #e0e7ef; }}
    footer {{
      text-align: center; padding: 20px;
      font-size: 11px; color: #999;
    }}
  </style>
</head>
<body>

<header>
  <h1>📊 Panorama do MEI nas Compras Públicas Federais</h1>
  <p>Análise dos últimos 6 meses · Gerado em {hoje} · Fontes: PNCP + Receita Federal</p>
</header>

<div class="cards">
  <div class="card">
    <div class="label">Participação por Quantidade</div>
    <div class="valor">{fmt_pct(share_contratos)}</div>
    <div class="sub">{contratos_mei:,} de {contratos_total:,} contratos</div>
  </div>
  <div class="card">
    <div class="label">Participação por Valor</div>
    <div class="valor">{fmt_pct(share_valor)}</div>
    <div class="sub">{fmt_brl(valor_mei)} de {fmt_brl(valor_total)}</div>
  </div>
  <div class="card">
    <div class="label">Total Pago a MEIs</div>
    <div class="valor">{fmt_brl(valor_mei)}</div>
    <div class="sub">últimos 6 meses · esfera federal</div>
  </div>
  <div class="card">
    <div class="label">Contratos com MEI</div>
    <div class="valor">{contratos_mei:,}</div>
    <div class="sub">contratos federais publicados no PNCP</div>
  </div>
</div>

<main>
{imgs_html}
</main>

<footer>
  Fonte: PNCP (Portal Nacional de Contratações Públicas) · Receita Federal (Simples Nacional/MEI) ·
  Projeto de Extensão MEMP — {hoje}
</footer>

</body>
</html>"""

    HTML_PATH.parent.mkdir(parents=True, exist_ok=True)
    HTML_PATH.write_text(html, encoding="utf-8")
    print(f"\n   ✅ Relatório HTML: {HTML_PATH}")

# ── Main ───────────────────────────────────────────────────────────────────
def main():
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"❌ Banco não encontrado: {DB_PATH}\n"
            f"   Execute primeiro os scripts 01 a 06."
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(DB_PATH))
    print("📊 Carregando KPIs do DuckDB...")

    kpi      = con.execute("SELECT * FROM kpi_mei_participacao_federal_6m").fetchdf()
    df_uf    = con.execute("SELECT * FROM kpi_mei_top_uf_federal_6m").fetchdf()
    df_serie = con.execute("SELECT * FROM kpi_mei_serie_diaria_federal_6m").fetchdf()
    df_cnae  = con.execute("SELECT * FROM kpi_mei_top_cnae_federal_6m").fetchdf()
    df_org   = con.execute("SELECT * FROM kpi_mei_top_orgaos_federal_6m").fetchdf()
    con.close()

    if kpi.empty:
        raise RuntimeError("❌ KPIs vazios. Rode primeiro: python pipeline/06_pncp_join_mei.py")

    k = kpi.iloc[0].to_dict()

    # Mostra resumo no terminal antes de gerar os gráficos
    print(f"\n   Contratos total:    {int(k.get('contratos_total') or 0):,}")
    print(f"   Contratos MEI:      {int(k.get('contratos_mei') or 0):,}")
    print(f"   Share quantidade:   {fmt_pct(k.get('share_contratos') or 0)}")
    print(f"   Share valor:        {fmt_pct(k.get('share_valor') or 0)}")

    print("\n🎨 Gerando gráficos...")
    caminhos = [
        grafico_participacao(k),
        grafico_top_uf(df_uf),
        grafico_serie_diaria(df_serie),
        grafico_top_cnae(df_cnae),
        grafico_top_orgaos(df_org),
    ]

    print("\n📄 Gerando relatório HTML...")
    gerar_html(k, caminhos)

    print("\n" + "="*50)
    print("🏁 Tudo gerado com sucesso!")
    print(f"   Gráficos:  {OUT_DIR}/")
    print(f"   Relatório: {HTML_PATH}")
    print("="*50)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        raise