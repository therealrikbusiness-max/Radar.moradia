"""Sondagem: verifica robots.txt e baixa amostras SOMENTE onde permitido."""
import json, pathlib, time, urllib.robotparser
from urllib.parse import urlparse
import requests

UA = "RadarMoradia/1.0 (+https://github.com/therealrikbusiness-max/Radar.moradia)"
out = pathlib.Path("probe_out"); out.mkdir(exist_ok=True)
summary = []
for i, line in enumerate(pathlib.Path("probe/urls.txt").read_text().split("\n")):
    if not line.strip():
        continue
    name, url = line.split("|", 1)
    base = "{0.scheme}://{0.netloc}".format(urlparse(url))
    rec = {"name": name, "url": url}
    try:
        r = requests.get(base + "/robots.txt", headers={"User-Agent": UA}, timeout=30)
        rec["robots_status"] = r.status_code
        pass
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        rec["allowed"] = rp.can_fetch(UA, url) if r.status_code == 200 else (r.status_code == 404)
    except Exception as e:
        rec["robots_error"] = repr(e); rec["allowed"] = False
    if rec.get("allowed"):
        time.sleep(3)
        try:
            p = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR"}, timeout=30)
            rec["page_status"] = p.status_code
            rec["final_url"] = p.url
            rec["len"] = len(p.text)
            (out / f"{i:02d}_{name}_page.html").write_text(p.text[:3000000])
        except Exception as e:
            rec["page_error"] = repr(e)
    summary.append(rec); print(rec, flush=True)
    time.sleep(2)
(out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
