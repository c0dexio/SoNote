import json
from flask import Flask, jsonify, render_template, request, abort, Response
from .database import connect, init_db


def create_app():
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    init_db()

    def page_row(db, page_id):
        row = db.execute("SELECT * FROM pages WHERE id=?", (page_id,)).fetchone()
        if not row: abort(404)
        return row

    def tree(db):
        folders = [dict(r) for r in db.execute("SELECT * FROM folders WHERE deleted=0 ORDER BY position,name")]
        pages = [dict(r) for r in db.execute("SELECT id,title,icon,folder_id,favorite,updated_at FROM pages WHERE deleted=0 ORDER BY favorite DESC,position,title")]
        def children(parent):
            return [{**f,"pages":[p for p in pages if p["folder_id"]==f["id"]],"children":children(f["id"])} for f in folders if f["parent_id"]==parent]
        return {"folders":children(None),"pages":[p for p in pages if p["folder_id"] is None],"favorites":[p for p in pages if p["favorite"]]}

    @app.get("/")
    def home(): return render_template("index.html")

    @app.get("/api/tree")
    def get_tree():
        with connect() as db: return jsonify(tree(db))

    @app.post("/api/pages")
    def create_page():
        data=request.get_json(force=True)
        with connect() as db:
            cur=db.execute("INSERT INTO pages(title,icon,folder_id) VALUES(?,?,?)",(data.get("title","Nouvelle page"),data.get("icon","📝"),data.get("folder_id")))
            db.execute("INSERT INTO blocks(page_id,type,content,position) VALUES(?,?,?,0)",(cur.lastrowid,"paragraph",""))
            return jsonify({"id":cur.lastrowid}),201

    @app.get("/api/pages/<int:page_id>")
    def get_page(page_id):
        with connect() as db:
            page=dict(page_row(db,page_id))
            if page["deleted"]: abort(404)
            page["blocks"]=[dict(r) for r in db.execute("SELECT * FROM blocks WHERE page_id=? ORDER BY position,id",(page_id,))]
            return jsonify(page)

    @app.put("/api/pages/<int:page_id>")
    def save_page(page_id):
        data=request.get_json(force=True)
        with connect() as db:
            page_row(db,page_id)
            db.execute("UPDATE pages SET title=?,icon=?,folder_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(data.get("title","Sans titre"),data.get("icon","📝"),data.get("folder_id"),page_id))
            db.execute("DELETE FROM blocks WHERE page_id=?",(page_id,))
            for i,b in enumerate(data.get("blocks",[])):
                db.execute("INSERT INTO blocks(page_id,type,content,position) VALUES(?,?,?,?)",(page_id,b.get("type","paragraph"),b.get("content",""),i))
            body=" ".join(str(b.get("content","")) for b in data.get("blocks",[]))
            db.execute("DELETE FROM page_search WHERE page_id=?",(str(page_id),))
            db.execute("INSERT INTO page_search(title,body,page_id) VALUES(?,?,?)",(data.get("title","Sans titre"),body,page_id))
            return jsonify({"ok":True})

    @app.post("/api/folders")
    def create_folder():
        d=request.get_json(force=True)
        parent_id=d.get("parent_id")
        with connect() as db:
            if parent_id is not None and not db.execute("SELECT 1 FROM folders WHERE id=? AND deleted=0",(parent_id,)).fetchone(): abort(400,"Dossier parent introuvable")
            c=db.execute("INSERT INTO folders(name,icon,parent_id) VALUES(?,?,?)",(d.get("name","Nouveau dossier"),d.get("icon","📁"),parent_id))
            return jsonify({"id":c.lastrowid}),201

    @app.patch("/api/folders/<int:folder_id>")
    def update_folder(folder_id):
        d=request.get_json(force=True)
        with connect() as db:
            if not db.execute("SELECT 1 FROM folders WHERE id=? AND deleted=0",(folder_id,)).fetchone(): abort(404)
            changes=[]; values=[]
            if "name" in d: changes.append("name=?"); values.append(d["name"])
            if "parent_id" in d:
                parent_id=d["parent_id"]
                if parent_id is not None:
                    if parent_id==folder_id: abort(400,"Un dossier ne peut pas être son propre parent")
                    if not db.execute("SELECT 1 FROM folders WHERE id=? AND deleted=0",(parent_id,)).fetchone(): abort(400,"Dossier parent introuvable")
                    descendants=set(); pending=[folder_id]
                    while pending:
                        node=pending.pop()
                        if node in descendants: continue
                        descendants.add(node)
                        pending.extend(r[0] for r in db.execute("SELECT id FROM folders WHERE parent_id=?",(node,)))
                    if parent_id in descendants: abort(400,"Impossible de déplacer un dossier dans son propre sous-dossier")
                changes.append("parent_id=?"); values.append(parent_id)
            if changes: db.execute("UPDATE folders SET "+", ".join(changes)+",updated_at=CURRENT_TIMESTAMP WHERE id=?",(*values,folder_id))
            return jsonify({"ok":True})

    @app.delete("/api/folders/<int:folder_id>")
    def delete_folder(folder_id):
        with connect() as db: db.execute("UPDATE folders SET deleted=1 WHERE id=?",(folder_id,))
        return jsonify({"ok":True})

    @app.patch("/api/pages/<int:page_id>")
    def update_page(page_id):
        d=request.get_json(force=True)
        with connect() as db:
            page_row(db,page_id)
            allowed={k:d[k] for k in ("title","icon","folder_id","favorite") if k in d}
            if allowed: db.execute("UPDATE pages SET "+", ".join(k+"=?" for k in allowed)+",updated_at=CURRENT_TIMESTAMP WHERE id=?",(*allowed.values(),page_id))
            return jsonify({"ok":True})

    @app.delete("/api/pages/<int:page_id>")
    def delete_page(page_id):
        with connect() as db: db.execute("UPDATE pages SET deleted=1 WHERE id=?",(page_id,))
        return jsonify({"ok":True})

    @app.get("/api/search")
    def search():
        q=request.args.get("q","").strip()
        if not q:return jsonify([])
        with connect() as db:
            try:
                rows=db.execute("SELECT p.id,p.title,p.icon,s.body FROM page_search s JOIN pages p ON CAST(s.page_id AS INTEGER)=p.id WHERE page_search MATCH ? AND p.deleted=0 LIMIT 30",(q.replace('"','')+"*",)).fetchall()
            except Exception:
                rows=db.execute("SELECT p.id,p.title,p.icon,substr(s.body,1,120) body FROM page_search s JOIN pages p ON CAST(s.page_id AS INTEGER)=p.id WHERE (p.title LIKE ? OR s.body LIKE ?) AND p.deleted=0 LIMIT 30",(f"%{q}%",f"%{q}%")).fetchall()
            return jsonify([dict(r) for r in rows])

    @app.get("/api/trash")
    def trash():
        with connect() as db:
            return jsonify({"pages":[dict(r) for r in db.execute("SELECT id,title,icon FROM pages WHERE deleted=1")],"folders":[dict(r) for r in db.execute("SELECT id,name,icon FROM folders WHERE deleted=1")]})

    def purge_page(db, page_id):
        db.execute("DELETE FROM page_search WHERE page_id=?", (str(page_id),))
        db.execute("DELETE FROM pages WHERE id=?", (page_id,))

    def purge_folder(db, folder_id):
        folder_ids=[]; pending=[folder_id]
        while pending:
            current=pending.pop()
            if current in folder_ids: continue
            folder_ids.append(current)
            pending.extend(r[0] for r in db.execute("SELECT id FROM folders WHERE parent_id=?", (current,)))
        if not folder_ids: return
        marks=",".join("?" for _ in folder_ids)
        page_ids=[r[0] for r in db.execute(f"SELECT id FROM pages WHERE folder_id IN ({marks})", folder_ids)]
        for page_id in page_ids: purge_page(db, page_id)
        for current in reversed(folder_ids): db.execute("DELETE FROM folders WHERE id=?", (current,))

    @app.post("/api/trash/purge")
    def purge_trash():
        data=request.get_json(force=True)
        with connect() as db:
            if data.get("all"):
                for row in db.execute("SELECT id FROM pages WHERE deleted=1").fetchall(): purge_page(db,row[0])
                for row in db.execute("SELECT id FROM folders WHERE deleted=1").fetchall(): purge_folder(db,row[0])
            else:
                items=data.get("items",[])
                for item in items:
                    kind=item.get("kind"); item_id=item.get("id")
                    if kind=="pages":
                        row=db.execute("SELECT deleted FROM pages WHERE id=?",(item_id,)).fetchone()
                        if row and row[0]: purge_page(db,item_id)
                    elif kind=="folders":
                        row=db.execute("SELECT deleted FROM folders WHERE id=?",(item_id,)).fetchone()
                        if row and row[0]: purge_folder(db,item_id)
                    else: abort(400,"Type d’élément invalide")
        return jsonify({"ok":True})

    @app.post("/api/restore/<kind>/<int:item_id>")
    def restore(kind,item_id):
        if kind not in ("pages","folders"): abort(404)
        with connect() as db: db.execute(f"UPDATE {kind} SET deleted=0 WHERE id=?",(item_id,))
        return jsonify({"ok":True})

    @app.get("/api/export/<int:page_id>")
    def export_page(page_id):
        with connect() as db:
            page=page_row(db,page_id); blocks=db.execute("SELECT type,content FROM blocks WHERE page_id=? ORDER BY position",(page_id,)).fetchall()
            lines=["# "+page["title"],""]
            for b in blocks:
                c=b["content"]; t=b["type"]
                if t.startswith("heading"): lines += ["#"*int(t[-1])+" "+c,""]
                elif t=="quote": lines += ["> "+c,""]
                elif t=="code": lines += ["```",c,"```",""]
                elif t=="bullet": lines += ["- "+c]
                elif t=="numbered": lines += ["1. "+c]
                elif t=="divider": lines += ["---",""]
                else: lines += [c,""]
            return Response("\n".join(lines),mimetype="text/markdown",headers={"Content-Disposition":f'attachment; filename="sonote-{page_id}.md"'})

    return app
