import sqlite3
import os
import json
import numpy as np

class RetrievalInterface:
    def __init__(self, db_path="runtime/library/rf_signature_library.sqlite", mode="update", top_k=3):
        self.db_path = db_path
        self.mode = mode.lower()
        self.top_k = top_k
        self.status = "SUCCESS"
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_db()

    def _init_db(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''CREATE TABLE IF NOT EXISTS signatures (
                                event_id TEXT PRIMARY KEY,
                                label TEXT,
                                freq_low REAL,
                                freq_high REAL,
                                time_start REAL,
                                time_end REAL,
                                confidence REAL
                            )''')
        except sqlite3.DatabaseError:
            self.status = "DATABASE_CORRUPT"

    def _get_record_count(self, conn):
        cursor = conn.execute('SELECT COUNT(*) FROM signatures')
        return cursor.fetchone()[0]

    def insert_signature(self, event, conn):
        if self.mode in ("off", "read"):
            return False
        
        try:
            tf = event.get('time_freq_estimate', {})
            cursor = conn.execute('''INSERT OR IGNORE INTO signatures 
                          (event_id, label, freq_low, freq_high, time_start, time_end, confidence) 
                          VALUES (?, ?, ?, ?, ?, ?, ?)''', 
                       (event['event_id'], event['label'], 
                        tf.get('freq_low_hz'), tf.get('freq_high_hz'),
                        tf.get('time_start_sec'), tf.get('time_end_sec'),
                        event.get('confidence')))
            return cursor.rowcount > 0
        except Exception:
            return False

    def query(self, detections, image):
        stats = {
            "library_mode": self.mode,
            "database_path": self.db_path,
            "records_before": 0,
            "records_searched": 0,
            "top_k_requested": self.top_k,
            "matches_returned": 0,
            "records_inserted": 0,
            "duplicates_skipped": 0,
            "records_after": 0,
            "database_modified": "No"
        }
        
        if self.mode == "off":
            return [{"retrieval_top3": [], "uncertainty": {}} for _ in detections], "DISABLED", stats
            
        if self.status != "SUCCESS":
            return [{"retrieval_top3": [], "uncertainty": {}} for _ in detections], self.status, stats
            
        results = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                stats["records_before"] = self._get_record_count(conn)
                stats["records_searched"] = stats["records_before"]
                
                for det in detections:
                    tf = det.get('time_freq_estimate', {})
                    f_low = tf.get('freq_low_hz')
                    
                    if f_low is not None:
                        cursor = conn.execute('''
                            SELECT event_id, label, ABS(freq_low - ?) as diff 
                            FROM signatures 
                            WHERE label = ? AND event_id != ?
                            ORDER BY diff ASC 
                            LIMIT ?
                        ''', (f_low, det['label'], det['event_id'], self.top_k))
                        rows = cursor.fetchall()
                        top3 = [{"rank": i+1, "event_id": r['event_id'], "class_name": r['label'], "similarity": 1.0 - (min(r['diff'], 1e6)/1e6)} for i, r in enumerate(rows)]
                        stats["matches_returned"] += len(top3)
                    else:
                        top3 = []
                        
                    results.append({
                        "retrieval_top3": top3,
                        "uncertainty": {}
                    })
                    
                    if self.mode == "update":
                        inserted = self.insert_signature(det, conn)
                        if inserted:
                            stats["records_inserted"] += 1
                        else:
                            stats["duplicates_skipped"] += 1
                            
                conn.commit()
                stats["records_after"] = self._get_record_count(conn)
                if stats["records_inserted"] > 0:
                    stats["database_modified"] = "Yes"
                        
        except sqlite3.DatabaseError:
            self.status = "DATABASE_CORRUPT"
            return [{"retrieval_top3": [], "uncertainty": {}} for _ in detections], self.status, stats
            
        return results, "SUCCESS", stats
