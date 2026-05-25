# 📊 Projeto MEMP — MEI nas Compras Públicas

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![DuckDB](https://img.shields.io/badge/DuckDB-latest-yellow.svg)](https://duckdb.org/)
[![Fonte: PNCP](https://img.shields.io/badge/Fonte-PNCP-green.svg)](https://pncp.gov.br)
[![Fonte: RFB](https://img.shields.io/badge/Fonte-Receita%20Federal-green.svg)](https://dadosabertos.rfb.gov.br/CNPJ/)
[![Licença: MIT](https://img.shields.io/badge/Licença-MIT-lightgrey.svg)](LICENSE)

> Análise quantitativa da participação de **Microempreendedores Individuais (MEI)**
> nas contratações públicas brasileiras, com atualização mensal automatizada.

---

## 🎯 Objetivos do Projeto

Este projeto responde a quatro perguntas estratégicas:

| Pergunta | KPI Gerado |
|---|---|
| Qual a fatia de dinheiro que o governo destina aos MEIs? | % por quantidade e valor de contratos |
| Onde estão os MEIs no Brasil? | Distribuição geográfica por UF |
| Quem são os concorrentes diretos? | Top CNAEs mais contratados |
| Quanto fatura um concorrente? | Valor por contrato por CNPJ |

---

## 🗂️ Fontes de Dados

### Receita Federal — Cadastro CNPJ (dados abertos)
**URL:** https://dados-abertos-rf-cnpj.casadosdados.com.br/arquivos

Arquivos utilizados:
- `Empresas*.zip` → razão social
- `Estabelecimentos*.zip` → UF, município, situação cadastral, CNAE
- `Simples.zip` → flag de opção pelo MEI (`opcaoMEI = 'S'`)

> ⚠️ Arquivos sem cabeçalho, encoding `latin-1`, dezenas de milhões de linhas.

### PNCP — Portal Nacional de Contratações Públicas
**API:** https://pncp.gov.br/api/consulta/swagger-ui/index.html

Endpoint utilizado:
```
GET /v1/contratos
```

Campos-chave: `dataPublicacaoPncp`, `niFornecedor`, `tipoPessoa`, `valorGlobal`, `orgaoEntidade`

---

## 🧱 Stack Tecnológica

| Tecnologia | Papel |
|---|---|
| **Python 3.10+** | Linguagem principal do pipeline |
| **DuckDB** | Banco analítico local — suporta dezenas de milhões de linhas sem servidor |
| **Pandas** | Manipulação de DataFrames para os KPIs |
| **Requests** | Coleta paginada da API REST do PNCP |
| **Matplotlib / Seaborn** | Geração dos gráficos PNG |
| **Schedule** | Agendamento da atualização mensal automática |

---

## 📁 Estrutura do Projeto

```
projeto_memp/
│
├── data/                               # Dados brutos (ignorados pelo git)
│   ├── rf_cnpj_csv/                    # CSVs da Receita Federal (~15-20 GB)
│   └── pncp_contratos_6m.jsonl         # Contratos baixados da API PNCP
│
├── db/                                 # Banco DuckDB (ignorado pelo git)
│   └── cnpj.duckdb
│
├── pipeline/                           # Scripts de ingestão e processamento
│   ├── 00_download_rfb.py              # Download automático dos arquivos da RFB
│   ├── 01_import_empresas.py           # Importa empresas para o DuckDB
│   ├── 02_import_estabelecimentos.py   # Importa estabelecimentos (UF, CNAE)
│   ├── 03_import_simples.py            # Importa Simples Nacional / MEI
│   ├── 04_create_mei_ativo.py          # Cruza as 3 tabelas → mei_ativo
│   ├── 05_pncp_coleta_contratos.py     # Coleta contratos federais via API
│   └── 06_pncp_join_mei.py             # Cruza contratos com MEI → KPIs
│
├── analysis/
│   └── 07_plot_kpis.py                 # Gera gráficos PNG + relatório HTML
│
├── dashboard/
│   └── relatorio_mei_pncp.html         # Relatório final interativo
│
├── scheduler/
│   └── atualizar_mensal.py             # Automação mensal do pipeline completo
│
├── out_charts/                         # Gráficos gerados (PNG)
│   ├── 01_participacao_mei.png
│   ├── 02_top_uf.png
│   ├── 03_serie_diaria.png
│   ├── 04_top_cnae.png
│   └── 05_top_orgaos.png
│
├── logs/                               # Logs das execuções mensais
│
├── .gitignore
├── requirements.txt
└── README.md
```

---

## 🧠 Arquitetura do Pipeline

```
┌─────────────────────────────────────────────────────────┐
│                   FONTES DE DADOS                        │
│                                                          │
│  Receita Federal (RFB)          PNCP (API REST)          │
│  dadosabertos.rfb.gov.br        pncp.gov.br              │
│  Empresas / Estabelecimentos    GET /v1/contratos        │
│  Simples Nacional               últimos 6 meses          │
└───────────────┬─────────────────────────┬────────────────┘
                │                         │
                ▼                         ▼
┌──────────────────────────┐   ┌──────────────────────────┐
│  00_download_rfb.py      │   │  05_pncp_coleta_         │
│  Download automático     │   │  contratos.py            │
│  + descompactação        │   │  Paginação + retry       │
└──────────────┬───────────┘   └──────────────┬───────────┘
               │                              │
               ▼                              ▼
┌──────────────────────────┐   ┌──────────────────────────┐
│  01_import_empresas.py   │   │                          │
│  02_import_estabele...   │   │  pncp_contratos_6m.jsonl │
│  03_import_simples.py    │   │  (salvamento incremental)│
│                          │   │                          │
│  Tabelas no DuckDB:      │   └──────────────┬───────────┘
│  • empresas              │                  │
│  • estabelecimentos      │                  │
│  • simples               │                  │
└──────────────┬───────────┘                  │
               │                              │
               ▼                              │
┌──────────────────────────┐                  │
│  04_create_mei_ativo.py  │                  │
│                          │                  │
│  mei_ativo =             │                  │
│    empresas              │                  │
│    ⨝ estabelecimentos    │                  │
│    ⨝ simples             │                  │
│    onde opcaoMEI = 'S'   │                  │
│    e situação = ativa    │                  │
└──────────────┬───────────┘                  │
               │                              │
               └──────────────┬───────────────┘
                              │
                              ▼
               ┌──────────────────────────────┐
               │  06_pncp_join_mei.py          │
               │                              │
               │  contratos PNCP              │
               │  ⨝ mei_ativo (pelo CNPJ)     │
               │                              │
               │  KPIs gerados:               │
               │  • participação geral        │
               │  • top UF                    │
               │  • top CNAE                  │
               │  • top órgãos                │
               │  • série temporal diária     │
               └──────────────┬───────────────┘
                              │
                              ▼
               ┌──────────────────────────────┐
               │  07_plot_kpis.py             │
               │                              │
               │  → Gráficos PNG              │
               │  → Relatório HTML            │
               └──────────────────────────────┘
```

---

## ⚙️ Como Instalar e Rodar

### Pré-requisitos
- Python 3.10+
- ~25 GB de espaço em disco livre
- Conexão com a internet

### 1. Clone o repositório
```bash
git clone https://github.com/GustavoWPJC/DashBoard-MEI.git
cd DashBoard-MEI
```

### 2. Crie o ambiente virtual e instale as dependências
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Execute o pipeline completo
```bash
# Etapa 0 — Baixa e descompacta os dados da Receita Federal (~5GB, pode demorar horas)
python pipeline/00_download_rfb.py

# Etapas 1-4 — Ingestão e construção da base de MEI ativo
python pipeline/01_import_empresas.py
python pipeline/02_import_estabelecimentos.py
python pipeline/03_import_simples.py
python pipeline/04_create_mei_ativo.py

# Etapa 5 — Coleta contratos do PNCP via API
python pipeline/05_pncp_coleta_contratos.py

# Etapa 6 — Cruza os dados e gera os KPIs
python pipeline/06_pncp_join_mei.py

# Etapa 7 — Gera gráficos e relatório HTML
python analysis/07_plot_kpis.py
```

### 4. Veja o resultado
Abra o relatório no navegador:
```bash
xdg-open dashboard/relatorio_mei_pncp.html
```

---

## 🔄 Atualização Mensal Automática

### Opção 1 — Rodar manualmente
```bash
python scheduler/atualizar_mensal.py --agora
```

### Opção 2 — Agendador interno (roda todo dia 1º às 06:00)
```bash
python scheduler/atualizar_mensal.py
```

### Opção 3 — Cron do Linux (recomendado para produção)
```bash
crontab -e
# Adicione a linha abaixo:
0 6 1 * * /caminho/projeto/venv/bin/python /caminho/projeto/scheduler/atualizar_mensal.py --agora
```

Cada execução gera um log em `logs/atualizacao_AAAAMM.log`.

---

## 📈 KPIs Gerados

| KPI | Tabela DuckDB | Gráfico |
|---|---|---|
| Participação por quantidade e valor | `kpi_mei_participacao_federal_6m` | `01_participacao_mei.png` |
| Top estados com mais MEIs contratados | `kpi_mei_top_uf_federal_6m` | `02_top_uf.png` |
| Evolução diária dos contratos | `kpi_mei_serie_diaria_federal_6m` | `03_serie_diaria.png` |
| Top atividades econômicas (CNAE) | `kpi_mei_top_cnae_federal_6m` | `04_top_cnae.png` |
| Top órgãos compradores | `kpi_mei_top_orgaos_federal_6m` | `05_top_orgaos.png` |

---

## ⚠️ Limitações Conhecidas

- Contratos com fornecedor PF não entram (MEI é sempre PJ)
- Contratos sem CNPJ válido de 14 dígitos são descartados
- Compras de valor muito baixo podem não passar pelo PNCP
- Qualidade dos dados depende do preenchimento correto pelos órgãos públicos
- A janela de análise é de 6 meses (configurável no script 05)

---

## 📦 Dependências

```
duckdb
pandas
requests
matplotlib
seaborn
plotly
schedule
```

Instale tudo com:
```bash
pip install -r requirements.txt
```

---

## 👥 Autores
Kaielly, Gustavo, Vinicius e Kauã.
Projeto de Extensão — **MEMP**
Desenvolvido com base nos dados abertos da Receita Federal e do PNCP.

---

## 📄 Licença

MIT License — veja o arquivo [LICENSE](LICENSE) para detalhes.