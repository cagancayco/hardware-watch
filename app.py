"""Local hackathon server. Run python app.py; open http://127.0.0.1:8765."""
import argparse, base64, json, mimetypes, sqlite3, threading, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,unquote
from datetime import datetime
import engine

ROOT=Path(__file__).resolve().parent;DATA=ROOT/'data';DATA.mkdir(exist_ok=True)
DB=DATA/'hardware.sqlite3';UPLOADS=DATA/'uploads';UPLOADS.mkdir(exist_ok=True)
LOCK=threading.RLock();CACHE=None
def state():
    global CACHE
    with LOCK:
        if CACHE is None:
            with engine.connect(DB) as db:CACHE=engine.build(db)
        return CACHE
def bootstrap(folder):
    with engine.connect(DB) as db:
        if db.execute('SELECT COUNT(*) FROM imports').fetchone()[0]:return
        for month,asof in [('July','2026-08-14'),('August','2026-09-14')]:
            dirs=list(Path(folder).glob(month+'*'))
            if not dirs:continue
            for p in sorted(dirs[0].glob('*.xlsx')):
                mappings={'fin dashboard':'inventory','Custom Orders':'custom_orders','Bulk Orders':'bulk_orders','Purchase Order and Related':'po_invoices','AP Invoice Summary':'ap_summary','SUHP EAM':'eam','BILLING_MANUAL':'manual'}
                kind=next((k for prefix,k in mappings.items() if p.name.startswith(prefix)),None)
                if not kind:continue
                effective=asof
                if kind=='eam':effective='2026-07-28' if month=='July' else '2026-08-28'
                if kind=='manual':effective='2026-07-29' if month=='July' else '2026-08-26'
                if month=='August' and kind in ('bulk_orders','custom_orders'):effective='2026-09-08'
                result=engine.ingest(db,p.read_bytes(),p.name,kind,effective)
                if not result['duplicate']:(UPLOADS/f"{result['id']}.xlsx").write_bytes(p.read_bytes())
                print(f'Loaded {p.name}',flush=True)
class Handler(BaseHTTPRequestHandler):
    def response(self,value,status=200):
        data=json.dumps(value).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def do_GET(self):
        try:
            path=unquote(urlparse(self.path).path)
            if path=='/api/state':return self.response(state())
            if path.startswith('/api/assets/'):
                with engine.connect(DB) as db:return self.response(engine.timeline(db,path.split('/')[-1]))
            if path.startswith('/api/source/'):
                ident=int(path.split('/')[-1])
                with engine.connect(DB) as db:imp=db.execute('SELECT name FROM imports WHERE id=?',(ident,)).fetchone()
                if not imp:return self.response({'error':'Source not found'},404)
                files=list(UPLOADS.glob(str(ident)+'.*'))
                if not files:return self.response({'error':'Original file unavailable'},404)
                data=files[0].read_bytes();self.send_response(200);self.send_header('Content-Type','application/octet-stream');self.send_header('Content-Disposition','attachment; filename="'+imp['name'].replace('"','')+'"');self.send_header('Content-Length',str(len(data)));self.end_headers();return self.wfile.write(data)
            file=ROOT/'static'/('index.html' if path=='/' else path.lstrip('/'))
            if not file.resolve().is_relative_to((ROOT/'static').resolve()) or not file.is_file():return self.response({'error':'Not found'},404)
            data=file.read_bytes();self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(file)[0] or 'application/octet-stream');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        except Exception as e:traceback.print_exc();self.response({'error':str(e)},500)
    def do_POST(self):
        global CACHE
        try:
            # Local-only mutations; reject cross-origin browser requests.
            origin=self.headers.get('Origin')
            if origin and origin!=f'http://{self.headers.get("Host")}':return self.response({'error':'Cross-origin request blocked'},403)
            length=int(self.headers.get('Content-Length','0'))
            if length>25*1024*1024:return self.response({'error':'Upload exceeds 25 MB request limit'},413)
            body=json.loads(self.rfile.read(length));path=urlparse(self.path).path
            with LOCK,engine.connect(DB) as db:
                if path=='/api/import':
                    content=base64.b64decode(body['content'],validate=True);result=engine.ingest(db,content,body['name'],body['kind'],body['asof'])
                    if not result['duplicate']:(UPLOADS/f"{result['id']}{Path(body['name']).suffix.lower()}").write_bytes(content)
                    CACHE=None;return self.response(result)
                if path=='/api/settings':
                    clean={k:int(body[k]) for k in ('lead_days','buffer_days','grace_days')}
                    if any(v<0 or v>365 for v in clean.values()) or clean['lead_days']==0:raise ValueError('Use 1–365 lead days; 0–365 buffer/grace days.')
                    db.execute('INSERT OR REPLACE INTO settings VALUES(1,?)',(json.dumps(clean),));db.commit();CACHE=None;return self.response({'ok':True})
                if path=='/api/decision':
                    issue=next((i for i in state()['issues'] if i['id']==body['id']),None)
                    if not issue:raise ValueError('Exception no longer exists; refresh first.')
                    if body['state'] not in ('Open','Investigating','Resolved'):raise ValueError('Unsupported decision state.')
                    if body['state']=='Resolved' and not body.get('note','').strip():raise ValueError('Add posting evidence or a documented disposition before resolving.')
                    db.execute('INSERT OR REPLACE INTO decisions VALUES(?,?,?,?,?,?)',(body['id'],body['state'],str(body.get('owner',''))[:200],str(body.get('note',''))[:5000],issue['signature'],datetime.now().isoformat()));db.commit();CACHE=None;return self.response({'ok':True})
            self.response({'error':'Not found'},404)
        except (ValueError,KeyError,TypeError) as e:self.response({'error':str(e)},400)
        except Exception as e:traceback.print_exc();self.response({'error':str(e)},500)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--host',default='127.0.0.1',help='Bind address; use 0.0.0.0 inside a container');parser.add_argument('--port',type=int,default=8765);parser.add_argument('--seed-folder',help='Optional local folder containing July/August exports');args=parser.parse_args()
    if args.seed_folder:bootstrap(args.seed_folder)
    state();print(f'Hardware Watch ready at http://{args.host}:{args.port}',flush=True)
    ThreadingHTTPServer((args.host,args.port),Handler).serve_forever()
if __name__=='__main__':main()
