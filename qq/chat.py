"""Local browser chat frontend for QonQrete.

The chat is deliberately a thin task launcher: every submitted message becomes
a temporary Markdown task inside the selected destination directory and invokes
the normal `qq run <task> <destination>` path, so the exact same TUI/dashboard
pipeline is used as the CLI.
"""
from __future__ import annotations
import datetime as _dt
import html
import json
import os
import subprocess
import sys
import threading
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

_HTML = r"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>QonQrete Chat</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;min-height:100vh;background:#0b0e12;color:#eee;font:15px system-ui,sans-serif;display:flex;justify-content:center}
.wrap{width:min(900px,96vw);padding:28px 0 90px}.brand{display:flex;align-items:center;gap:12px;margin-bottom:26px}.brand img{width:58px;height:58px;object-fit:contain;border-radius:14px}.brand h1{margin:0;font-size:25px}.sub{opacity:.65}
.card{background:#12171d;border:1px solid #2a323b;border-radius:18px;padding:20px;box-shadow:0 16px 50px #0007}.messages{min-height:280px;max-height:52vh;overflow:auto;padding:8px}.msg{padding:14px 16px;border-radius:14px;margin:10px 0;white-space:pre-wrap}.user{background:#202a35;margin-left:15%}.sys{background:#171e25;border:1px solid #2a323b}
label{display:block;font-weight:700;margin:16px 0 7px}textarea,input{width:100%;background:#0c1116;color:#fff;border:1px solid #303943;border-radius:11px;padding:12px;font:inherit}textarea{min-height:130px;resize:vertical}.row{display:flex;gap:9px}.row input{flex:1}button{border:0;border-radius:11px;padding:12px 17px;background:#d99b2b;color:#101010;font-weight:800;cursor:pointer}button.secondary{background:#2b333c;color:#fff}button:disabled{opacity:.45;cursor:not-allowed}.actions{display:flex;justify-content:flex-end;margin-top:14px}.status{margin-top:12px;min-height:24px;opacity:.8}.mascot{position:fixed;right:18px;bottom:15px;width:120px;height:120px;object-fit:contain;filter:drop-shadow(0 0 18px #000)}@media(max-width:650px){.user{margin-left:0}.mascot{width:80px;height:80px}}
</style></head>
<body><main class="wrap">
<div class="brand"><img src="/asset/squid"><div><h1>QonQrete Chat</h1><div class="sub">Describe what you want built. Then let the squid pour it.</div></div></div>
<section class="card"><div id="messages" class="messages"><div class="msg sys">Ready. Give QonQrete a task and choose where it should be built.</div></div>
<label for="destination">Destination directory</label>
<div class="row"><input id="destination" required><button class="secondary" id="browse" type="button">Browse…</button></div>
<label for="prompt">Task</label><textarea id="prompt" placeholder="What should QonQrete build?"></textarea>
<div class="actions"><button id="send">Build with QonQrete</button></div><div id="status" class="status"></div></section>
</main><img class="mascot" src="/asset/squid" alt="QonQrete cybersquid">
<script>
const d=document.getElementById('destination'),p=document.getElementById('prompt'),b=document.getElementById('send'),st=document.getElementById('status'),m=document.getElementById('messages');
const pad=n=>String(n).padStart(2,'0');
const now=new Date(), rootHint='__ROOT_HINT__';
d.value=rootHint+'/runs/qonqrete-run-'+now.getFullYear()+'-'+pad(now.getMonth()+1)+'-'+pad(now.getDate())+'_'+pad(now.getHours())+'_'+pad(now.getMinutes());
document.getElementById('browse').onclick=async()=>{try{const r=await fetch('/api/browse');const j=await r.json();if(!r.ok)throw new Error(j.error||'Folder picker unavailable');if(j.path)d.value=j.path;}catch(e){st.textContent=e.message+' You can type the destination path manually.'}};
function add(cls,text){const x=document.createElement('div');x.className='msg '+cls;x.textContent=text;m.appendChild(x);m.scrollTop=m.scrollHeight}
async function build(){const prompt=p.value.trim(),dest=d.value.trim();if(!prompt||!dest){st.textContent='Task and destination are required.';return}
b.disabled=true;p.disabled=true;d.disabled=true;st.textContent='QonQrete is building… input locked until the run finishes.';add('user',prompt);
try{const r=await fetch('/api/build',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt,destination:dest})});const j=await r.json();if(!r.ok)throw new Error(j.error||'Build failed to start');st.textContent='Run '+j.run_id+' started. TUI + briQsQope are handling it.';p.value='';poll(j.run_id)}catch(e){st.textContent=e.message;b.disabled=false;p.disabled=false;d.disabled=false}}
async function poll(id){try{const r=await fetch('/api/status?id='+encodeURIComponent(id));const j=await r.json();if(j.running){st.textContent='Run '+id+' is '+j.state+'…';setTimeout(()=>poll(id),1500)}else{st.textContent='Run '+id+' finished ('+j.state+'). You can build another task.';b.disabled=false;p.disabled=false;d.disabled=false}}catch(e){setTimeout(()=>poll(id),2000)}}
b.onclick=build;p.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();build()}})
</script></body></html>"""

class _Handler(BaseHTTPRequestHandler):
    server_version = "QonQreteChat/1.0"
    def log_message(self, fmt, *args): pass
    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        data=body.encode() if isinstance(body,str) else body
        self.send_response(code); self.send_header("Content-Type",ctype); self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        u=urlparse(self.path)
        if u.path=="/":
            root=html.escape(self.server.root, quote=True)
            self._send(200,_HTML.replace("__ROOT_HINT__",root)); return
        if u.path=="/asset/squid":
            path=os.path.join(self.server.repo_root,"qq","web","qonqrete-bottom-right.jpg")
            try: self._send(200,open(path,"rb").read(),"image/jpeg")
            except OSError: self._send(404,b"")
            return
        if u.path=="/api/browse":
            try:
                import tkinter as tk
                from tkinter import filedialog
                root=tk.Tk(); root.withdraw(); root.attributes("-topmost",True)
                selected=filedialog.askdirectory(initialdir=self.server.root,title="Choose QonQrete destination")
                root.destroy()
                self._send(200,json.dumps({"path":selected}),"application/json")
            except Exception as e:
                self._send(500,json.dumps({"error":f"Native folder picker unavailable: {e}"}),"application/json")
            return
        if u.path=="/api/status":
            from urllib.parse import parse_qs
            rid=parse_qs(u.query).get("id",[""])[0]
            with self.server.lock:
                rec=self.server.runs.get(rid,{"running":False,"state":"unknown"})
            self._send(200,json.dumps(rec),"application/json"); return
        self._send(404,"not found")
    def do_POST(self):
        if self.path!="/api/build": self._send(404,"not found"); return
        with self.server.lock:
            if any(v.get("running") for v in self.server.runs.values()):
                self._send(409,json.dumps({"error":"A QonQrete run is already in progress."}),"application/json"); return
        try:
            n=int(self.headers.get("Content-Length","0")); payload=json.loads(self.rfile.read(n))
            prompt=str(payload.get("prompt","")).strip(); dest=os.path.abspath(os.path.expanduser(str(payload.get("destination","")).strip()))
            if not prompt or not dest: raise ValueError("Task and destination are required.")
            os.makedirs(dest,exist_ok=True)
            run_id=_dt.datetime.now().strftime("%Y%m%d-%H%M%S")+"-"+uuid.uuid4().hex[:8]
            task=os.path.join(dest,".qonqrete-chat-task-"+run_id+".md")
            with open(task,"w",encoding="utf-8") as f: f.write("# Chat task\n\n"+prompt+"\n")
            env=os.environ.copy()
            if self.server.provider: env["QQ_PROVIDER"]=self.server.provider
            cmd=[sys.executable,"-m","qq","run",task,dest]
            if self.server.config_path: cmd += ["--config", self.server.config_path]
            if self.server.web_port is not None: cmd += ["--web-port",str(self.server.web_port),"--web-open-browser"]
            with self.server.lock: self.server.runs[run_id]={"running":True,"state":"starting","task":task,"destination":dest}
            threading.Thread(target=self.server._run, args=(run_id,cmd,task), daemon=True).start()
            self._send(202,json.dumps({"run_id":run_id}),"application/json")
        except Exception as e:
            self._send(400,json.dumps({"error":str(e)}),"application/json")

def serve_chat(host="127.0.0.1",port=1337,open_browser=True,provider=None,config_path=None,web_port=None):
    repo=os.environ.get("QQ_SRC") or os.getcwd()
    class Server(ThreadingHTTPServer):
        allow_reuse_address=True
    srv=Server((host,port),_Handler); srv.repo_root=os.path.abspath(repo); srv.root=os.path.abspath(repo)
    srv.provider=provider; srv.config_path=config_path; srv.web_port=web_port; srv.runs={}; srv.lock=threading.RLock()
    def _run(run_id,cmd,task):
        try:
            p=subprocess.run(cmd,cwd=srv.repo_root,env=os.environ.copy() if not provider else {**os.environ,"QQ_PROVIDER":provider})
            state="done" if p.returncode==0 else "failed"
        except Exception as e: state="failed"
        finally:
            try: os.remove(task)
            except OSError: pass
            with srv.lock: srv.runs[run_id]={"running":False,"state":state}
    srv._run=_run
    url=f"http://{host}:{port}"
    print(f"QonQrete chat: {url}")
    if open_browser: webbrowser.open(url)
    try: srv.serve_forever()
    except KeyboardInterrupt: pass
    finally: srv.server_close()
    return 0
