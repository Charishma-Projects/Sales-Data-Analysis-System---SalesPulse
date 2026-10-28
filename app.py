"""
app.py - Main Flask Application Server for Sales Data Analysis System
Provides:
  1. REST APIs for CSV ingestion, schema validation, analytics, and record maintenance.
  2. Integrated Matplotlib and interactive chart endpoints.
  3. Public Key authentication and live public tunnel management.
  4. Dual-mode database compatibility (SQLite & MySQL).
"""

import os
import sys
import io
import csv
import secrets
from flask import Flask, request, jsonify, render_template, send_from_directory, Response
from flask_cors import CORS

from database import DatabaseManager, db
from csv_processor import CSVProcessor
from analytics_engine import SalesAnalyticsEngine
from chart_generator import render_all_charts
from tunnel_manager import TunnelAndKeyManager

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app, resources={r"/*": {"origins": "*"}})

# Managers
processor = CSVProcessor(db)
tunnel_manager = TunnelAndKeyManager(db, port=5000)

# Pre-populate sample data if database is brand new
def auto_seed_sample_if_empty():
    try:
        df = db.get_all_sales_df()
        if df.empty:
            sample_path = os.path.join(os.path.dirname(__file__), "sample_data", "sales_sample_clean.csv")
            if os.path.exists(sample_path):
                with open(sample_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    processor.validate_and_import(content, duplicate_policy="skip")
                    print("[AutoSeed] Successfully initialized database with clean sample sales records.")
    except Exception as e:
        print(f"[AutoSeed] Warning: {e}")

auto_seed_sample_if_empty()


# Helper: API Key verification for remote API callers
def verify_api_key_if_provided():
    """Returns True if request has valid API key, or None if no key passed."""
    key = request.headers.get("X-API-Key") or request.args.get("api_key")
    if key:
        return tunnel_manager.validate_api_key(key)
    return None


# -------------------------------------------------------------
# Frontend Route
# -------------------------------------------------------------
@app.route("/")
def index():
    """Serves the main interactive Sales Data Analysis web dashboard."""
    return render_template("index.html")


# -------------------------------------------------------------
# Analytics & Reports APIs
# -------------------------------------------------------------
@app.route("/api/analytics", methods=["GET"])
def get_analytics():
    """Returns full analytics metrics: KPIs, rankings, trends, MoM growth."""
    # Optional API key check (returns 401 only if an invalid key was explicitly sent)
    key_valid = verify_api_key_if_provided()
    if key_valid is False:
        return jsonify({"success": False, "error": "Unauthorized: Invalid Public API Key provided."}), 401

    df = db.get_all_sales_df()
    engine = SalesAnalyticsEngine(df)
    report = engine.get_complete_analytics_report()
    
    return jsonify({
        "success": True,
        "database_type": db.db_type,
        "analytics": report
    })


@app.route("/api/charts", methods=["GET"])
def get_charts():
    """Generates and returns Matplotlib base64 charts."""
    df = db.get_all_sales_df()
    engine = SalesAnalyticsEngine(df)
    report = engine.get_complete_analytics_report()
    charts = render_all_charts(report)
    
    return jsonify({
        "success": True,
        "charts": charts
    })


# -------------------------------------------------------------
# CSV Ingestion, Validation & Cleaning APIs
# -------------------------------------------------------------
@app.route("/api/upload-csv", methods=["POST"])
def upload_csv():
    """
    Handles CSV file upload or raw text, validates headers and rows,
    cleans formats and calculates revenues, generates downloadable cleaned CSV,
    applies duplicate policy ('skip', 'replace', 'abort'),
    and returns detailed validation/error report.
    """
    key_valid = verify_api_key_if_provided()
    if key_valid is False:
        return jsonify({"success": False, "error": "Unauthorized: Invalid Public API Key."}), 401

    duplicate_policy = request.form.get("duplicate_policy", "skip").strip().lower()
    clean_only = request.form.get("clean_only", "false").strip().lower() in ("true", "1", "yes")
    filename = "sales_upload.csv"
    
    # 1. From uploaded file
    if "file" in request.files:
        file = request.files["file"]
        if file.filename == "":
            return jsonify({"success": False, "error": "No file selected for upload."}), 400
        filename = file.filename
        try:
            content = file.read().decode("utf-8-sig", errors="replace")
        except Exception as e:
            return jsonify({"success": False, "error": f"Failed to read file: {e}"}), 400

    # 2. From JSON body (raw csv string)
    elif request.is_json and "csv_data" in request.json:
        content = request.json["csv_data"]
        duplicate_policy = request.json.get("duplicate_policy", duplicate_policy).strip().lower()
        clean_only = str(request.json.get("clean_only", clean_only)).strip().lower() in ("true", "1", "yes")
        filename = request.json.get("filename", filename)

    # 3. From raw form-data body
    elif "csv_text" in request.form:
        content = request.form["csv_text"]

    else:
        return jsonify({"success": False, "error": "Please provide a CSV file or csv_data string."}), 400

    # Execute cleaning and import (or clean-only)
    if clean_only:
        report = processor.clean_only(content, duplicate_policy=duplicate_policy, original_filename=filename)
    else:
        report = processor.validate_and_import(content, duplicate_policy=duplicate_policy, original_filename=filename)
        
    return jsonify(report), 200 if report.get("success") else 422


@app.route("/api/clean-csv", methods=["POST"])
def clean_csv():
    """
    Dedicated CSV Data Cleaning Service.
    Accepts raw or messy external sales CSV, standardizes column headers,
    cleans values (dates to ISO YYYY-MM-DD, numerical values sanitized, computed revenues),
    isolates malformed records, and returns cleaned dataset.
    
    Can return JSON metadata + download URLs or direct CSV file attachment (via ?format=file).
    """
    key_valid = verify_api_key_if_provided()
    if key_valid is False:
        return jsonify({"success": False, "error": "Unauthorized: Invalid Public API Key."}), 401

    duplicate_policy = request.form.get("duplicate_policy", "skip").strip().lower()
    import_to_db = request.form.get("import_to_db", "false").strip().lower() in ("true", "1", "yes")
    filename = "sales_upload.csv"

    if "file" in request.files:
        file = request.files["file"]
        if file.filename == "":
            return jsonify({"success": False, "error": "No file selected."}), 400
        filename = file.filename
        content = file.read().decode("utf-8-sig", errors="replace")
    elif request.is_json and "csv_data" in request.json:
        content = request.json["csv_data"]
        duplicate_policy = request.json.get("duplicate_policy", duplicate_policy).strip().lower()
        import_to_db = str(request.json.get("import_to_db", import_to_db)).strip().lower() in ("true", "1", "yes")
        filename = request.json.get("filename", filename)
    elif "csv_text" in request.form:
        content = request.form["csv_text"]
    else:
        return jsonify({"success": False, "error": "Please provide a CSV file or csv_data string."}), 400

    if import_to_db:
        report = processor.validate_and_import(content, duplicate_policy=duplicate_policy, original_filename=filename)
    else:
        report = processor.clean_only(content, duplicate_policy=duplicate_policy, original_filename=filename)

    # If direct file download requested
    if request.args.get("format") == "file" or request.headers.get("Accept") == "text/csv":
        cleaned_csv = report.get("cleaned_csv_content", "")
        return Response(
            cleaned_csv,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment;filename=cleaned_{filename}"}
        )

    return jsonify(report), 200 if report.get("success") else 422


@app.route("/api/download-cleaned/<batch_id>", methods=["GET"])
def download_cleaned_file(batch_id):
    """
    Serves the cleaned and normalized CSV file for a given upload batch.
    Supports ?filename=custom_name.csv and batch_id='latest'.
    """
    uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
    if batch_id == "latest":
        target_file = "cleaned_latest.csv"
    else:
        target_file = f"cleaned_{batch_id}.csv"

    target_path = os.path.join(uploads_dir, target_file)
    if not os.path.exists(target_path):
        return jsonify({"success": False, "error": f"Cleaned file for batch '{batch_id}' was not found."}), 404

    download_name = request.args.get("filename", f"cleaned_{target_file}")
    if not download_name.endswith(".csv"):
        download_name += ".csv"

    return send_from_directory(
        uploads_dir,
        target_file,
        as_attachment=True,
        download_name=download_name
    )


@app.route("/api/download-malformed/<batch_id>", methods=["GET"])
def download_malformed_file(batch_id):
    """
    Serves the diagnostic CSV report of malformed/rejected rows for a given upload batch.
    """
    uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
    target_file = f"malformed_{batch_id}.csv"
    target_path = os.path.join(uploads_dir, target_file)

    if not os.path.exists(target_path):
        return jsonify({"success": False, "error": f"No malformed rows found for batch '{batch_id}'."}), 404

    download_name = request.args.get("filename", f"malformed_report_{batch_id}.csv")
    if not download_name.endswith(".csv"):
        download_name += ".csv"

    return send_from_directory(
        uploads_dir,
        target_file,
        as_attachment=True,
        download_name=download_name
    )


# -------------------------------------------------------------
# Sales Record CRUD & Maintenance APIs
# -------------------------------------------------------------
@app.route("/api/records", methods=["GET"])
def get_records():
    """Returns paginated sales records with optional region/category filtering."""
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))
    region = request.args.get("region")
    category = request.args.get("category")

    records, total_count = db.get_sales_records(limit=limit, offset=offset, region=region, category=category)
    return jsonify({
        "success": True,
        "total_records": total_count,
        "limit": limit,
        "offset": offset,
        "records": records
    })


@app.route("/api/records", methods=["POST"])
def add_record():
    """Manually add or update a sales record."""
    data = request.get_json(force=True, silent=True) or request.form.to_dict()
    required = ["product_id", "sale_date", "quantity", "unit_price", "region"]
    
    for req in required:
        if req not in data or str(data[req]).strip() == "":
            return jsonify({"success": False, "error": f"Missing required field: '{req}'."}), 400

    sale_id = str(data.get("sale_id", "") or data.get("sales_id", "")).strip()
    if not sale_id:
        sale_id = f"SALE-{secrets.token_hex(4).upper()}"

    product_id = str(data["product_id"]).strip()
    product_name = str(data.get("product_name", f"Product {product_id}")).strip()
    category = str(data.get("category", "General")).strip()
    sale_date = str(data["sale_date"]).strip()
    
    try:
        quantity = int(data["quantity"])
        if quantity <= 0:
            return jsonify({"success": False, "error": "Quantity must be greater than 0."}), 400
    except ValueError:
        return jsonify({"success": False, "error": "Quantity must be a valid integer."}), 400

    try:
        unit_price = round(float(data["unit_price"]), 2)
        if unit_price <= 0:
            return jsonify({"success": False, "error": "Unit price must be greater than 0."}), 400
    except ValueError:
        return jsonify({"success": False, "error": "Unit price must be a valid number."}), 400

    region = str(data["region"]).strip()
    total_revenue = round(quantity * unit_price, 2)
    duplicate_policy = str(data.get("duplicate_policy", "replace")).lower()

    # Save product
    db.upsert_product(product_id, product_name, category)
    
    # Save sale
    try:
        status = db.insert_sale_record(
            sale_id=sale_id,
            product_id=product_id,
            sale_date=sale_date,
            quantity=quantity,
            unit_price=unit_price,
            region=region,
            total_revenue=total_revenue,
            duplicate_policy=duplicate_policy
        )
        return jsonify({
            "success": True,
            "status": status,
            "message": f"Sale record '{sale_id}' {status} successfully.",
            "total_revenue": total_revenue
        })
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400


@app.route("/api/records/<sale_id>", methods=["DELETE"])
def delete_record(sale_id):
    """Deletes a sales record by ID."""
    deleted = db.delete_sale_record(sale_id)
    if deleted:
        return jsonify({"success": True, "message": f"Sale '{sale_id}' deleted."})
    return jsonify({"success": False, "error": f"Sale '{sale_id}' not found."}), 404


# -------------------------------------------------------------
# Public Key & Tunnel Management APIs
# -------------------------------------------------------------
@app.route("/api/public-key", methods=["GET"])
def get_public_key_info():
    """Returns the current public key, tunnel URL, and network info."""
    return jsonify({
        "success": True,
        "public_key": tunnel_manager.get_public_key(),
        "tunnel_status": tunnel_manager.get_status()
    })


@app.route("/api/public-key/regenerate", methods=["POST"])
def regenerate_key():
    """Regenerates a new secure Public API Key."""
    new_key = tunnel_manager.regenerate_public_key()
    return jsonify({
        "success": True,
        "public_key": new_key,
        "message": "Public Key regenerated successfully."
    })


@app.route("/api/tunnel/start", methods=["POST"])
def start_public_tunnel():
    """Initiates the public tunnel (localtunnel) in the background."""
    url = tunnel_manager.start_tunnel()
    return jsonify({
        "success": True,
        "public_url": url,
        "tunnel_info": tunnel_manager.get_status()
    })


# -------------------------------------------------------------
# Utility & Sample Downloads
# -------------------------------------------------------------
@app.route("/api/download-sample/<filename>", methods=["GET"])
def download_sample(filename):
    """Provides downloadable sample CSV files."""
    valid_files = ["sales_sample_clean.csv", "sales_sample_with_errors.csv"]
    if filename not in valid_files:
        return jsonify({"success": False, "error": "Invalid sample file requested."}), 404
    
    sample_dir = os.path.join(os.path.dirname(__file__), "sample_data")
    return send_from_directory(sample_dir, filename, as_attachment=True)


@app.route("/api/export-csv", methods=["GET"])
def export_csv():
    """Exports all current database records as a downloadable CSV."""
    df = db.get_all_sales_df()
    output = io.StringIO()
    df.to_csv(output, index=False)
    csv_str = output.getvalue()
    
    return Response(
        csv_str,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=sales_data_export.csv"}
    )


@app.route("/api/reset-data", methods=["POST"])
def reset_data():
    """Clears all records and optionally reloads clean sample data."""
    reload_sample = request.json.get("reload_sample", True) if request.is_json else True
    db.clear_all_data()
    
    if reload_sample:
        auto_seed_sample_if_empty()
        msg = "Database cleared and re-seeded with clean sample sales records."
    else:
        msg = "Database cleared. Ready for new CSV upload."

    return jsonify({"success": True, "message": msg})


@app.route("/api/db-config", methods=["POST"])
def update_db_config():
    """Switches database between SQLite and MySQL."""
    global db, processor, tunnel_manager
    data = request.get_json(force=True, silent=True) or {}
    engine_type = data.get("db_type", "sqlite").lower()

    if engine_type == "mysql":
        try:
            new_db = DatabaseManager(
                db_type="mysql",
                host=data.get("host", "127.0.0.1"),
                port=int(data.get("port", 3306)),
                user=data.get("user", "root"),
                password=data.get("password", ""),
                database=data.get("database", "sales_analytics_db")
            )
            # Test connection
            conn = new_db.get_connection()
            conn.close()

            db = new_db
            processor = CSVProcessor(db)
            tunnel_manager.db = db
            return jsonify({"success": True, "message": "Successfully connected and switched to MySQL database!"})
        except Exception as e:
            return jsonify({"success": False, "error": f"Failed to connect to MySQL: {e}"}), 400
    else:
        db = DatabaseManager(db_type="sqlite")
        processor = CSVProcessor(db)
        tunnel_manager.db = db
        return jsonify({"success": True, "message": "Switched to SQLite local database."})


if __name__ == "__main__":
    # Start public tunnel in background automatically
    tunnel_manager.start_tunnel()
    
    port = int(os.getenv("PORT", 5000))
    print(f"\n=======================================================")
    print(f"[SERVER] Sales Data Analysis System is RUNNING")
    print(f"[LOCAL]  Web UI:         http://127.0.0.1:{port}")
    print(f"[KEY]    Public API Key: {tunnel_manager.get_public_key()}")
    print(f"[TUNNEL] Public Tunnel:  {tunnel_manager.public_url or 'Starting in background...'}")
    print(f"=======================================================\n")
    
    app.run(host="0.0.0.0", port=port, debug=False)
