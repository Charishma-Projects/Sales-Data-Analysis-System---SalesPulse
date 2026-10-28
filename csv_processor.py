"""
csv_processor.py - CSV Ingestion, Validation, Cleaning, and Duplicate Management Engine
Implements strict column schema validation, malformed row reporting,
automated data cleaning (dates, numbers, strings, computed revenues),
generation of downloadable cleaned CSV files, and documented duplicate handling policies ('skip', 'replace', 'abort').
"""

import io
import os
import csv
import re
import secrets
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
from database import DatabaseManager

REQUIRED_COLUMNS = ["sale_date", "quantity", "unit_price", "region"]
OPTIONAL_COLUMNS = ["sale_id", "product_id", "product_name", "category", "total_revenue"]
ALL_STANDARD_COLUMNS = ["sale_id", "product_id", "product_name", "category", "sale_date", "quantity", "unit_price", "region", "total_revenue"]

# Mapping common alternative header names across various ERP and retail systems
COLUMN_ALIASES = {
    "sale_id": ["sales_id", "salesid", "saleid", "order_id", "orderid", "transaction_id", "trans_id", "id", "sale_number", "invoice_no", "invoice_id", "receipt_id"],
    "product_id": ["productid", "item_id", "itemid", "sku", "prod_id", "item_code", "product_code"],
    "product_name": ["productname", "item_name", "product_title", "title", "name", "product", "description"],
    "category": ["product_category", "dept", "department", "cat", "genre", "category_name"],
    "sale_date": ["saledate", "date", "order_date", "transaction_date", "timestamp", "invoice_date", "trans_date"],
    "quantity": ["qty", "units", "quantity_sold", "units_sold", "count", "num_units"],
    "unit_price": ["unitprice", "price", "rate", "cost_per_unit", "item_price", "cost", "unit_cost"],
    "region": ["sales_region", "area", "zone", "territory", "location", "country", "city", "state"],
    "total_revenue": ["revenue", "total_amount", "amount", "total", "sales_amount", "total_sales"]
}

UPLOADS_DIR = os.getenv("UPLOADS_DIR", os.path.join(os.path.dirname(__file__), "uploads"))


def normalize_headers(headers: List[str]) -> Tuple[Dict[str, str], List[str]]:
    """
    Normalizes input CSV header names to standard entity fields using aliases.
    Returns: (mapping of normalized_name -> original_header, list of missing required fields)
    """
    cleaned_headers = {h.strip().lower().replace(" ", "_"): h for h in headers if h}
    resolved_mapping = {}

    for standard_col in REQUIRED_COLUMNS + OPTIONAL_COLUMNS:
        # Exact match
        if standard_col in cleaned_headers:
            resolved_mapping[standard_col] = cleaned_headers[standard_col]
            continue
        # Alias match
        aliases = COLUMN_ALIASES.get(standard_col, [])
        for alias in aliases:
            if alias in cleaned_headers:
                resolved_mapping[standard_col] = cleaned_headers[alias]
                break

    # Validate required columns
    missing_required = []

    # Product identifier check: must have either product_id or product_name
    if "product_id" not in resolved_mapping and "product_name" not in resolved_mapping:
        missing_required.append("product_name (or product_id)")

    for col in REQUIRED_COLUMNS:
        if col not in resolved_mapping:
            missing_required.append(col)

    return resolved_mapping, missing_required


def parse_flexible_date(date_str: Any) -> Optional[str]:
    """Parses various date formats and converts to ISO standard YYYY-MM-DD."""
    if not date_str:
        return None
    val = str(date_str).strip()
    if not val:
        return None
    # Strip ISO timestamp time component if present
    if "T" in val:
        val = val.split("T")[0]
    elif " " in val and (val.count("-") == 2 or val.count("/") == 2):
        parts = val.split(" ")
        if len(parts) >= 2 and ":" in parts[1]:
            val = parts[0]

    formats = [
        "%Y-%m-%d", "%Y/%m/%d",
        "%d-%m-%Y", "%d/%m/%Y",
        "%m-%d-%Y", "%m/%d/%Y",
        "%Y-%m-%d %H:%M:%S",
        "%d-%b-%Y", "%d %b %Y", "%B %d, %Y",
        "%d %B %Y", "%b %d, %Y",
        "%m/%d/%y", "%d/%m/%y"
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(val, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def generate_cleaned_csv(valid_rows: List[Dict[str, Any]]) -> str:
    """Generates pristine, normalized CSV string containing only cleaned and valid records."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=ALL_STANDARD_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in valid_rows:
        writer.writerow({
            "sale_id": str(row.get("sale_id", "")).strip(),
            "product_id": str(row.get("product_id", "")).strip(),
            "product_name": str(row.get("product_name", "")).strip(),
            "category": str(row.get("category", "")).strip(),
            "sale_date": str(row.get("sale_date", "")).strip(),
            "quantity": int(row.get("quantity", 0)),
            "unit_price": f"{float(row.get('unit_price', 0.0)):.2f}",
            "region": str(row.get("region", "")).strip(),
            "total_revenue": f"{float(row.get('total_revenue', 0.0)):.2f}"
        })
    return output.getvalue()


def generate_malformed_csv(malformed_rows: List[Dict[str, Any]]) -> str:
    """Generates diagnostic CSV report of malformed and rejected rows with error reasons."""
    output = io.StringIO()
    fieldnames = ["row_number", "sale_id", "product_id", "product_name", "category", "sale_date", "quantity", "unit_price", "region", "validation_errors"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for item in malformed_rows:
        data = item.get("data", {})
        writer.writerow({
            "row_number": item.get("row_number", ""),
            "sale_id": data.get("sale_id", ""),
            "product_id": data.get("product_id", ""),
            "product_name": data.get("product_name", ""),
            "category": data.get("category", ""),
            "sale_date": data.get("sale_date", ""),
            "quantity": data.get("quantity", ""),
            "unit_price": data.get("unit_price", ""),
            "region": data.get("region", ""),
            "validation_errors": " | ".join(item.get("errors", []))
        })
    return output.getvalue()


def save_batch_files(
    batch_id: str,
    cleaned_csv_content: str,
    malformed_csv_content: Optional[str] = None
) -> Tuple[str, Optional[str]]:
    """Saves cleaned and malformed files into uploads directory for persistent download."""
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    
    cleaned_filename = f"cleaned_{batch_id}.csv"
    cleaned_path = os.path.join(UPLOADS_DIR, cleaned_filename)
    with open(cleaned_path, "w", encoding="utf-8") as f:
        f.write(cleaned_csv_content)
        
    latest_path = os.path.join(UPLOADS_DIR, "cleaned_latest.csv")
    with open(latest_path, "w", encoding="utf-8") as f:
        f.write(cleaned_csv_content)

    malformed_path = None
    if malformed_csv_content:
        malformed_filename = f"malformed_{batch_id}.csv"
        malformed_path = os.path.join(UPLOADS_DIR, malformed_filename)
        with open(malformed_path, "w", encoding="utf-8") as f:
            f.write(malformed_csv_content)

    return cleaned_path, malformed_path


class CSVProcessor:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def clean_dataset(
        self,
        file_content: str,
        duplicate_policy: str = "skip",
        original_filename: str = "sales_upload.csv"
    ) -> Dict[str, Any]:
        """
        Parses, validates, and cleans external sales CSV data.
        Performs:
          1. Header normalization and alias resolution.
          2. Row sanitation (dates to ISO YYYY-MM-DD, numbers to valid int/float, trimmed text).
          3. Total revenue calculation (quantity * unit_price).
          4. Malformed row isolation and reporting.
          5. Duplicate handling according to policy ('skip', 'replace', 'abort').
          6. Generates and stores cleaned CSV and malformed diagnostics files.
        """
        if duplicate_policy not in ("skip", "replace", "abort"):
            duplicate_policy = "skip"

        clean_basename = os.path.splitext(os.path.basename(original_filename))[0] if original_filename else "sales_data"
        batch_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + secrets.token_hex(4)

        f = io.StringIO(file_content.strip())
        reader = csv.reader(f)
        
        try:
            raw_headers = next(reader)
        except StopIteration:
            return {
                "success": False,
                "batch_id": batch_id,
                "error": "The uploaded CSV file is completely empty.",
                "total_rows": 0,
                "valid_rows_count": 0,
                "malformed_rows_count": 0,
                "malformed_rows": [],
                "duplicates_count": 0,
                "cleaned_download_url": None,
                "cleaned_csv_content": ""
            }

        # 1. Column Header Validation
        resolved_mapping, missing_required = normalize_headers(raw_headers)
        if missing_required:
            return {
                "success": False,
                "batch_id": batch_id,
                "error": f"Header validation failed! Missing required columns: {', '.join(missing_required)}.",
                "required_columns": REQUIRED_COLUMNS,
                "detected_headers": raw_headers,
                "total_rows": 0,
                "valid_rows_count": 0,
                "malformed_rows_count": 0,
                "malformed_rows": [],
                "cleaned_download_url": None,
                "cleaned_csv_content": ""
            }

        # Map standard column name to column index in reader row
        col_index_map = {}
        header_to_idx = {h.strip(): idx for idx, h in enumerate(raw_headers)}
        for std_col, orig_header in resolved_mapping.items():
            col_index_map[std_col] = header_to_idx[orig_header.strip()]

        total_rows = 0
        valid_rows_to_insert = []
        malformed_rows = []
        seen_sale_ids_in_batch = {}

        # 2. Row-by-Row Schema and Constraint Validation
        for line_num, row in enumerate(reader, start=2):
            if not row or all(c.strip() == "" for c in row):
                continue  # skip completely blank lines

            total_rows += 1
            row_errors = []

            # Helper to extract value safely
            def get_val(std_key, default=""):
                if std_key in col_index_map and col_index_map[std_key] < len(row):
                    return row[col_index_map[std_key]].strip()
                return default

            sale_id = get_val("sale_id")
            # sale_id is optional: auto-generate unique identifier if omitted or blank
            if not sale_id:
                sale_id = f"SALE-{secrets.token_hex(4).upper()}"

            raw_product_id = get_val("product_id")
            raw_product_name = get_val("product_name")

            if "product_id" in col_index_map and not raw_product_id:
                # product_id column was present in CSV header, but left empty on this row
                row_errors.append("Missing required field 'product_id'.")
                product_id = ""
                product_name = raw_product_name or "Unknown Product"
            elif raw_product_id:
                product_id = raw_product_id
                product_name = raw_product_name or f"Product {product_id}"
            elif raw_product_name:
                # product_id column was not in CSV; derive clean product_id from product_name
                product_name = raw_product_name
                clean_slug = re.sub(r"[^A-Za-z0-9]", "", product_name).upper()[:12]
                product_id = f"P-{clean_slug}" if clean_slug else f"P-{secrets.token_hex(3).upper()}"
            else:
                row_errors.append("Missing product information (both 'product_id' and 'product_name' are empty).")
                product_id = ""
                product_name = "Unknown Product"

            category = get_val("category", "General") or "General"
            raw_date = get_val("sale_date")
            raw_qty = get_val("quantity")
            raw_price = get_val("unit_price")
            region = get_val("region")

            row_dict = {
                "sale_id": sale_id,
                "product_id": product_id,
                "product_name": product_name,
                "category": category,
                "sale_date": raw_date,
                "quantity": raw_qty,
                "unit_price": raw_price,
                "region": region
            }

            # Validation checks
            if not region:
                row_errors.append("Missing required field 'region'.")

            # Date check
            parsed_date = parse_flexible_date(raw_date)
            if not parsed_date:
                row_errors.append(f"Invalid date format '{raw_date}'. Expected YYYY-MM-DD or DD/MM/YYYY.")

            # Quantity check
            quantity_int = 0
            try:
                q_float = float(raw_qty)
                if not q_float.is_integer() or q_float <= 0:
                    row_errors.append(f"Quantity must be a positive integer > 0, got '{raw_qty}'.")
                else:
                    quantity_int = int(q_float)
            except (ValueError, TypeError):
                row_errors.append(f"Invalid quantity value '{raw_qty}'. Must be a positive integer.")

            # Unit Price check
            unit_price_float = 0.0
            try:
                cleaned_price = re.sub(r"[^\d.]", "", str(raw_price))
                unit_price_float = float(cleaned_price)
                if unit_price_float <= 0:
                    row_errors.append(f"Unit price must be greater than 0, got '{raw_price}'.")
                else:
                    unit_price_float = round(unit_price_float, 2)
            except (ValueError, TypeError):
                row_errors.append(f"Invalid unit price value '{raw_price}'. Must be a valid positive number.")

            # Batch internal duplicate check
            if sale_id and not row_errors:
                if sale_id in seen_sale_ids_in_batch:
                    if duplicate_policy == "abort":
                        row_errors.append(f"Duplicate sale_id '{sale_id}' found in batch (Row {line_num} duplicates Row {seen_sale_ids_in_batch[sale_id]}). Policy is 'abort'.")
                    elif duplicate_policy == "skip":
                        row_errors.append(f"Duplicate sale_id '{sale_id}' in batch skipped (first seen on row {seen_sale_ids_in_batch[sale_id]}).")
                else:
                    seen_sale_ids_in_batch[sale_id] = line_num

            # Malformed or Valid
            if row_errors:
                malformed_rows.append({
                    "row_number": line_num,
                    "errors": row_errors,
                    "data": row_dict
                })
            else:
                total_revenue = round(quantity_int * unit_price_float, 2)
                valid_rows_to_insert.append({
                    "sale_id": sale_id,
                    "product_id": product_id,
                    "product_name": product_name or f"Product {product_id}",
                    "category": category or "General",
                    "sale_date": parsed_date,
                    "quantity": quantity_int,
                    "unit_price": unit_price_float,
                    "region": region,
                    "total_revenue": total_revenue
                })

        # Generate cleaned CSV text
        cleaned_csv_content = generate_cleaned_csv(valid_rows_to_insert) if valid_rows_to_insert else ""
        malformed_csv_content = generate_malformed_csv(malformed_rows) if malformed_rows else None

        # Save files to uploads directory
        save_batch_files(batch_id, cleaned_csv_content, malformed_csv_content)

        batch_total_revenue = round(sum(item["total_revenue"] for item in valid_rows_to_insert), 2)

        return {
            "success": True,
            "batch_id": batch_id,
            "original_filename": original_filename,
            "cleaned_download_url": f"/api/download-cleaned/{batch_id}?filename=cleaned_{clean_basename}.csv",
            "cleaned_filename": f"cleaned_{clean_basename}.csv",
            "cleaned_rows_count": len(valid_rows_to_insert),
            "cleaned_csv_content": cleaned_csv_content,
            "malformed_download_url": f"/api/download-malformed/{batch_id}?filename=malformed_{clean_basename}.csv" if malformed_rows else None,
            "malformed_filename": f"malformed_{clean_basename}.csv" if malformed_rows else None,
            "total_rows": total_rows,
            "valid_rows_count": len(valid_rows_to_insert),
            "malformed_rows_count": len(malformed_rows),
            "malformed_rows": malformed_rows,
            "valid_rows_to_insert": valid_rows_to_insert,
            "batch_total_revenue": batch_total_revenue,
            "duplicate_policy": duplicate_policy
        }

    def validate_and_import(
        self,
        file_content: str,
        duplicate_policy: str = "skip",
        original_filename: str = "sales_upload.csv"
    ) -> Dict[str, Any]:
        """
        Parses CSV string content, executes column validation, per-row validation,
        generates cleaned downloadable dataset, applies duplicate policy ('skip', 'replace', 'abort'),
        and records transactions in the database.
        
        Returns comprehensive execution report dictionary.
        """
        clean_res = self.clean_dataset(file_content, duplicate_policy=duplicate_policy, original_filename=original_filename)
        if not clean_res.get("success"):
            return clean_res

        total_rows = clean_res["total_rows"]
        malformed_rows = clean_res["malformed_rows"]
        valid_rows = clean_res["valid_rows_to_insert"]
        batch_id = clean_res["batch_id"]

        # Check if policy is abort and we found duplicates or malformed rows
        if duplicate_policy == "abort" and malformed_rows:
            return {
                "success": False,
                "batch_id": batch_id,
                "error": f"Import aborted! Found {len(malformed_rows)} invalid or duplicate rows under strict 'abort' policy.",
                "total_rows": total_rows,
                "valid_rows_count": 0,
                "malformed_rows_count": len(malformed_rows),
                "malformed_rows": malformed_rows,
                "cleaned_download_url": clean_res["cleaned_download_url"],
                "cleaned_filename": clean_res["cleaned_filename"],
                "malformed_download_url": clean_res["malformed_download_url"],
                "malformed_filename": clean_res["malformed_filename"],
                "duplicate_policy": duplicate_policy
            }

        # 3. Database Insertion & Upsert
        inserted_count = 0
        skipped_count = 0
        replaced_count = 0
        batch_total_revenue = 0.0

        for item in valid_rows:
            # Check duplicate against DB before inserting if abort policy
            if duplicate_policy == "abort" and self.db.check_sale_exists(item["sale_id"]):
                return {
                    "success": False,
                    "batch_id": batch_id,
                    "error": f"Import aborted! Duplicate sale_id '{item['sale_id']}' already exists in database under 'abort' policy.",
                    "total_rows": total_rows,
                    "valid_rows_count": inserted_count,
                    "inserted_count": inserted_count,
                    "replaced_count": replaced_count,
                    "skipped_count": skipped_count,
                    "malformed_rows_count": len(malformed_rows),
                    "malformed_rows": malformed_rows,
                    "cleaned_download_url": clean_res["cleaned_download_url"],
                    "cleaned_filename": clean_res["cleaned_filename"],
                    "malformed_download_url": clean_res["malformed_download_url"],
                    "malformed_filename": clean_res["malformed_filename"],
                    "duplicate_policy": duplicate_policy
                }

            # Upsert product first to maintain relational integrity
            self.db.upsert_product(
                product_id=item["product_id"],
                product_name=item["product_name"],
                category=item["category"]
            )

            try:
                status = self.db.insert_sale_record(
                    sale_id=item["sale_id"],
                    product_id=item["product_id"],
                    sale_date=item["sale_date"],
                    quantity=item["quantity"],
                    unit_price=item["unit_price"],
                    region=item["region"],
                    total_revenue=item["total_revenue"],
                    duplicate_policy=duplicate_policy
                )
            except ValueError as ve:
                return {
                    "success": False,
                    "batch_id": batch_id,
                    "error": f"Import aborted! {ve}",
                    "total_rows": total_rows,
                    "valid_rows_count": inserted_count,
                    "malformed_rows_count": len(malformed_rows),
                    "malformed_rows": malformed_rows,
                    "cleaned_download_url": clean_res["cleaned_download_url"],
                    "cleaned_filename": clean_res["cleaned_filename"],
                    "malformed_download_url": clean_res["malformed_download_url"],
                    "malformed_filename": clean_res["malformed_filename"],
                    "duplicate_policy": duplicate_policy
                }

            if status == "inserted":
                inserted_count += 1
                batch_total_revenue += item["total_revenue"]
            elif status == "replaced":
                replaced_count += 1
                batch_total_revenue += item["total_revenue"]
            elif status == "skipped":
                skipped_count += 1

        return {
            "success": True,
            "message": f"Successfully processed {total_rows} rows. Inserted: {inserted_count}, Replaced: {replaced_count}, Skipped Duplicates: {skipped_count}, Malformed: {len(malformed_rows)}.",
            "batch_id": batch_id,
            "cleaned_download_url": clean_res["cleaned_download_url"],
            "cleaned_filename": clean_res["cleaned_filename"],
            "cleaned_rows_count": len(valid_rows),
            "malformed_download_url": clean_res["malformed_download_url"],
            "malformed_filename": clean_res["malformed_filename"],
            "total_rows": total_rows,
            "valid_rows_count": inserted_count + replaced_count,
            "inserted_count": inserted_count,
            "replaced_count": replaced_count,
            "skipped_count": skipped_count,
            "malformed_rows_count": len(malformed_rows),
            "malformed_rows": malformed_rows,
            "batch_total_revenue": round(batch_total_revenue, 2),
            "duplicate_policy": duplicate_policy
        }

    def clean_only(
        self,
        file_content: str,
        duplicate_policy: str = "skip",
        original_filename: str = "sales_upload.csv"
    ) -> Dict[str, Any]:
        """Cleans external CSV data and prepares downloadable files without touching database."""
        res = self.clean_dataset(file_content, duplicate_policy=duplicate_policy, original_filename=original_filename)
        if res.get("success"):
            res["message"] = f"Successfully cleaned {res['total_rows']} rows ({res['cleaned_rows_count']} valid, {res['malformed_rows_count']} malformed)."
        return res
