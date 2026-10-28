# 📊 Sales Data Analysis System (SalesPulse)

An enterprise-ready **Sales Data Analysis System** built with **Python**, **Pandas**, **NumPy**, **Matplotlib**, and **Flask**. The system provides comprehensive sales analytics, automated CSV schema validation with malformed row diagnostics, documented duplicate resolution policies, interactive web dashboards, and public exposure via **Public API Keys** and **Global HTTPS Tunnels**.

---

## 🎯 Objectives & Scope

- **Ingest & Validate Sales Records**: Securely upload and validate structured CSV files or manage sales records manually.
- **Data Integrity & Diagnostics**: Strict column schema verification, per-row constraint validation, and malformed row reporting.
- **Duplicate Policy Engine**: Documented handling of duplicate transaction identifiers (`skip`, `replace`, or `abort`).
- **Data Aggregations**:
  - **Pandas**: Automated data cleaning, multi-level aggregations, and date grouping.
  - **NumPy**: Vectorized revenue computations, summary statistics, and Month-over-Month (MoM) growth calculations.
- **Visualization**:
  - **Matplotlib**: Server-rendered, publication-quality Base64 charts (dual-axis trends, horizontal product rankings, category donut, and regional bars).
  - **Chart.js**: Real-time interactive charts with dynamic tooltips.
- **Public Key & Global Exposure**: Expose the server publicly via Localtunnel with Public API Key authentication.

---

## 🏗️ Architecture & Entities

### Relational Schema

```sql
-- Products Entity
CREATE TABLE products (
    product_id VARCHAR(64) PRIMARY KEY,
    product_name VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sales Entity
CREATE TABLE sales (
    sale_id VARCHAR(64) PRIMARY KEY,
    product_id VARCHAR(64) NOT NULL,
    sale_date DATE NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(10, 2) NOT NULL,
    region VARCHAR(100) NOT NULL,
    total_revenue DECIMAL(12, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE
);
```

> **Dual Database Engine**: The system runs automatically out-of-the-box using local SQLite (`sales_system.db`), and supports seamless switching to MySQL through the UI or environment variables.

---

## 🚀 Acceptance Criteria & Features

| Acceptance Criteria | Implementation Details |
| :--- | :--- |
| **Malformed Rows Reported** | Every uploaded row is strictly validated against date formats, positive integer quantities, and valid decimal prices. Invalid rows are isolated with line numbers, raw values, and detailed reasons. |
| **External Files Cleaned & Downloadable** | External CSV uploads are sanitized automatically: column aliases mapped, dates converted to ISO (`YYYY-MM-DD`), prices/quantities stripped of symbols, and revenues calculated. A pristine **Cleaned CSV file is immediately downloadable** by the user, alongside a malformed diagnostic report. |
| **Revenue Calculations Tested** | Verified using automated unit tests comparing `quantity * unit_price`, vectorized NumPy arrays, and Pandas group aggregations. |
| **Duplicate Policy Documented** | User-selectable policy: <br>• `skip`: Retains original record, skips duplicate in batch.<br>• `replace`: Updates existing transaction with incoming values.<br>• `abort`: Fails the entire batch if any duplicate transaction ID is detected. |
| **Public Execution & Public Key** | Generates a persistent Public Key (`pk_live_sales_...`) for external API authentication, and provisions a live HTTPS Public URL via Localtunnel. |

---

## 📦 Installation & Quick Start

### 1. Requirements

Make sure Python 3.10+ is installed. Dependencies are listed in `requirements.txt`:
```bash
pip install -r requirements.txt
```

### 2. Start the Server

Run the Flask application:
```bash
python app.py
```

Console output will display:
```
=======================================================
📊 Sales Data Analysis System is RUNNING
📍 Local Web UI:    http://127.0.0.1:5000
🔑 Public API Key:  pk_live_sales_78f19...
🌐 Public Tunnel:   https://funny-otter-42.loca.lt
=======================================================
```

---

## 🔑 Public Key & Remote API Usage

You can query the analytics engine or upload records remotely using your **Public API Key**:

### Header Authentication
Pass the key in the `X-API-Key` HTTP header:
```bash
curl -X GET "http://127.0.0.1:5000/api/analytics" \
  -H "X-API-Key: YOUR_PUBLIC_KEY"
```bash
# Clean external CSV and download the cleaned version directly:
curl -X POST "http://127.0.0.1:5000/api/clean-csv?format=file" \
  -H "X-API-Key: YOUR_PUBLIC_KEY" \
  -F "file=@dirty_sales.csv" \
  -o "cleaned_sales.csv"
```

### Python Integration Example
```python
import requests

PUBLIC_URL = "http://127.0.0.1:5000"  # or your https://*.loca.lt URL
PUBLIC_KEY = "YOUR_PUBLIC_KEY"

headers = {"X-API-Key": PUBLIC_KEY}

# Fetch summary KPIs & rankings
response = requests.get(f"{PUBLIC_URL}/api/analytics", headers=headers)
data = response.json()
print("Total Revenue:", data["analytics"]["summary_kpis"]["total_revenue"])
print("Top Product:", data["analytics"]["summary_kpis"]["best_product"])

# Clean an external file and get downloadable cleaned URL
with open("dirty_sales.csv", "rb") as f:
    upload_res = requests.post(f"{PUBLIC_URL}/api/upload-csv", files={"file": f}, headers=headers).json()
print("Cleaned Rows:", upload_res["cleaned_rows_count"])
print("Cleaned Download URL:", upload_res["cleaned_download_url"])
```

---

## 🧪 Automated Test Suite

Run the acceptance tests anytime:
```bash
python -m unittest tests/test_sales_system.py
```

Verified tests (9 test cases):
- `test_missing_column_headers`: Verifies column schema detection and failure reporting.
- `test_malformed_rows_reporting`: Verifies malformed rows with negative quantities, invalid dates, and text prices.
- `test_revenue_calculations`: Tests mathematical calculations of revenue and AOV.
- `test_duplicate_handling_policies`: Validates `skip`, `replace`, and `abort` policies.
- `test_product_ranking_and_mom_growth`: Tests NumPy Month-over-Month growth and ranking formulas.
- `test_chart_generation`: Tests Matplotlib Base64 rendering.
- `test_public_key_authentication`: Tests key generation, validation, and regeneration.
- `test_cleaned_file_generation_and_download`: Tests external file cleaning, sanitization, revenue computation, and file download.
- `test_clean_only_mode_without_db_modification`: Tests file cleaning and downloadable output without modifying the live database.
