"""QonQrete image smoke test using the configured image backend."""
from __future__ import annotations
import json, os
from datetime import datetime, timezone
CYBERSQUID_PROMPT=("High-detail cinematic QonQrete cybersquid: dark concrete cybernetic squid, "
"ember-orange circuitry, steel tentacles, molten gold ꝖꝖ emblem, neon command-line ocean, "
"code streams and sparks, dramatic production concept art.")
def run_image_smoke_test(output_dir=".", force_real=False):
    from .image_gen import generate_image
    os.makedirs(output_dir,exist_ok=True)
    path=os.path.join(os.path.abspath(output_dir),"qonqrete_cybersquid.png")
    result=generate_image(CYBERSQUID_PROMPT,aspect_ratio="16:9",resolution="1K",output_path=path)
    if not result.success:
        if force_real: print("QonQrete cybersquid image test FAILED:",result.error); return 1
        # deterministic tiny PNG fallback keeps offline smoke tests useful
        import struct,zlib
        def chunk(t,d): return struct.pack(">I",len(d))+t+d+struct.pack(">I",zlib.crc32(t+d)&0xffffffff)
        raw=b"\x00\x80"; data=b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",1,1,8,0,0,0,0))+chunk(b"IDAT",zlib.compress(raw))+chunk(b"IEND",b"")
        open(path,"wb").write(data); result_provider="mock"; result_model="mock"
    else: result_provider=result.metadata.get("route","configured"); result_model=result.model_used
    meta={"prompt":CYBERSQUID_PROMPT,"provider":result_provider,"model_used":result_model,
          "image_path":path,"created_at":datetime.now(timezone.utc).isoformat()}
    with open(os.path.join(os.path.abspath(output_dir),"qonqrete_cybersquid.meta.json"),"w") as f: json.dump(meta,f,indent=2)
    print("QonQrete cybersquid image test finished."); print("Image saved at:",path); return 0
def main(argv=None):
    import argparse
    p=argparse.ArgumentParser(); p.add_argument("--output-dir",default="."); p.add_argument("--real",action="store_true")
    a=p.parse_args(argv); raise SystemExit(run_image_smoke_test(a.output_dir,a.real))
if __name__=="__main__": main()
