#!/usr/bin/env python3
import os,json,time,re,gc,logging,subprocess,threading,requests
from pathlib import Path
from datetime import datetime
from flask import Flask,request,jsonify
app=Flask(__name__)
B=Path("/tmp/yt");AD=B/"au";ID=B/"im";VD=B/"vd";TD=B/"th"
for d in[AD,ID,VD,TD]:d.mkdir(parents=1,exist_ok=1)
logging.basicConfig(level=logging.INFO,format='%(asctime)s [%(levelname)s] %(message)s')
L=logging.getLogger(__name__)
OK=os.getenv("OPENAI_API_KEY","");PK=os.getenv("PEXELS_API_KEY","")
TT=os.getenv("TELEGRAM_BOT_TOKEN","");TC=os.getenv("TELEGRAM_CHAT_ID","")
PS={"running":False,"lr":None,"res":None}
def ntf(m):
 L.info(f"[N] {m}")
 if TT and TC:
  try:requests.post(f"https://api.telegram.org/bot{TT}/sendMessage",json={"chat_id":TC,"text":m,"parse_mode":"HTML"},timeout=10)
  except Exception as e:L.warning(f"TG fail:{e}")
def cld(d):
 for f in Path(d).glob("*"):
  if f.is_file():f.unlink(missing_ok=1)
 gc.collect()
def gad(p):
 r=subprocess.run(["ffprobe","-v","quiet","-show_entries","format=duration","-of","csv=p=0",str(p)],capture_output=1,text=1)
 try:return float(r.stdout.strip())
 except:return 60.0
def tts(nar,sid):
 L.info("TTS start")
 cl=re.sub(r'\[IMAGE:.*?\]','',nar).strip() or "test"
 ss=[s.strip() for s in re.split(r'(?<=[.!?])\s+',cl) if s.strip()]
 chs,cu=[],""
 for s in ss:
  if len(cu)+len(s)+1>3500:
   if cu:chs.append(cu.strip())
   cu=s
  else:cu+=" "+s if cu else s
 if cu:chs.append(cu.strip())
 if not chs:chs=[cl[:3500]]
 sil=AD/f"{sid}_sil.mp3"
 subprocess.run(["ffmpeg","-y","-f","lavfi","-i","anullsrc=r=24000:cl=mono","-t","0.3","-q:a","9",str(sil)],capture_output=1,timeout=10)
 cf=AD/f"{sid}_lst.txt"
 hd={"Authorization":f"Bearer {OK}","Content-Type":"application/json"}
 with open(cf,'w') as f:
  for i,ch in enumerate(chs):
   cp=AD/f"{sid}_c{i}.mp3"
   try:
    r=requests.post("https://api.openai.com/v1/audio/speech",headers=hd,json={"model":"tts-1","input":ch,"voice":"onyx","speed":0.92,"response_format":"mp3"},timeout=120)
    r.raise_for_status();cp.write_bytes(r.content)
    f.write(f"file '{cp}'\n")
    if i<len(chs)-1:f.write(f"file '{sil}'\n")
    L.info(f" c{i+1}/{len(chs)} ok")
   except Exception as e:L.error(f" c{i+1} fail:{e}")
   time.sleep(0.3)
 raw=AD/f"{sid}_r.mp3"
 subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(cf),"-c","copy",str(raw)],capture_output=1,timeout=60)
 fn=AD/f"{sid}_f.mp3"
 subprocess.run(["ffmpeg","-y","-i",str(raw),"-af","loudnorm=I=-16:TP=-1.5:LRA=11","-ar","24000","-ac","1",str(fn)],capture_output=1,timeout=60)
 for f in AD.glob(f"{sid}_c*.mp3"):f.unlink(missing_ok=1)
 for f in[sil,cf,raw]:Path(f).unlink(missing_ok=1)
 gc.collect();return fn
def imgs(qs,sid):
 d=ID/sid;d.mkdir(exist_ok=1);dl=[]
 for i,q in enumerate(qs[:8]):
  try:
   r=requests.get("https://api.pexels.com/v1/search",headers={"Authorization":PK},params={"query":q,"per_page":1,"orientation":"landscape","size":"medium"},timeout=10)
   r.raise_for_status();ph=r.json().get("photos",[])
   if ph:
    ir=requests.get(ph[0]["src"]["large"],timeout=20)
    rp=d/f"r{i}.jpg";rp.write_bytes(ir.content)
    rs=d/f"i{i:03d}.jpg"
    subprocess.run(["ffmpeg","-y","-i",str(rp),"-vf","scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720","-q:v","3",str(rs)],capture_output=1,timeout=15)
    rp.unlink(missing_ok=1);dl.append(str(rs))
  except:pass
  time.sleep(0.2)
 while len(dl)<3:
  fb=d/f"fb{len(dl)}.jpg"
  subprocess.run(["ffmpeg","-y","-f","lavfi","-i","color=c=0x1a1a2e:s=1280x720:d=1","-frames:v","1","-q:v","3",str(fb)],capture_output=1,timeout=10)
  dl.append(str(fb))
 gc.collect();return dl
def thb(bg,sid):
 o=TD/f"{sid}_t.jpg"
 if bg and os.path.exists(bg):
  subprocess.run(["ffmpeg","-y","-i",bg,"-vf","scale=1280:720","-frames:v","1","-q:v","2",str(o)],capture_output=1,timeout=15)
 else:
  subprocess.run(["ffmpeg","-y","-f","lavfi","-i","color=c=0x1a1a2e:s=1280x720:d=1","-frames:v","1","-q:v","2",str(o)],capture_output=1,timeout=10)
 return o
def vid(im,au,sid):
 dur=gad(str(au));cd=max(dur/len(im),3.0)
 zp={"zi":"zoompan=z='min(zoom+0.002,1.2)':d={}:s=1280x720:fps=24","zo":"zoompan=z='if(eq(on,1),1.2,max(zoom-0.002,1))':d={}:s=1280x720:fps=24"}
 cf=VD/f"{sid}_l.txt";cc=0
 with open(cf,'w') as f:
  for i,img in enumerate(im):
   a=min(cd,dur-(i*cd))
   if a<=0:break
   cl=VD/f"{sid}_c{i}.mp4";ef=zp["zo" if i%2 else "zi"].format(int(a*24))
   subprocess.run(["ffmpeg","-y","-loop","1","-i",img,"-vf",ef,"-t",str(a),"-c:v","libx264","-preset","ultrafast","-crf","28","-pix_fmt","yuv420p","-r","24","-threads","1",str(cl)],capture_output=1,timeout=120)
   if cl.exists() and cl.stat().st_size>0:
    f.write(f"file '{cl}'\n");cc+=1
   gc.collect()
 if cc==0:raise Exception("no clips")
 rv=VD/f"{sid}_r.mp4"
 subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(cf),"-c:v","libx264","-preset","ultrafast","-crf","28","-pix_fmt","yuv420p",str(rv)],capture_output=1,timeout=120)
 for f in VD.glob(f"{sid}_c*.mp4"):f.unlink(missing_ok=1)
 gc.collect()
 bgm=AD/f"{sid}_bg.mp3"
 subprocess.run(["ffmpeg","-y","-f","lavfi","-i",f"sine=f=180:r=24000:d={dur},tremolo=f=0.3:d=0.5,lowpass=f=250,volume=0.02","-t",str(dur),"-ar","24000","-ac","1",str(bgm)],capture_output=1,timeout=30)
 mx=AD/f"{sid}_mx.mp3"
 subprocess.run(["ffmpeg","-y","-i",str(au),"-i",str(bgm),"-filter_complex","[1]volume=0.06[bg];[0][bg]amix=inputs=2:duration=first","-ar","24000","-ac","1",str(mx)],capture_output=1,timeout=60)
 bgm.unlink(missing_ok=1)
 fn=VD/f"{sid}_f.mp4"
 subprocess.run(["ffmpeg","-y","-i",str(rv),"-i",str(mx),"-c:v","libx264","-preset","ultrafast","-crf","28","-c:a","aac","-b:a","128k","-ar","24000","-shortest","-movflags","+faststart","-threads","1",str(fn)],capture_output=1,timeout=180)
 for f in[rv,mx,cf]:Path(f).unlink(missing_ok=1)
 gc.collect()
 sz=fn.stat().st_size/(1024*1024) if fn.exists() else 0
 L.info(f"Vid done:{fn} ({sz:.1f}MB)");return fn
# === YouTube OAuth ===
CID=os.getenv("YT_CLIENT_ID","")
CSC=os.getenv("YT_CLIENT_SECRET","")
RDU=os.getenv("YT_REDIRECT_URI","https://yt-auto-server.onrender.com/oauth/callback")
TKF=Path("/tmp/yt_token.json")
def yt_creds():
 if not TKF.exists():return None
 tk=json.loads(TKF.read_text())
 if tk.get("expires_at",0)<time.time():
  r=requests.post("https://oauth2.googleapis.com/token",data={"client_id":CID,"client_secret":CSC,"refresh_token":tk["refresh_token"],"grant_type":"refresh_token"})
  if r.status_code==200:
   d=r.json();tk["access_token"]=d["access_token"];tk["expires_at"]=time.time()+d.get("expires_in",3600)-60
   TKF.write_text(json.dumps(tk))
 return tk
def yt_upload(vp,ti,desc,tags):
 tk=yt_creds()
 if not tk:L.warning("No YT token");return None
 meta={"snippet":{"title":ti[:100],"description":desc[:5000],"tags":tags[:30],"categoryId":"22","defaultLanguage":"ko"},"status":{"privacyStatus":"public","selfDeclaredMadeForKids":False}}
 r=requests.post("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",headers={"Authorization":f"Bearer {tk['access_token']}","Content-Type":"application/json"},json=meta,timeout=30)
 if r.status_code!=200:L.error(f"YT init:{r.status_code}");return None
 uurl=r.headers.get("Location")
 if not uurl:return None
 with open(vp,'rb') as f:
  r2=requests.put(uurl,headers={"Content-Type":"video/mp4"},data=f,timeout=600)
 if r2.status_code in(200,201):
  vid=r2.json().get("id","");L.info(f"YT ok:{vid}");return vid
 L.error(f"YT fail:{r2.status_code}");return None
def pipe(sj):
 sid=datetime.now().strftime("%Y%m%d_%H%M%S")
 for d in[AD,ID,VD,TD]:cld(d)
 ntf("🎬 <b>Start</b>")
 try:
  ti=sj.get("title","");na=sj.get("narration","")
  tt=sj.get("thumbnail_text",ti);iq=sj.get("image_queries",["Korea","Seoul"])
  ntf(f"📝 {ti}")
  au=tts(na,sid);ntf("🎙 TTS done")
  im=imgs(iq,sid);ntf(f"🖼 {len(im)} imgs")
  th=thb(im[0] if im else "",sid);ntf("🎨 thumb")
  vd=vid(im,au,sid)
  sz=vd.stat().st_size/(1024*1024) if vd.exists() else 0
  ntf(f"✅ <b>Done!</b>\n{ti}\n{sz:.1f}MB")
  yid=yt_upload(str(vd),ti,sj.get("description",""),sj.get("tags",[]))
  if yid:ntf(f"📺 <b>YouTube!</b>^nhttps://youtu.be/{yid}")
  else:ntf("⚠️ YT upload skipped (no OAuth)")
  return {"status":"success","title":ti,"video":str(vd),"size_mb":round(sz,1),"youtube_id":yid}
 except Exception as e:
  L.error(f"Err:{e}",exc_info=1);ntf(f"❌ <b>Error</b>\n{str(e)[:200]}")
  return {"status":"error","error":str(e)}
@app.route("/")
def home():return jsonify({"service":"yt-auto v3","status":"running","busy":PS["running"]})
@app.route("/health")
def health():return jsonify({"status":"ok","ts":datetime.now().isoformat()})
@app.route("/trigger",methods=["POST"])
def trigger():
 if PS["running"]:return jsonify({"status":"busy"}),429
 d=request.json or {};s=d.get("script",d)
 threading.Thread(target=_r,args=(s,)).start()
 return jsonify({"status":"started","ts":datetime.now().isoformat()})
@app.route("/status")
def status():return jsonify(PS)
@app.route("/oauth/start")
def oauth_start():
 u=f"https://accounts.google.com/o/oauth2/v2/auth?client_id={CID}&redirect_uri={RDU}&response_type=code&scope=https://www.googleapis.com/auth/youtube.upload&access_type=offline&prompt=consent"
 return f'<h2>YouTube OAuth</h2><a href="{u}" style="font-size:24px">Google Login</a>'
@app.route("/oauth/callback")
def oauth_cb():
 code=request.args.get("code")
 if not code:return "no code",400
 r=requests.post("https://oauth2.googleapis.com/token",data={"code":code,"client_id":CID,"client_secret":CSC,"redirect_uri":RDU,"grant_type":"authorization_code"})
 if r.status_code!=200:return f"error:{r.text}",400
 d=r.json();d["expires_at"]=time.time()+d.get("expires_in",3600)-60
 TKF.write_text(json.dumps(d));ntf("🔑 YouTube OAuth done!")
 return "<h2>Success! YouTube connected.</h2>"
@app.route("/oauth/status")
def oauth_st():
 if TKF.exists():return jsonify({"status":"connected"})
 return jsonify({"status":"not_connected"})
def _r(s):
 PS["running"]=True;PS["lr"]=datetime.now().isoformat()
 try:PS["res"]=pipe(s)
 except Exception as e:PS["res"]={"status":"error","error":str(e)}
 finally:PS["running"]=False
if __name__=="__main__":
 p=int(os.getenv("PORT",10000));L.info(f"🎬 v3:{p}")
 app.run(host="0.0.0.0",port=p)
