"""Service to query and index the local Hi-Tek database CSV files."""

import csv
import logging
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Find the repository base directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DB_DIR = BASE_DIR / "DBs" / "hi-tek"
INDEX_DB_PATH = DB_DIR / "hitek_index.db"

# Columns expected in Hi-Tek CSV files
REQUIRED_COLUMNS = ["mobile", "name", "fname", "address", "alt", "circle", "id", "email"]


class HiTekConnectorService:
    """Connector and Indexer for the local Hi-Tek CSV database."""

    _indexing_thread: threading.Thread | None = None
    _indexing_status: str = "idle"  # idle, indexing, completed, failed
    _indexing_error: str | None = None

    def __init__(self) -> None:
        self.db_dir = DB_DIR
        self.index_db_path = INDEX_DB_PATH
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the SQLite index database."""
        self.db_dir.mkdir(parents=True, exist_ok=True)
        
        # Check if table exists and has COLLATE NOCASE in schema
        recreate = False
        if self.index_db_path.exists():
            try:
                with sqlite3.connect(self.index_db_path) as conn:
                    cursor = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='hitek_records'")
                    row = cursor.fetchone()
                    if row and "COLLATE NOCASE" not in row[0]:
                        recreate = True
            except Exception:
                pass
        
        if recreate:
            try:
                with sqlite3.connect(self.index_db_path) as conn:
                    conn.execute("DROP TABLE IF EXISTS hitek_records")
                    conn.execute("DROP TABLE IF EXISTS indexed_files")
                    conn.commit()
            except Exception as e:
                logger.warning("Failed to drop tables for recreation: %s", e)

        with sqlite3.connect(self.index_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS indexed_files (
                    file_path TEXT PRIMARY KEY,
                    file_size INTEGER,
                    last_modified REAL,
                    status TEXT,
                    record_count INTEGER,
                    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS hitek_records (
                    mobile TEXT COLLATE NOCASE,
                    name TEXT COLLATE NOCASE,
                    fname TEXT COLLATE NOCASE,
                    address TEXT COLLATE NOCASE,
                    alt TEXT COLLATE NOCASE,
                    circle TEXT COLLATE NOCASE,
                    id TEXT COLLATE NOCASE,
                    email TEXT COLLATE NOCASE,
                    file_path TEXT
                )
                """
            )
            # Recreate indexes for fast case-insensitive querying
            conn.execute("DROP INDEX IF EXISTS idx_hitek_mobile")
            conn.execute("DROP INDEX IF EXISTS idx_hitek_alt")
            conn.execute("DROP INDEX IF EXISTS idx_hitek_email")
            conn.execute("DROP INDEX IF EXISTS idx_hitek_name")
            conn.execute("DROP INDEX IF EXISTS idx_hitek_fname")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hitek_mobile ON hitek_records(mobile)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hitek_alt ON hitek_records(alt)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hitek_email ON hitek_records(email)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hitek_name ON hitek_records(name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hitek_fname ON hitek_records(fname)")

            # If any files were left in 'indexing' state (e.g. server crashed), reset them to failed
            conn.execute("UPDATE indexed_files SET status = 'failed' WHERE status = 'indexing'")

    def get_status(self) -> Dict[str, Any]:
        """Check the files in the directory and their index status."""
        folder_exists = self.db_dir.exists()
        csv_files = []
        total_records = 0

        # Read status of files from SQLite
        indexed_info = {}
        if folder_exists:
            try:
                with sqlite3.connect(self.index_db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.execute("SELECT * FROM indexed_files")
                    for row in cursor.fetchall():
                        indexed_info[row["file_path"]] = dict(row)
                        if row["status"] == "completed" and row["record_count"]:
                            total_records += row["record_count"]
            except Exception as e:
                logger.error("Failed to read indexed_files table: %s", e)

        # Scan folder for CSVs
        if folder_exists:
            for file_path in self.db_dir.glob("*.csv"):
                abs_path = str(file_path.resolve())
                stat = file_path.stat()
                
                # Check header validity
                valid_headers = False
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        reader = csv.reader(f)
                        header = next(reader)
                        header_normalized = [h.strip().lower().replace('"', '') for h in header]
                        # Verify we have the key columns
                        valid_headers = all(col in header_normalized for col in ["mobile", "name", "email"])
                except Exception:
                    pass

                db_info = indexed_info.get(abs_path, {})
                
                # Determine status of this file
                file_status = db_info.get("status", "pending")
                if file_status == "completed":
                    # Double check if file changed
                    if db_info.get("file_size") != stat.st_size or db_info.get("last_modified") != stat.st_mtime:
                        file_status = "modified"

                csv_files.append({
                    "name": file_path.name,
                    "path": abs_path,
                    "size_bytes": stat.st_size,
                    "valid_headers": valid_headers,
                    "status": file_status,
                    "record_count": db_info.get("record_count", 0)
                })

        # Global index status based on files
        global_status = "completed"
        if any(f["status"] == "indexing" for f in csv_files) or self._indexing_status == "indexing":
            global_status = "indexing"
        elif any(f["status"] in ["pending", "modified"] for f in csv_files):
            global_status = "pending"
        elif any(f["status"] == "failed" for f in csv_files):
            global_status = "failed"

        return {
            "configured": folder_exists and len(csv_files) > 0,
            "folder_exists": folder_exists,
            "index_status": global_status,
            "indexing_error": self._indexing_error,
            "total_records": total_records,
            "csv_files": csv_files,
            "database_path": str(self.index_db_path.resolve())
        }

    def start_indexing(self) -> bool:
        """Trigger background indexing if not already running."""
        status = self.get_status()
        if status["index_status"] == "indexing":
            return False

        self._indexing_status = "indexing"
        self._indexing_error = None
        
        self._indexing_thread = threading.Thread(target=self._run_indexing_task)
        self._indexing_thread.daemon = True
        self._indexing_thread.start()
        return True

    def _run_indexing_task(self) -> None:
        """Background worker to index all CSV files."""
        try:
            status = self.get_status()
            files_to_index = [f for f in status["csv_files"] if f["status"] in ["pending", "modified", "failed"]]
            
            if not files_to_index:
                self._indexing_status = "completed"
                return

            for file_info in files_to_index:
                csv_path = file_info["path"]
                stat = Path(csv_path).stat()
                
                # Mark file as indexing in database
                with sqlite3.connect(self.index_db_path) as conn:
                    conn.execute(
                        """
                        INSERT INTO indexed_files (file_path, file_size, last_modified, status, record_count)
                        VALUES (?, ?, ?, 'indexing', 0)
                        ON CONFLICT(file_path) DO UPDATE SET
                            file_size = excluded.file_size,
                            last_modified = excluded.last_modified,
                            status = 'indexing'
                        """
                    , (csv_path, stat.st_size, stat.st_mtime))
                    conn.commit()

                try:
                    # Perform file indexing
                    count = self._index_single_csv(csv_path)
                    
                    # Mark completed
                    with sqlite3.connect(self.index_db_path) as conn:
                        conn.execute(
                            "UPDATE indexed_files SET status = 'completed', record_count = ? WHERE file_path = ?",
                            (count, csv_path)
                        )
                        conn.commit()
                except Exception as e:
                    logger.error("Error indexing file %s: %s", csv_path, e)
                    with sqlite3.connect(self.index_db_path) as conn:
                        conn.execute(
                            "UPDATE indexed_files SET status = 'failed' WHERE file_path = ?",
                            (csv_path,)
                        )
                        conn.commit()
                    raise e

            self._indexing_status = "completed"
        except Exception as e:
            self._indexing_status = "failed"
            self._indexing_error = str(e)

    def _index_single_csv(self, csv_path: str) -> int:
        """Parse and load single CSV file into SQLite in batches."""
        # 1. Clean existing records for this file from the database
        with sqlite3.connect(self.index_db_path) as conn:
            conn.execute("DELETE FROM hitek_records WHERE file_path = ?", (csv_path,))
            conn.commit()

        # 2. Parse CSV and map columns
        count = 0
        batch = []
        batch_size = 50000

        with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f)
            try:
                header = next(reader)
            except StopIteration:
                return 0

            # Normalize header columns
            header_normalized = [h.strip().lower().replace('"', '') for h in header]
            
            # Map indices
            col_map = {col: header_normalized.index(col) if col in header_normalized else None for col in REQUIRED_COLUMNS}
            
            # Helper to retrieve value safely
            def get_val(row: List[str], col_name: str) -> str:
                idx = col_map[col_name]
                if idx is not None and idx < len(row):
                    return row[idx].strip()
                return ""

            # 3. Read and insert in batches
            with sqlite3.connect(self.index_db_path) as conn:
                # Disable journaling & synchronous checks during index loading to maximize throughput
                conn.execute("PRAGMA journal_mode = OFF")
                conn.execute("PRAGMA synchronous = OFF")

                for row in reader:
                    if not row:
                        continue
                    
                    mobile = get_val(row, "mobile")
                    name = get_val(row, "name")
                    fname = get_val(row, "fname")
                    address = get_val(row, "address")
                    alt = get_val(row, "alt")
                    circle = get_val(row, "circle")
                    id_val = get_val(row, "id")
                    email = get_val(row, "email")

                    # Skip entirely empty rows
                    if not any([mobile, name, email]):
                        continue

                    batch.append((mobile, name, fname, address, alt, circle, id_val, email, csv_path))
                    count += 1

                    if len(batch) >= batch_size:
                        conn.executemany(
                            """
                            INSERT INTO hitek_records (mobile, name, fname, address, alt, circle, id, email, file_path)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            batch
                        )
                        conn.commit()
                        batch.clear()

                if batch:
                    conn.executemany(
                        """
                        INSERT INTO hitek_records (mobile, name, fname, address, alt, circle, id, email, file_path)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        batch
                    )
                    conn.commit()
                    batch.clear()

        return count

    @staticmethod
    def _get_sig(r: Dict[str, Any]) -> tuple:
        return (r.get('mobile') or '', r.get('name') or '', r.get('email') or '')

    def _search_name_fast(self, name: str) -> List[Dict[str, Any]]:
        # 1. Exact match
        results = self._query("SELECT * FROM hitek_records WHERE name = ? LIMIT 100", (name,))
        fname_results = self._query("SELECT * FROM hitek_records WHERE fname = ? LIMIT 100", (name,))
        
        seen = {self._get_sig(r) for r in results}
        for r in fname_results:
            sig = self._get_sig(r)
            if sig not in seen:
                results.append(r)
                seen.add(sig)

        # 2. Prefix match
        prefix_name = self._query("SELECT * FROM hitek_records WHERE name LIKE ? LIMIT 100", (f"{name}%",))
        prefix_fname = self._query("SELECT * FROM hitek_records WHERE fname LIKE ? LIMIT 100", (f"{name}%",))
        
        for r in prefix_name + prefix_fname:
            sig = self._get_sig(r)
            if sig not in seen:
                results.append(r)
                seen.add(sig)
        return results[:100]

    def _search_name_slow(self, name: str, existing_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = {self._get_sig(r) for r in existing_results}
        results = list(existing_results)
        substring_name = self._query("SELECT * FROM hitek_records WHERE name LIKE ? LIMIT 100", (f"%{name}%",))
        substring_fname = self._query("SELECT * FROM hitek_records WHERE fname LIKE ? LIMIT 100", (f"%{name}%",))
        
        for r in substring_name + substring_fname:
            sig = self._get_sig(r)
            if sig not in seen:
                results.append(r)
                seen.add(sig)
        return results[:100]

    def _search_phone_fast(self, phone: str) -> List[Dict[str, Any]]:
        clean_phone = "".join(c for c in phone if c.isdigit())
        if not clean_phone:
            return []

        # 1. Exact match
        results = self._query("SELECT * FROM hitek_records WHERE mobile = ? LIMIT 100", (clean_phone,))
        alt_results = self._query("SELECT * FROM hitek_records WHERE alt = ? LIMIT 100", (clean_phone,))
        
        seen = {self._get_sig(r) for r in results}
        for r in alt_results:
            sig = self._get_sig(r)
            if sig not in seen:
                results.append(r)
                seen.add(sig)

        # 2. Prefix match
        prefix_mobile = self._query("SELECT * FROM hitek_records WHERE mobile LIKE ? LIMIT 100", (f"{clean_phone}%",))
        prefix_alt = self._query("SELECT * FROM hitek_records WHERE alt LIKE ? LIMIT 100", (f"{clean_phone}%",))
        
        for r in prefix_mobile + prefix_alt:
            sig = self._get_sig(r)
            if sig not in seen:
                results.append(r)
                seen.add(sig)
        return results[:100]

    def _search_phone_slow(self, phone: str, existing_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        clean_phone = "".join(c for c in phone if c.isdigit())
        if not clean_phone:
            return existing_results

        seen = {self._get_sig(r) for r in existing_results}
        results = list(existing_results)
        substring_mobile = self._query("SELECT * FROM hitek_records WHERE mobile LIKE ? LIMIT 100", (f"%{clean_phone}%",))
        substring_alt = self._query("SELECT * FROM hitek_records WHERE alt LIKE ? LIMIT 100", (f"%{clean_phone}%",))
        
        for r in substring_mobile + substring_alt:
            sig = self._get_sig(r)
            if sig not in seen:
                results.append(r)
                seen.add(sig)
        return results[:100]

    def _search_email_fast(self, email: str) -> List[Dict[str, Any]]:
        # 1. Exact match
        results = self._query("SELECT * FROM hitek_records WHERE email = ? LIMIT 100", (email,))
        
        seen = {self._get_sig(r) for r in results}
        # 2. Prefix match
        prefix_results = self._query("SELECT * FROM hitek_records WHERE email LIKE ? LIMIT 100", (f"{email}%",))
        for r in prefix_results:
            sig = self._get_sig(r)
            if sig not in seen:
                results.append(r)
                seen.add(sig)
        return results[:100]

    def _search_email_slow(self, email: str, existing_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = {self._get_sig(r) for r in existing_results}
        results = list(existing_results)
        substring_results = self._query("SELECT * FROM hitek_records WHERE email LIKE ? LIMIT 100", (f"%{email}%",))
        for r in substring_results:
            sig = self._get_sig(r)
            if sig not in seen:
                results.append(r)
                seen.add(sig)
        return results[:100]

    def search_by_name(self, name: str) -> List[Dict[str, Any]]:
        """Search indexed Hi-Tek records by name (exact + prefix + substring)."""
        fast = self._search_name_fast(name)
        if fast:
            return fast
        return self._search_name_slow(name, [])

    def search_by_phone(self, phone: str) -> List[Dict[str, Any]]:
        """Search indexed Hi-Tek records by phone (exact + prefix + substring)."""
        fast = self._search_phone_fast(phone)
        if fast:
            return fast
        return self._search_phone_slow(phone, [])

    def search_by_email(self, email: str) -> List[Dict[str, Any]]:
        """Search indexed Hi-Tek records by email (exact + prefix + substring)."""
        fast = self._search_email_fast(email)
        if fast:
            return fast
        return self._search_email_slow(email, [])

    def search_all(self, query: str) -> Dict[str, Any]:
        """Search all fields (name, phone, email) and return in integrated schema."""
        q = query.strip()
        if not q or len(q) < 3:
            return {
                "database_path": str(self.index_db_path.resolve()),
                "by_username": [],
                "by_phone": [],
                "by_email": []
            }

        # 1. Fast match (exact and prefix - all use indexes, take <1ms total)
        by_username_raw = self._search_name_fast(q)
        by_phone_raw = self._search_phone_fast(q)
        by_email_raw = self._search_email_fast(q)

        # Map helper
        def map_record(r: Dict[str, Any]) -> Dict[str, Any]:
            alt_user = f"Father: {r['fname']}" if r.get("fname") else ""
            if r.get("alt"):
                alt_user += f" (Alt Phone: {r['alt']})"
            
            return {
                "username": r.get("name") or "Unknown",
                "phone": r.get("mobile") or "N/A",
                "email": r.get("email") or "N/A",
                "address": r.get("address") or "N/A",
                "alternate_username": alt_user.strip() or "N/A",
                "platform": "Hi-Tek DB",
                "data_source": f"Hi-Tek (Circle: {r.get('circle') or 'N/A'}, ID: {r.get('id') or 'N/A'})",
                "added_date": "2026-06-30"
            }

        def build_response(users, phones, emails):
            return {
                "database_path": str(self.index_db_path.resolve()),
                "by_username": [map_record(r) for r in users],
                "by_phone": [map_record(r) for r in phones],
                "by_email": [map_record(r) for r in emails]
            }

        # If we have any fast matches, return immediately to bypass slow scans
        if by_username_raw or by_phone_raw or by_email_raw:
            return build_response(by_username_raw, by_phone_raw, by_email_raw)

        # 2. Substring fallback (only if no fast matches were found anywhere)
        by_username_raw = self._search_name_slow(q, by_username_raw)
        by_phone_raw = self._search_phone_slow(q, by_phone_raw)
        by_email_raw = self._search_email_slow(q, by_email_raw)

        return build_response(by_username_raw, by_phone_raw, by_email_raw)

    def search_strict(self, username: str, full_name: str | None = None) -> Dict[str, Any]:
        by_username = []
        by_phone = []
        by_email = []

        def is_email(q: str) -> bool:
            return "@" in q

        def is_phone(q: str) -> bool:
            clean = "".join(c for c in q if c.isdigit())
            return len(clean) >= 7

        import re
        def generate_search_variants(query: str) -> List[str]:
            variants = []
            q_clean = query.strip()
            if not q_clean:
                return variants
            variants.append(q_clean)
            
            # 1. Strip trailing digits (e.g. "amit_chaudhary1111" -> "amit_chaudhary")
            without_trailing_digits = re.sub(r'\d+$', '', q_clean)
            if without_trailing_digits and without_trailing_digits != q_clean:
                variants.append(without_trailing_digits)
                
            # 2. Simplify by removing spaces, underscores, dots, and dashes
            def simplify(s: str) -> str:
                return re.sub(r'[\s_\.\-]+', '', s)
                
            simple_q = simplify(q_clean)
            if simple_q and simple_q not in variants:
                variants.append(simple_q)
                
            simple_without_digits = simplify(without_trailing_digits)
            if simple_without_digits and simple_without_digits not in variants:
                variants.append(simple_without_digits)
                
            return list(dict.fromkeys(variants))

        targets = [username]
        if full_name:
            targets.append(full_name)

        for t in targets:
            t_clean = t.strip()
            if not t_clean or len(t_clean) < 3:
                continue

            if is_email(t_clean):
                by_email.extend(self._search_email_fast(t_clean))
            elif is_phone(t_clean):
                by_phone.extend(self._search_phone_fast(t_clean))
            else:
                variants = generate_search_variants(t_clean)
                for var in variants:
                    if len(var) < 3:
                        continue
                    by_username.extend(self._search_name_fast(var))

        # Map records to UI schema
        def map_record(r: Dict[str, Any]) -> Dict[str, Any]:
            alt_user = f"Father: {r['fname']}" if r.get("fname") else ""
            if r.get("alt"):
                alt_user += f" (Alt Phone: {r['alt']})"
            return {
                "username": r.get("name") or "Unknown",
                "phone": r.get("mobile") or "N/A",
                "email": r.get("email") or "N/A",
                "address": r.get("address") or "N/A",
                "alternate_username": alt_user.strip() or "N/A",
                "platform": "Hi-Tek DB",
                "data_source": f"Hi-Tek (Circle: {r.get('circle') or 'N/A'}, ID: {r.get('id') or 'N/A'})",
                "added_date": "2026-06-30"
            }

        def dedup_mapped(lst):
            seen = set()
            res = []
            for r in lst:
                sig = (r.get("mobile") or "", r.get("name") or "", r.get("email") or "")
                if sig not in seen:
                    seen.add(sig)
                    res.append(map_record(r))
            return res

        return {
            "database_path": str(self.index_db_path.resolve()),
            "by_username": dedup_mapped(by_username),
            "by_phone": dedup_mapped(by_phone),
            "by_email": dedup_mapped(by_email),
        }

    def _query(self, sql: str, params: tuple) -> List[Dict[str, Any]]:
        """Utility query execution helper."""
        try:
            with sqlite3.connect(self.index_db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(sql, params)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error("Error executing query '%s' on index DB: %s", sql, e)
            return []
