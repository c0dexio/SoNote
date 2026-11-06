import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DB_PATH = DATA / "sonote.db"


def connect():
    DATA.mkdir(exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def init_db():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS folders (
          id INTEGER PRIMARY KEY, name TEXT NOT NULL, icon TEXT NOT NULL DEFAULT '📁',
          parent_id INTEGER REFERENCES folders(id), position INTEGER NOT NULL DEFAULT 0,
          deleted INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS pages (
          id INTEGER PRIMARY KEY, title TEXT NOT NULL DEFAULT 'Sans titre', icon TEXT NOT NULL DEFAULT '📝',
          folder_id INTEGER REFERENCES folders(id), favorite INTEGER NOT NULL DEFAULT 0,
          position INTEGER NOT NULL DEFAULT 0, deleted INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS blocks (
          id INTEGER PRIMARY KEY, page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
          type TEXT NOT NULL DEFAULT 'paragraph', content TEXT NOT NULL DEFAULT '', position INTEGER NOT NULL DEFAULT 0
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS page_search USING fts5(title, body, page_id UNINDEXED);
        """)
        if not db.execute("SELECT 1 FROM pages WHERE deleted=0 LIMIT 1").fetchone():
            cur = db.execute("INSERT INTO pages(title,icon) VALUES('Bienvenue dans SoNote','👋')")
            db.execute("INSERT INTO blocks(page_id,type,content,position) VALUES(?,?,?,?)", (cur.lastrowid,"heading1","Votre espace de notes",0))
            db.execute("INSERT INTO blocks(page_id,type,content,position) VALUES(?,?,?,?)", (cur.lastrowid,"paragraph","Tout est prêt. Créez une page ou un dossier depuis la barre latérale. Vos notes restent enregistrées sur cet ordinateur.",1))
            db.execute("INSERT INTO page_search(title,body,page_id) VALUES(?,?,?)",("Bienvenue dans SoNote","Votre espace de notes",cur.lastrowid))
