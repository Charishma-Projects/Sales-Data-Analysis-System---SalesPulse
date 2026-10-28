"""
database.py - Unified Database Layer for Sales Data Analysis System
Supports SQLite (zero-config default) and MySQL (production/enterprise).
Matches entities:
  - products(product_id, product_name, category)
  - sales(sale_id, product_id, sale_date, quantity, unit_price, region)
"""

import os
import sqlite3
import pymysql
from pymysql.cursors import DictCursor
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple

DB_TYPE = os.getenv("DB_TYPE", "sqlite").lower()
SQLITE_PATH = os.getenv("SQLITE_PATH", os.path.join(os.path.dirname(__file__), "sales_system.db"))

MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DB = os.getenv("MYSQL_DB", "sales_analytics_db")


class DatabaseManager:
    def __init__(self, db_type: Optional[str] = None, **custom_kwargs):
        self.db_type = db_type or DB_TYPE
        self.sqlite_path = custom_kwargs.get("sqlite_path", SQLITE_PATH)
        self.mysql_config = {
            "host": custom_kwargs.get("host", MYSQL_HOST),
            "port": custom_kwargs.get("port", MYSQL_PORT),
            "user": custom_kwargs.get("user", MYSQL_USER),
            "password": custom_kwargs.get("password", MYSQL_PASSWORD),
            "database": custom_kwargs.get("database", MYSQL_DB),
            "cursorclass": DictCursor,
            "autocommit": True,
            "charset": "utf8mb4"
        }
        self.init_db()

    def get_connection(self):
        """Returns an active database connection depending on configured engine."""
        if self.db_type == "mysql":
            try:
                return pymysql.connect(**self.mysql_config)
            except pymysql.err.OperationalError as e:
                # If database does not exist, try creating it
                if e.args[0] in (1049,):
                    cfg_no_db = dict(self.mysql_config)
                    db_name = cfg_no_db.pop("database")
                    conn_root = pymysql.connect(**cfg_no_db)
                    with conn_root.cursor() as cur:
                        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` DEFAULT CHARACTER SET utf8mb4;")
                    conn_root.close()
                    return pymysql.connect(**self.mysql_config)
                raise e
        else:
            conn = sqlite3.connect(self.sqlite_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            return conn

    def init_db(self):
        """Initializes tables matching exact required entities & system metadata."""
        if self.db_type == "mysql":
            self._init_mysql()
        else:
            self._init_sqlite()

    def _init_sqlite(self):
        conn = sqlite3.connect(self.sqlite_path)
        with conn:
            cur = conn.cursor()
            # Products table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    product_id TEXT PRIMARY KEY,
                    product_name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Sales table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sales (
                    sale_id TEXT PRIMARY KEY,
                    product_id TEXT NOT NULL,
                    sale_date TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    unit_price REAL NOT NULL,
                    region TEXT NOT NULL,
                    total_revenue REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE
                );
            """)

            # System settings table for public key / configuration
            cur.execute("""
                CREATE TABLE IF NOT EXISTS system_settings (
                    key_name TEXT PRIMARY KEY,
                    key_value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()
        conn.close()

    def _init_mysql(self):
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS products (
                        product_id VARCHAR(64) PRIMARY KEY,
                        product_name VARCHAR(255) NOT NULL,
                        category VARCHAR(100) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS sales (
                        sale_id VARCHAR(64) PRIMARY KEY,
                        product_id VARCHAR(64) NOT NULL,
                        sale_date DATE NOT NULL,
                        quantity INT NOT NULL,
                        unit_price DECIMAL(10, 2) NOT NULL,
                        region VARCHAR(100) NOT NULL,
                        total_revenue DECIMAL(12, 2) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS system_settings (
                        key_name VARCHAR(100) PRIMARY KEY,
                        key_value TEXT NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)
            conn.close()
        except Exception as e:
            # Fallback to SQLite if MySQL connection fails during startup
            print(f"[DatabaseManager] MySQL init failed ({e}). Falling back to SQLite.")
            self.db_type = "sqlite"
            self._init_sqlite()

    def upsert_product(self, product_id: str, product_name: str, category: str):
        """Insert or update a product."""
        conn = self.get_connection()
        try:
            if self.db_type == "mysql":
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO products (product_id, product_name, category)
                        VALUES (%s, %s, %s)
                        ON DUPLICATE KEY UPDATE product_name = VALUES(product_name), category = VALUES(category)
                    """, (product_id, product_name, category))
            else:
                with conn:
                    conn.execute("""
                        INSERT INTO products (product_id, product_name, category)
                        VALUES (?, ?, ?)
                        ON CONFLICT(product_id) DO UPDATE SET 
                            product_name = excluded.product_name,
                            category = excluded.category
                    """, (product_id, product_name, category))
        finally:
            conn.close()

    def get_setting(self, key_name: str, default: Optional[str] = None) -> Optional[str]:
        """Fetch a system setting / public key."""
        conn = self.get_connection()
        try:
            if self.db_type == "mysql":
                with conn.cursor() as cur:
                    cur.execute("SELECT key_value FROM system_settings WHERE key_name = %s", (key_name,))
                    row = cur.fetchone()
                    return row["key_value"] if row else default
            else:
                cur = conn.cursor()
                cur.execute("SELECT key_value FROM system_settings WHERE key_name = ?", (key_name,))
                row = cur.fetchone()
                return row[0] if row else default
        finally:
            conn.close()

    def set_setting(self, key_name: str, key_value: str):
        """Save a system setting / public key."""
        conn = self.get_connection()
        try:
            if self.db_type == "mysql":
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO system_settings (key_name, key_value)
                        VALUES (%s, %s)
                        ON DUPLICATE KEY UPDATE key_value = VALUES(key_value)
                    """, (key_name, key_value))
            else:
                with conn:
                    conn.execute("""
                        INSERT INTO system_settings (key_name, key_value)
                        VALUES (?, ?)
                        ON CONFLICT(key_name) DO UPDATE SET key_value = excluded.key_value
                    """, (key_name, key_value))
        finally:
            conn.close()

    def get_all_sales_df(self) -> pd.DataFrame:
        """Returns all sales joined with product data as a clean Pandas DataFrame."""
        conn = self.get_connection()
        query = """
            SELECT 
                s.sale_id,
                s.product_id,
                p.product_name,
                p.category,
                s.sale_date,
                s.quantity,
                s.unit_price,
                s.total_revenue,
                s.region,
                s.created_at
            FROM sales s
            LEFT JOIN products p ON s.product_id = p.product_id
            ORDER BY s.sale_date DESC
        """
        try:
            df = pd.read_sql_query(query, conn)
            if not df.empty:
                df["sale_date"] = pd.to_datetime(df["sale_date"], errors="coerce")
                df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0).astype(int)
                df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce").fillna(0.0)
                df["total_revenue"] = pd.to_numeric(df["total_revenue"], errors="coerce").fillna(0.0)
            return df
        finally:
            conn.close()

    def get_all_products(self) -> List[Dict[str, Any]]:
        """Return list of all products."""
        conn = self.get_connection()
        try:
            if self.db_type == "mysql":
                with conn.cursor() as cur:
                    cur.execute("SELECT product_id, product_name, category, created_at FROM products ORDER BY product_name ASC")
                    return cur.fetchall()
            else:
                cur = conn.cursor()
                cur.execute("SELECT product_id, product_name, category, created_at FROM products ORDER BY product_name ASC")
                rows = cur.fetchall()
                return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_sales_records(self, limit: int = 100, offset: int = 0, region: Optional[str] = None, category: Optional[str] = None) -> Tuple[List[Dict[str, Any]], int]:
        """Fetch paginated sales records with optional filtering."""
        conn = self.get_connection()
        try:
            where_clauses = []
            params = []
            if region:
                where_clauses.append("s.region = %s" if self.db_type == "mysql" else "s.region = ?")
                params.append(region)
            if category:
                where_clauses.append("p.category = %s" if self.db_type == "mysql" else "p.category = ?")
                params.append(category)

            where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
            
            # Count query
            count_query = f"SELECT COUNT(*) as total FROM sales s LEFT JOIN products p ON s.product_id = p.product_id {where_sql}"
            
            # Data query
            param_symbol = "%s" if self.db_type == "mysql" else "?"
            data_query = f"""
                SELECT 
                    s.sale_id,
                    s.product_id,
                    COALESCE(p.product_name, 'Unknown') as product_name,
                    COALESCE(p.category, 'Uncategorized') as category,
                    s.sale_date,
                    s.quantity,
                    s.unit_price,
                    s.total_revenue,
                    s.region,
                    s.created_at
                FROM sales s
                LEFT JOIN products p ON s.product_id = p.product_id
                {where_sql}
                ORDER BY s.sale_date DESC
                LIMIT {param_symbol} OFFSET {param_symbol}
            """

            if self.db_type == "mysql":
                with conn.cursor() as cur:
                    cur.execute(count_query, tuple(params))
                    total_count = cur.fetchone()["total"]
                    
                    data_params = list(params) + [limit, offset]
                    cur.execute(data_query, tuple(data_params))
                    records = cur.fetchall()
                    return records, total_count
            else:
                cur = conn.cursor()
                cur.execute(count_query, tuple(params))
                total_count = cur.fetchone()[0]
                
                data_params = list(params) + [limit, offset]
                cur.execute(data_query, tuple(data_params))
                rows = cur.fetchall()
                records = [dict(r) for r in rows]
                return records, total_count
        finally:
            conn.close()

    def check_sale_exists(self, sale_id: str) -> bool:
        """Check if a sale record exists."""
        conn = self.get_connection()
        try:
            if self.db_type == "mysql":
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM sales WHERE sale_id = %s", (sale_id,))
                    return cur.fetchone() is not None
            else:
                cur = conn.cursor()
                cur.execute("SELECT 1 FROM sales WHERE sale_id = ?", (sale_id,))
                return cur.fetchone() is not None
        finally:
            conn.close()

    def insert_sale_record(self, sale_id: str, product_id: str, sale_date: str, 
                           quantity: int, unit_price: float, region: str, 
                           total_revenue: float, duplicate_policy: str = "skip") -> str:
        """
        Insert sale record according to duplicate policy ('skip', 'replace', 'abort').
        Returns status: 'inserted', 'skipped', 'replaced'.
        Raises ValueError on duplicate if duplicate_policy == 'abort'.
        """
        exists = self.check_sale_exists(sale_id)
        if exists:
            if duplicate_policy == "abort":
                raise ValueError(f"Duplicate sale_id '{sale_id}' detected while policy is 'abort'.")
            elif duplicate_policy == "skip":
                return "skipped"
            elif duplicate_policy == "replace":
                conn = self.get_connection()
                try:
                    if self.db_type == "mysql":
                        with conn.cursor() as cur:
                            cur.execute("""
                                UPDATE sales 
                                SET product_id = %s, sale_date = %s, quantity = %s, unit_price = %s, region = %s, total_revenue = %s
                                WHERE sale_id = %s
                            """, (product_id, sale_date, quantity, unit_price, region, total_revenue, sale_id))
                    else:
                        with conn:
                            conn.execute("""
                                UPDATE sales 
                                SET product_id = ?, sale_date = ?, quantity = ?, unit_price = ?, region = ?, total_revenue = ?
                                WHERE sale_id = ?
                            """, (product_id, sale_date, quantity, unit_price, region, total_revenue, sale_id))
                    return "replaced"
                finally:
                    conn.close()

        # Insert new record
        conn = self.get_connection()
        try:
            if self.db_type == "mysql":
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO sales (sale_id, product_id, sale_date, quantity, unit_price, region, total_revenue)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (sale_id, product_id, sale_date, quantity, unit_price, region, total_revenue))
            else:
                with conn:
                    conn.execute("""
                        INSERT INTO sales (sale_id, product_id, sale_date, quantity, unit_price, region, total_revenue)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (sale_id, product_id, sale_date, quantity, unit_price, region, total_revenue))
            return "inserted"
        finally:
            conn.close()

    def delete_sale_record(self, sale_id: str) -> bool:
        """Delete a single sale record."""
        conn = self.get_connection()
        try:
            if self.db_type == "mysql":
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM sales WHERE sale_id = %s", (sale_id,))
                    return cur.rowcount > 0
            else:
                with conn:
                    cur = conn.execute("DELETE FROM sales WHERE sale_id = ?", (sale_id,))
                    return cur.rowcount > 0
        finally:
            conn.close()

    def clear_all_data(self):
        """Clears all records for testing/resetting."""
        conn = self.get_connection()
        try:
            if self.db_type == "mysql":
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM sales")
                    cur.execute("DELETE FROM products")
            else:
                with conn:
                    conn.execute("DELETE FROM sales")
                    conn.execute("DELETE FROM products")
        finally:
            conn.close()

# Singleton instance for general use
db = DatabaseManager()
