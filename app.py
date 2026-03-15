#!/usr/bin/env python3
import os,json,time,re,gc,logging,subprocess,threading
from pathlib import Path
from datetime import datetime
from flask import Flask,request,jsonify
import requests
app=Flask(__name__)
BD=Path("/tmp/yt");AD=BD/"a";ID=BD/"i";VD=BD/"v";TD=BD/"t"
for d in[AD,ID,VD,TD]:d.mkdir(parents=True,exist_ok=True)
logging.basicConfig(level=logging.INFO,format='%(asctime)s [%(levelname)s] %(message)s')
L=logging.getLogger(__name__)
OK=os.getenv("OPENAI_API_KEY","");PK=os.getenv("PEXELS_API_KEY","")
TT=os.getenv("TELEGRAM_BOT_TOKEN","");TC=os.getenv("TELEGRAM_CHAT_ID","")
PS={"running":False,"last_run":None,"last_result":None}

def notify(m):
    L.info(f"[N] {m}")
    if TT and TC:
        try:requests.post(f"https://api.telegram.org/bot{TT}/sendMessage",json={"chat_id":TC,"text":m,"parse_mode":"HTML"},timeout=10)
        except Exception as e:L.warning(f"TG fail:{e}")

def clean(d):
    for f in Path(d).glob("*"):
        if f.is_file():f.unlink(missing_ok=True)
    gc.collect()

def adur(p):
    r=subprocess.run(["ffprobe","-v","quiet","-show_entries","format=duration","-of","csv=p=0",str(p)],capture_output=True,text=True)
    try:return float(r.stdout.strip())
    except:return 60.0

def tts(nar,sid):
    L.info("TTS start")
    c=re.sub(r'\[IMAGE:.*?\]','',nar).strip() or "test"
    ss=[s.strip() for s in re.split(r'(?<=[.!?])\s+',c) if s.strip()]
    cks,cu=[],""
    for s in ss:
        if len(cu)+len(s)+1>3500:
            if cu:cks.append(cu.strip())
            cu=s
        else:cu+=" "+s if cu else s
    if cu:cks.append(cu.strip())
    if not cks:cks=[c[:3500]]
    L.info(f"TTS:{len(cks)} chunks")
    sl=AD/f"{sid}_sl.mp3"
    subprocess.run(["ffmpeg","-y","-f","lavfi","-i","anullsrc=r=24000:cl=mono","-t","0.3","-q:a","9",str(sl)],capture_output=True,timeout=10)
    cf=AD/f"{sid}_l.txt";hd={"Authorization":f"Bearer {OK}","Content-Type":"application/json"}
    with open(cf,'w') as f:
        for i,ch in enumerate(cks):
            cp=AD/f"{sid}_c{i}.mp3"
            try:
                r=requests.post("https://api.openai.com/v1/audio/speech",headers=hd,json={"model":"tts-1","input":ch,"voice":"onyx","speed":0.92,"response_format":"mp3"},timeout=120)
                r.raise_for_status();cp.write_bytes(r.content)
                f.write(f"file '{cp}'\n")
                if i<len(cks)-1:f.write(f"file '{sl}'\n")
                L.info(f"  c{i+1}/{len(cks)} ok")
            except Exception as e:L.error(f"  c{i+1} fail:{e}")
            time.sleep(0.3)
    raw=AD/f"{sid}_r.mp3"
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(cf),"-c","copy",str(raw)],capture_output=True,timeout=60)
    fn=AD/f"{sid}_f.mp3"
    subprocess.run(["ffmpeg","-y","-i",str(raw),"-af","loudnorm=I=-16:TP=-1.5:LRA=11","-ar","24000","-ac","1",str(fn)],capture_output=True,timeout=60)
    for f in AD.glob(f"{sid}_c*.mp3"):f.unlink(missing_ok=True)
    for f in[sl,cf,raw]:Path(f).unlink(missing_ok=True)
    gc.collect();L.info(f"TTS done:{fn}");return fn

def imgs(qs,sid):
    L.info(f"Imgs:{len(qs)}q")
    d=ID/sid;d.mkdir(exist_ok=True);dl=[]
    for i,q in enumerate(qs[:10]):
        try:
            r=requests.get("https://api.pexels.com/v1/search",headers={"Authorization":PK},params={"query":q,"per_page":1,"orientation":"landscape","size":"medium"},timeout=10)
            r.raise_for_status();ph=r.json().get("photos",[])
            if ph:
                ir=requests.get(ph[0]["src"]["large"],timeout=20)
                rp=d/f"r{i}.jpg";rp.write_bytes(ir.content)
                rs=d/f"i{i:03d}.jpg"
                subprocess.run(["ffmpeg","-y","-i",str(rp),"-vf","scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720","-q:v","3",str(rs)],capture_output=True,timeout=15)
                rp.unlink(missing_ok=True);dl.append(str(rs));L.info(f"  i{i+1}:{q[:15]} ok")
        except Exception as e:L.warning(f"  i{i+1} fail:{e}")
        time.sleep(0.2)
    while len(dl)<3:
        fb=d/f"fb{len(dl)}.jpg"
        subprocess.run(["ffmpeg","-y","-f","lavfi","-i","color=c=0x1a1a2e:s=1280x720:d=1","-frames:v","1","-q:v","3",str(fb)],capture_output=True,timeout=10)
        dl.append(str(fb))
    gc.collect();L.info(f"Imgs done:{len(dl)}");return dl

def thumb(txt,bg,sid):
    o=TD/f"{sid}_t.jpg"
    if bg and os.path.exists(bg):
        subprocess.run(["ffmpeg","-y","-i",bg,"-vf","scale=1280:720,colorbalance=bs=-0.3:bm=-0.3:bh=-0.3","-frames:v","1","-q:v","2",str(o)],capture_output=True,timeout=15)
    else:
        subprocess.run(["ffmpeg","-y","-f","lavfi","-i","color=c=0x1a1a2e:s=1280x720:d=1","-frames:v","1","-q:v","2",str(o)],capture_output=True,timeout=10)
    L.info(f"Thumb:{o}");return o

def tc(s):
    h=int(s//3600);m=int((s%3600)//60);se=int(s%60);ms=int((s%1)*1000)
    return f"{h:02d}:{m:02d}:{se:02d},{ms:03d}"

def video(im,aud,nar,sid):
    L.info("Vid start")
    dur=adur(str(aud));cd=max(dur/len(im),3.0)
    zp={"zi":"zoompan=z='min(zoom+0.002,1.2)':d={}:s=1280x720:fps=24","zo":"zoompan=z='if(eq(on,1),1.2,max(zoom-0.002,1))':d={}:s=1280x720:fps=24"}
    cf=VD/f"{sid}_l.txt";cc=0
    with open(cf,'w') as f:
        for i,img in enumerate(im):
            a=min(cd,dur-(i*cd))
            if a<=0:break
            cl=VD/f"{sid}_c{i}.mp4";ef=zp["zo" if i%2 else "zi"].format(int(a*24))
            subprocess.run(["ffmpeg","-y","-loop","1","-i",img,"-vf",ef,"-t",str(a),"-c:v","libx264","-preset","ultrafast","-crf","28","-pix_fmt","yuv420p","-r","24","-threads","1",str(cl)],capture_output=True,timeout=120)
            if cl.exists() and cl.stat().st_size>0:
                f.write(f"file '{cl}'\n");cc+=1;L.info(f"  cl{i+1}/{len(im)} ok")
            gc.collect()
    if cc==0:raise Exception("no clips")
    rv=VD/f"{sid}_r.mp4"
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(cf),"-c:v","libx264","-preset","ultrafast","-crf","28","-pix_fmt","yuv420p",str(rv)],capture_output=True,timeout=120)
    for f in VD.glob(f"{sid}_c*.mp4"):f.unlink(missing_ok=True)
    gc.collect()
    bgm=AD/f"{sid}_bg.mp3"
    subprocess.run(["ffmpeg","-y","-f","lavfi","-i",f"sine=f=180:r=24000:d={dur},tremolo=f=0.3:d=0.5,lowpass=f=250,volume=0.02","-t",str(dur),"-ar","24000","-ac","1",str(bgm)],capture_output=True,timeout=30)
    mx=AD/f"{sid}_mx.mp3"
    subprocess.run(["ffmpeg","-y","-i",str(aud),"-i",str(bgm),"-filter_complex","[1]volume=0.06[bg];[0][bg]amix=inputs=2:duration=first","-ar","24000","-ac","1",str(mx)],capture_output=True,timeout=60)
    bgm.unlink(missing_ok=True)
    fn=VD/f"{sid}_f.mp4"
    subprocess.run(["ffmpeg","-y","-i",str(rv),"-i",str(mx),"-c:v","libx264","-preset","ultrafast","-crf","28","-c:a","aac","-b:a","128k","-ar","24000","-shortest","-movflags","+faststart","-threads","1",str(fn)],capture_output=True,timeout=180)
    for f in[rv,mx,cf]:Path(f).unlink(missing_ok=True)
    gc.collect()
    sz=fn.stat().st_size/(1024*1024) if fn.exists() else 0
    L.info(f"Vid done:{fn} ({sz:.1f}MB)");return fn

def pipeline(sj):
    sid=datetime.now().strftime("%Y%m%d_%H%M%S")
    for d in[AD,ID,VD,TD]:clean(d)
    notify("ğŸ¬ <b>Start</b>")
    try:
        ti=sj.get("title","");na=sj.get("narration","");tt=sj.get("thumbnail_text",ti)
        iq=sj.get("image_queries",["Korea","Seoul"])
        notify(f"ğŸ“ {ti}")
        au=tts(na,sid);notify("ğŸ™ï¸ TTS done")
        im2=imgs(iq,sid);notify(f"ğŸ–¼ï¸ {len(im2)} imgs")
        th=thumb(tt,im2[0] if im2 else "",sid);notify("ğŸ¨ thumb")
        vd=video(im2,au,na,sid)
        sz=vd.stat().st_size/(1024*1024) if vd.exists() else 0
        notify(f"â€ñˆù½¹”„ğ½ˆùq¹íÑ¥õq¹íÍèè¸Å™õ5ˆ¤(€€€€€€€É•ÑÕÉ¸ì‰ÍÑ…ÑÕÌˆè‰ÍÕ•ÍÌˆ°‰Ñ¥Ñ±”ˆéÑ¤°‰Ù¥‘•¼ˆéÍÑÈ¡Ù¤°‰Í¥é•}µˆˆéÉ½Õ¹¡Íè°Ä¥ô(€€€•á•ÁĞá•ÁÑ¥½¸…Ì”è(€€€€€€€0¹•ÉÉ½È¡˜‰ÉÈéí•ôˆ±•á}¥¹™¼õQÉÕ”¤í¹½Ñ¥™ä¡˜‹Šv0íÍÑÈ¡”¥lèÈÀÁuôˆ¤(€€€€€€€É•ÑÕÉ¸ì‰ÍÑ…ÑÕÌˆè‰•ÉÉ½Èˆ°‰•ÉÉ½ÈˆéÍÑÈ¡”¥ô()…ÁÀ¹É½ÕÑ” ˆ¼ˆ¤)‘•˜¡½µ” ¤éÉ•ÑÕÉ¸©Í½¹¥™ä¡ì‰Í•ÉÙ¥”ˆè‰åĞµ…ÕÑ¼µØÌˆ°‰ÉÕ¹¹¥¹œˆéAMl‰ÉÕ¹¹¥¹œ‰uô¤)…ÁÀ¹É½ÕÑ” ˆ½¡•…±Ñ ˆ¤)‘•˜¡•…±Ñ  ¤éÉ•ÑÕÉ¸©Í½¹¥™ä¡ì‰ÍÑ…ÑÕÌˆè‰½¬ˆ°‰ÑÌˆé‘…Ñ•Ñ¥µ”¹¹½Ü ¤¹¥Í½™½Éµ…Ğ ¥ô¤)…ÁÀ¹É½ÕÑ” ˆ½ÑÉ¥•Èˆ±µ•Ñ¡½‘Ìõl‰A=MP‰t¤)‘•˜ÑÉ¥•È ¤è(€€€¥˜AMl‰ÉÕ¹¹¥¹œ‰téÉ•ÑÕÉ¸©Í½¹¥™ä¡ì‰ÍÑ…ÑÕÌˆè‰‰ÕÍä‰ô¤°ĞÈä(€€€õÉ•ÅÕ•ÍĞ¹©Í½¸½ÈíôíÌõ¹•Ğ ‰ÍÉ¥ÁĞˆ±¤(€€€Ñ¡É•…‘¥¹œ¹Q¡É•…¡Ñ…É•Ğõ}È±…ÉÌô¡Ì°¤¤¹ÍÑ…ÉĞ ¤(€€€É•ÑÕÉ¸©Í½¹¥™ä¡ì‰ÍÑ…ÑÕÌˆè‰ÍÑ…ÉÑ•ˆ°‰ÑÌˆé‘…Ñ•Ñ¥µ”¹¹½Ü ¤¹¥Í½™½Éµ…Ğ ¥ô¤)…ÁÀ¹É½ÕÑ” ˆ½ÍÑ…ÑÕÌˆ¤)‘•˜ÍÑ…ÑÕÌ ¤éÉ•ÑÕÉ¸©Í½¹¥™ä¡AL¤)‘•˜}È¡Ì¤è(€€€AMl‰ÉÕ¹¹¥¹œ‰tõQÉÕ”íAMl‰±…ÍÑ}ÉÕ¸‰tõ‘…Ñ•Ñ¥µ”¹¹½Ü ¤¹¥Í½™½Éµ…Ğ ¤(€€€ÑÉäéAMl‰±…ÍÑ}É•ÍÕ±Ğ‰tõÁ¥Á•±¥¹”¡Ì¤(€€€•á•ÁĞá•ÁÑ¥½¸…Ì”éAMl‰±…ÍÑ}É•ÍÕ±Ğ‰tõì‰ÍÑ…ÑÕÌˆè‰•ÉÉ½Èˆ°‰•ÉÉ½ÈˆéÍÑÈ¡”¥ô(€€€™¥¹…±±äéAMl‰ÉÕ¹¹¥¹œ‰tõ…±Í”()¥˜}}¹…µ•}|ôô‰}}µ…¥¹}|ˆè(€€€Àõ¥¹Ğ¡½Ì¹•Ñ•¹Ø ‰A=IPˆ°ÄÀÀÀÀ¤¤í0¹¥¹™¼¡˜‹Â~:°ØÌéíÁôˆ¤(€€€…ÁÀ¹ÉÕ¸¡¡½ÍĞôˆÀ¸À¸À¸Àˆ±Á½ÉĞõÀ¤(