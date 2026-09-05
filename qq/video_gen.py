from __future__ import annotations
import os, shutil, subprocess, tempfile, textwrap, json
from dataclasses import dataclass

@dataclass
class VideoResult:
    success: bool
    output_path: str = ""
    method: str = ""
    error: str = ""

def _run(cmd,cwd=None):
    return subprocess.run(cmd,cwd=cwd,capture_output=True,text=True,timeout=600)

def _manim(prompt,out,w,h,fps,duration,script):
    if not shutil.which("manim"): return VideoResult(False,error="manim is not installed.")
    scene = textwrap.dedent(f'''
from manim import *
class QonQreteScene(Scene):
    def construct(self):
        title=Text({prompt!r}).scale(0.7)
        self.play(Write(title), run_time=1.2)
        self.play(title.animate.scale(1.25), run_time=1.0)
        self.play(Rotate(title, angle=2*PI), run_time={max(1,duration-2)})
        self.wait(0.5)
''') if not script else open(script,encoding="utf-8").read()
    with tempfile.TemporaryDirectory(prefix="qq-manim-") as td:
        src=os.path.join(td,"scene.py"); open(src,"w").write(scene)
        r=_run(["manim","-ql","--fps",str(fps),src,"QonQreteScene","-o",os.path.basename(out)],td)
        if r.returncode:return VideoResult(False,error=r.stderr[-2000:])
        found=next((os.path.join(dp,f) for dp,_,fs in os.walk(td) for f in fs if f.endswith(".mp4")),None)
        if not found:return VideoResult(False,error="Manim completed but no MP4 was produced.")
        os.makedirs(os.path.dirname(os.path.abspath(out)) or ".",exist_ok=True); shutil.copy2(found,out)
    return VideoResult(True,out,"manim")

def _remotion(prompt,out,w,h,fps,duration,script):
    if not shutil.which("npx"): return VideoResult(False,error="Node/npm (npx) is required for Remotion.")
    with tempfile.TemporaryDirectory(prefix="qq-remotion-") as td:
        pkg={"dependencies":{"@remotion/cli":"latest","remotion":"latest","react":"latest","react-dom":"latest"}}
        os.makedirs(td+"/src"); open(td+"/package.json","w").write(json.dumps(pkg))
        if script:
            src=open(script,encoding="utf-8").read()
        else:
            src = """import React from "react";
import {Composition, useCurrentFrame} from "remotion";
export const Scene=()=>{const f=useCurrentFrame(); return React.createElement("div",{style:{width:"100%",height:"100%",display:"flex",alignItems:"center",justifyContent:"center",fontSize:64,fontFamily:"sans-serif",background:"#111",color:"white",transform:"scale("+(1+Math.min(f/%d,1)*.2)+") rotate("+(f/%d*8)+"deg)"}},"%s");};
export const RemotionVideo=()=>React.createElement(Composition,{id:"QonQrete",component:Scene,durationInFrames:%d,fps:%d,width:%d,height:%d});
""" % (fps,fps,prompt.replace("\\","\\\\").replace('"','\\\"'),fps*duration,fps,w,h)
        open(td+"/src/index.jsx","w").write(src)
        open(td+"/src/index.js","w").write('import {registerRoot} from "remotion"; import {RemotionVideo} from "./index.jsx"; registerRoot(RemotionVideo);')
        r=_run(["npx","--yes","remotion","render","src/index.js","QonQrete","out.mp4"],td)
        if r.returncode:return VideoResult(False,error=r.stderr[-2000:])
        if not os.path.isfile(td+"/out.mp4"):return VideoResult(False,error="Remotion completed without out.mp4.")
        shutil.copy2(td+"/out.mp4",out)
    return VideoResult(True,out,"remotion")

def _p5(prompt,out,w,h,fps,duration,script):
    try: import playwright.sync_api as pw
    except ImportError: return VideoResult(False,error="p5 backend requires playwright and a browser.")
    if not shutil.which("ffmpeg"): return VideoResult(False,error="p5 backend requires ffmpeg.")
    with tempfile.TemporaryDirectory(prefix="qq-p5-") as td:
        js=open(script,encoding="utf-8").read() if script else f'''function setup(){{createCanvas({w},{h});}} function draw(){{background(10); fill(255); textAlign(CENTER,CENTER); textSize(48); text({prompt!r},width/2,height/2); translate(width/2,height/2); rotate(frameCount*0.03); noFill(); stroke(220); circle(0,0,220);}}'''
        html=f'''<html><body><script src="https://cdn.jsdelivr.net/npm/p5@1.11.1/lib/p5.min.js"></script><script>{js}</script></body></html>'''
        open(td+"/index.html","w").write(html)
        with pw.sync_playwright() as p:
            browser=p.chromium.launch(headless=True); page=browser.new_page(viewport={"width":w,"height":h})
            page.goto("file://"+td+"/index.html"); page.wait_for_timeout(100)
            for i in range(int(fps*duration)):
                page.evaluate("window.dispatchEvent(new Event('qqframe'))")
                page.screenshot(path=f"{td}/f{i:06d}.png")
            browser.close()
        r=_run(["ffmpeg","-y","-framerate",str(fps),"-i",td+"/f%06d.png","-pix_fmt","yuv420p",out])
        if r.returncode:return VideoResult(False,error=r.stderr[-2000:])
    return VideoResult(True,out,"p5")

def generate_video(method,prompt,output_path,script_path=None,width=1280,height=720,fps=30,duration=5):
    return {"manim":_manim,"remotion":_remotion,"p5":_p5}[method](prompt,output_path,width,height,fps,duration,script_path)
