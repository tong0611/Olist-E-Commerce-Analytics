# Tableau Public build guide

Three dashboards built from the CSVs in `exports/` (produced by `make export`).

| Dashboard | Data sources |
|---|---|
| 1. Revenue Overview | `mart_revenue_monthly`, `fct_orders` + `dim_customers` |
| 2. Customers & Retention | `dim_customers`, `mart_customer_cohorts` |
| 3. Product Performance | `mart_product_performance` |

> **Rule of thumb:** the marts are pre-aggregated. Never `AVG()` a ratio column such as `avg_order_value`;
> rebuild ratios from their parts (`SUM(revenue) / SUM(orders)`), so they stay correct under any filter.

---

## 0. Setup (10 min)

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
| **MoM Growth** | Columns: `MONTH(month)`. Rows: `AVG(revenue_mom_growth)` (one row per month, so AVG = the value). Bars, color by sign: `[revenue_mom_growth] > 0`. Format as %. |
| **Revenue by State** | Source *Orders*: `state` (from dim_customers) → geographic role **State/Province**. Map → Edit Locations → Country **Brazil**. Color `SUM(revenue)`. If a state doesn't place, use a symbol map on `AVG(latitude)` / `AVG(longitude)` instead. |
| **Payment Mix** | Source *Orders*: Rows `primary_payment_type`, Columns `SUM(revenue)`, sorted descending, filter `is_revenue_order = true`. |

### Dashboard
**Dashboard → New Dashboard**, Size **Fixed 1200 × 900**. KPI row on top, Revenue Trend full width,
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
5. Copy the public URL into the project README (Phase 8 section) and take a screenshot of each dashboard for `docs/img/`.

## Refreshing after the pipeline runs
`make export` overwrites the CSVs in place. In Tableau: **Data → (source) → Refresh**, then re-save to Tableau Public.
