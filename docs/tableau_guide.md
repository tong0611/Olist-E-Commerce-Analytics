# Tableau build guide

Three dashboards in `tableau/olist_dashboards.twb`. Two ways to feed them:

- **Tableau Desktop → Snowflake (used for this project).** Connect live to `OLIST.MARTS`, build,
  then switch each data source to **Extract** before publishing. See *0a* below.
- **Tableau Public app → CSVs** in `exports/` (produced by `make export`). See *0b* below.

## 0a. Tableau Desktop + Snowflake

1. Install the Snowflake ODBC driver (Tableau prompts for it; driver name `SnowflakeDSIIDriver`).
2. **Connect → Snowflake**: server `<account>.snowflakecomputing.com`, role `OLIST_REPORTER`,
   warehouse `OLIST_BI_WH`, authentication **Sign in using OAuth**. This needs the
   `TABLEAU_DESKTOP_OAUTH` security integration (section 8 of `snowflake/01_account_setup.sql`)
   and `GRANT ROLE OLIST_REPORTER TO USER <you>`. Admin roles are blocked for OAuth.
3. Database `OLIST`, schema `MARTS`. Create two data sources (**Data → New Data Source** each time;
   don't add tables to an existing one):

| Data source | Tables |
|---|---|
| Revenue Monthly | `MART_REVENUE_MONTHLY` |
| Orders | `FCT_ORDERS` related to `DIM_CUSTOMERS` on `Customer Unique Id`. Performance options: Many-to-One, *All records match* |

4. **Session expiry:** Snowflake caps Tableau Desktop's OAuth refresh token at 10 hours, and idle
   sessions also expire ("OAuth refresh token is expired" / "Master token can never be renewed").
   Fix: save, **File → Close**, reopen the workbook and sign in again. To avoid it entirely, switch
   each data source to **Extract** (Data Source tab, top right); `.hyper` files are gitignored.
   Tableau Public needs extracts anyway.

Field names show title-cased in Tableau (`revenue` → **Revenue**, `is_partial_month` → **Is Partial Month**).

## 0b. Tableau Public + CSVs

| Dashboard | Data sources |
|---|---|
| 1. Revenue Overview | `mart_revenue_monthly`, `fct_orders` + `dim_customers` |
| 2. Customers & Retention | `dim_customers`, `mart_customer_cohorts` |
| 3. Product Performance | `mart_product_performance` |

> **Rule of thumb:** the marts are pre-aggregated. Never `AVG()` a ratio column such as `avg_order_value`;
> rebuild ratios from their parts (`SUM(revenue) / SUM(orders)`), so they stay correct under any filter.

---

1. Create a free account at **public.tableau.com**, then **Create → Download the App** (Tableau Public for Mac).
2. Open Tableau Public. Under **Connect → To a File → Text file**, open `exports/mart_revenue_monthly.csv`.
3. On the **Data Source** tab, check each field's type icon and fix any that are wrong:
   - `month`, `purchase_date`, `purchase_month`, `cohort_month`, `*_date` → **Date**
   - `*_at` → **Date & Time**
   - `zip_code_prefix` → **String** (otherwise leading zeros are lost)
   - `latitude` / `longitude` → **Number (decimal)**, Geographic Role **Latitude / Longitude**
4. Rename the data source (top-left) to something readable, e.g. **Revenue Monthly**.
5. Add the other sources with **Data → New Data Source → Text file**:

| Data source name | File(s) | How |
|---|---|---|
| Revenue Monthly | `mart_revenue_monthly.csv` | single table |
| Orders | `fct_orders.csv` **+** `dim_customers.csv` | drag `dim_customers` onto the canvas next to `fct_orders` → relationship on `customer_unique_id = customer_unique_id` |
| Customers | `dim_customers.csv` | single table |
| Cohorts | `mart_customer_cohorts.csv` | single table |
| Products | `mart_product_performance.csv` | single table |

Save early: **File → Save to Tableau Public As…** (Tableau Public saves to the web only).

### Formatting: Brazilian Real
Right-click any money measure → **Default Properties → Number Format → Currency (Custom)**:
prefix `R$`, 0 decimals for totals (2 for AOV/CLV), display units Thousands (K) or Millions (M) where useful.

---

## 1. Revenue Overview

### Calculated fields (data source *Revenue Monthly*)
```
AOV                 = SUM([revenue]) / SUM([orders])
Repeat Share        = SUM([returning_customers]) / SUM([active_customers])
Complete Month      = NOT [is_partial_month]
```

### Sheets
| Sheet | Build |
|---|---|
| **KPI – Revenue** | Text mark: `SUM(revenue)`. Title "Total Revenue". Repeat for **Orders** (`SUM(orders)`) and **AOV** (`AOV`). |
| **KPI – Customers** | Source *Orders*: `COUNTD(customer_unique_id)` with filter `is_revenue_order = true`. (Don't sum `active_customers` across months: it double-counts people.) |
| **Revenue Trend** | Columns: `MONTH(month)` (green/continuous). Rows: `SUM(revenue)`. Line + area. Filter `Complete Month = True`. Add a trend line (Analytics pane). |
| **New vs Returning** | Columns: `MONTH(month)`. Rows: Measure Values = `SUM(new_customers)`, `SUM(returning_customers)`. Stacked bars, color by Measure Names. |
| **MoM Growth** | Columns: `MONTH(month)`. Rows: `AVG(revenue_mom_growth)` (one row per month, so AVG = the value). Bars, color by sign: `AVG([revenue_mom_growth]) > 0` (green/red). Format as %. **Filter `month` to Feb 2017 – Aug 2018**: the months after near-empty ones show absurd growth (Oct 2016 +18,261%, Jan 2017 +697,879%) and flatten every other bar. |
| **Revenue by State** | Source *Orders*: `state` (from dim_customers) → geographic role **State/Province**. Map → Edit Locations → Country **Brazil**. Color `SUM(revenue)`. If a state doesn't place, use a symbol map on `AVG(latitude)` / `AVG(longitude)` instead. |
| **Payment Mix** | Source *Orders*: Rows `primary_payment_type`, Columns `SUM(revenue)`, sorted descending, filter `is_revenue_order = true`. |

### Expected values (check against these)
| Measure | Value | Note |
|---|---|---|
| Total Revenue | R$15,736K | ties to the source DB to the cent |
| Orders | 98,207 | `mart_revenue_monthly` counts **revenue orders only**; 99,441 includes 1,234 canceled/unavailable |
| AOV | R$160.23 | `SUM(revenue) / SUM(orders)` |
| Customers | 94,990 | distinct buyers with ≥ 1 revenue order (96,096 includes cancel-only customers) |
| Peak month | Nov 2017, R$1.17M | Black Friday; MoM +53%, then Dec −27% |
| Top state | SP, R$5.9M (~37%) | then RJ R$2.1M, MG R$1.8M |
| Payment mix | credit card 78%, boleto 18%, voucher 2%, debit 1% | exclude the one Null (R$143) |

Map tip: Tableau recognises the two-letter state codes once `state` has the State/Province role.
If the dashboard tile shows the whole world, use the map toolbar's reset (home) button.

### Dashboard
**Dashboard → New Dashboard**, Size **Fixed 1200 × 900**. KPI row on top (set each KPI tile to **Fit → Entire View** to avoid scrollbars), Revenue Trend full width,
then New vs Returning, MoM Growth, and Map + Payment Mix. Use a **Year** filter (from `month`) applied to all
sheets using that source (filter menu → Apply to Worksheets → All Using This Data Source).

Title with the insight, not the chart type, e.g.
*"Monthly revenue grew ~8x from Jan 2017 to 2018; ~98% of each month's buyers are new customers"*.

---

## 2. Customers & Retention

### Parameter (makes churn interactive)
**Create Parameter** `Churn Window (days)`: Integer, current value 180, range 30–365, step 30. Right-click → **Show Parameter**.

### Calculated fields (data source *Customers*)
```
Is Purchaser         = [revenue_orders] > 0
Churned (param)      = [Is Purchaser] AND [days_since_last_purchase] > [Churn Window (days)]
Churn Rate           = SUM(IIF([Churned (param)], 1, 0)) / SUM(IIF([Is Purchaser], 1, 0))
Repeat Rate          = SUM(IIF([customer_type] = "repeat", 1, 0)) / SUM(IIF([Is Purchaser], 1, 0))
Avg CLV              = SUM([customer_lifetime_value]) / SUM(IIF([Is Purchaser], 1, 0))
```

### Sheets
| Sheet | Build |
|---|---|
| **KPIs** | Text marks: `COUNTD(customer_unique_id)` (filter Is Purchaser), `Repeat Rate`, `Avg CLV`, `Churn Rate`. |
| **CLV by Type** | Rows `customer_type` (exclude `no_purchase`), Columns `AVG(customer_lifetime_value)`. Label bars. Shows repeat buyers are worth ~2x. |
| **Recency Histogram** | `days_since_last_purchase` → right-click → Create → Bins (size 30). Columns: the bin, Rows: `CNT(customer_unique_id)`. Color by `Churned (param)`. Add a **Reference Line** at the parameter value. |
| **Cohort Heatmap** | Source *Cohorts*. Rows: `MONTH(cohort_month)` (discrete, blue). Columns: `months_since_first_purchase` (discrete). Filter `months_since_first_purchase` 1–12 (month 0 is always 100%) **and `cohort_size` ≥ 100** (late-2016 cohorts have 1–2 customers and show fake 50–100% retention). Mark: Square, Color `AVG(retention_rate)` (sequential palette), Label as % with 2 decimals. |
| **Customers by State** | Symbol or filled map of `COUNTD(customer_unique_id)` by `state`. |

### Dashboard
Fixed 1200 × 900. KPIs on top, with the parameter control beside them. Cohort Heatmap is the hero chart.
Insight title, e.g. *"Only 3% of customers ever buy twice, and under 0.5% return the next month: retention is the growth lever"*.

> For a single "Month-1 retention" number, weight by cohort size: `SUM([active_customers]) / SUM([cohort_size])` filtered to month 1 → **0.45%**. A plain `AVG(retention_rate)` gives 5.2% because tiny cohorts dominate it.

---

## 3. Product Performance

### Calculated fields (data source *Products*)
```
Revenue per Unit     = SUM([revenue]) / SUM([units_sold])
Top 20 Product       = [revenue_rank] <= 20
```

### Sheets
| Sheet | Build |
|---|---|
| **Top Categories** | Rows `category_label`, Columns `SUM(revenue)`, sort descending, Filter → Top → By field: Top 10 by SUM(revenue). Color by `AVG(avg_review_score)` (diverging, center 4). |
| **Units vs Revenue** | Category-level scatter: Detail `category_label`, Columns `SUM(units_sold)`, Rows `SUM(revenue)`, Size `SUM(orders)`. Label the outliers. |
| **Review vs Price** | Columns `AVG(avg_price)`, Rows `AVG(avg_review_score)`, Detail `category_label`. Shows whether expensive categories review worse. |
| **Top Products** | Text table: `product_id` (or a shortened ID), `category_label`, `SUM(units_sold)`, `SUM(revenue)`, `AVG(avg_review_score)`. Filter `Top 20 Product = True`. |

### Dashboard
Add a **Category** filter applied to all Products sheets. Insight title, e.g.
*"Health & Beauty leads revenue; Bed/Bath/Table leads volume at lower prices"*.

---

## 4. Polish and publish

1. Create a **Story** (optional) or a landing dashboard with navigation buttons (Objects → Navigation) to the three dashboards.
2. Use one consistent palette and font. Hide sheet tabs that aren't dashboards (right-click → Hide).
3. Add a footer text object: *"Source: Olist (Kaggle) · Pipeline: Postgres → S3 → Snowflake → dbt → Tableau · github.com/<you>/…"*.
4. **File → Save to Tableau Public**. On the web page: Edit details → description and the GitHub link; toggle "Allow workbook download".
   - If **Server → Tableau Public** is greyed out, check **Help → Manage Product Keys**: *Tableau Desktop Free
     Edition* cannot publish to Tableau Public (only Public Edition can). Workaround used here: switch every data
     source to Extract, **File → Export Packaged Workbook** (`.twbx`, gitignored), open it in **Tableau Desktop
     Public Edition**, then **File → Save to Tableau Public As…**.
   - Only the tab that was active when saving is shown at first: turn on *Show Workbook Sheets as Tabs* (gear icon).
5. Copy the public URL into the project README (Phase 8 section) and take a screenshot of each dashboard for `docs/img/`.

## Refreshing after the pipeline runs
`make export` overwrites the CSVs in place. In Tableau: **Data → (source) → Refresh**, then re-save to Tableau Public.
