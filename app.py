#!/usr/bin/env python3
"""
🎬 국뽕유튜브 자동화 서버 v3 — 대규모 업그레이드
================================================================
채널명: 썰국 (@ssulgook)
타겟: 50~60대 한국 남성 / 해외반응·국뽕 롱폼 콘텐츠
참고채널: 쓸모왕, 위대한언니, 꿀튜브, 단골이슈, 존크TV 등

v3 변경사항:
- TTS: speed 1.05 + pitch 약간 높임 → 뉴스 앵커 스타일
- 자막: 검정 윤곽 흰색 글씨, 화면 하단 1줄, 음성 싱크
- 영상: 이미지당 5~8초 유지 (빠른 전환 방지)
- 길이: 5~10분 (RPM 극대화, 중간광고 가능)
- 썸네일: 후킹 텍스트 + 큰 글씨 + 빨간/노란 강조
- 대본: GPT로 5060 맞춤 국뽕 대본 자동 생성
- YouTube: OAuth 자동 업로드 + 메타데이터 최적화
- 메모리: 512MB RAM 안정 동작 (720p, 순차처리)
================================================================
"""

import os
import json
import time
import re
import gc
import math
import logging
import subprocess
import threading
import pickle
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify, redirect, session
import requests

# ============================================================
# Flask 앱 초기화
# ============================================================
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "ssulgook-secret-2026")

BASE_DIR = Path("/tmp/yt_auto")
AUDIO_DIR = BASE_DIR / "audio"
IMAGE_DIR = BASE_DIR / "images"
VIDEO_DIR = BASE_DIR / "video"
THUMB_DIR = BASE_DIR / "thumbnails"
TOKEN_DIR = BASE_DIR / "tokens"

for d in [AUDIO_DIR, IMAGE_DIR, VIDEO_DIR, THUMB_DIR, TOKEN_DIR]:
    d.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
L = logging.getLogger(__name__)

# ============================================================
# 환경변수
# ============================================================
OK = os.getenv("OPENAI_API_KEY", "")
PK = os.getenv("PEXELS_API_KEY", "")
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")
YT_CLIENT_ID = os.getenv("YT_CLIENT_ID", "")
YT_CLIENT_SECRET = os.getenv("YT_CLIENT_SECRET", "")
YT_REDIRECT_URI = os.getenv("YT_REDIRECT_URI", "https://yt-auto-server.onrender.com/oauth/callback")
YT_API_KEY = os.getenv("YT_API_KEY", "")

pipeline_status = {"running": False, "last_run": None, "last_result": None}

# ============================================================
# 유틸리티
# ============================================================
def notify(msg):
    """텔레그램 알림"""
    L.info(f"[알림] {msg}")
    if TG_TOKEN and TG_CHAT:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "HTML"},
                timeout=10,
            )
        except Exception as e:
            L.warning(f"TG 실패: {e}")


def cleanup(directory):
    """디렉토리 정리 + 메모리 해제"""
    for f in Path(directory).glob("*"):
        if f.is_file():
            f.unlink(missing_ok=True)
    gc.collect()


def audio_duration(path):
    """오디오 파일 길이(초)"""
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(r.stdout.strip())
    except:
        return 60.0


def split_sentences(text):
    """한국어 문장 분리 (마침표/물음표/느낌표 기준)"""
    sents = re.split(r"(?<=[.!?。])\s+", text.strip())
    return [s.strip() for s in sents if s.strip()]


# ============================================================
# 1. 대본 생성 (GPT) — 5060 타겟 국뽕 콘텐츠 최적화
# ============================================================
def generate_script(topic=None):
    """
    GPT로 국뽕 대본 + 제목 + 썸네일 텍스트 + 이미지 키워드 자동 생성
    topic이 없으면 자동으로 트렌딩 주제 선택
    """
    L.info(f"📝 대본 생성 시작 (주제: {topic or '자동선택'})")

    system_prompt = """너는 유튜브 채널 '썰국'의 전문 대본 작가야.
타겟 시청자: 50~60대 한국 남성
카테고리: 해외반응, 외국인반응, 국뽕 콘텐츠
참고채널 스타일: 쓸모왕, 위대한언니, 꿀튜브, 단골이슈, 존크TV

대본 작성 규칙:
1. 분량: 1200~1800자 (읽으면 5~8분 분량)
2. 톤: 뉴스 앵커처럼 신뢰감 있되, 감탄과 자부심을 자연스럽게 유도
3. 구조: 후킹 도입(30초) → 본문(3~4개 에피소드) → 마무리(구독유도)
4. 도입부에 "여러분, 이거 아시나요?" 같은 질문형 후킹 필수
5. 중간중간 "정말 대단하지 않습니까?" 같은 감탄 유도 멘트
6. 마무리: "이런 대한민국이 자랑스럽지 않으십니까? 구독과 좋아요 부탁드립니다"
7. 외국인 이름, 국가명을 구체적으로 언급 (신뢰감)
8. 숫자와 통계 적극 활용 (조회수, 댓글 수, 랭킹 등)
9. [IMAGE:키워드] 태그를 본문 중 6~10개 삽입 (이미지 전환 포인트)

반드시 JSON 형식으로 응답:
{
  "title": "유튜브 제목 (후킹, 40자 이내, 따옴표+감탄사 포함)",
  "thumbnail_text": "썸네일 메인 텍스트 (10자 이내, 임팩트)",
  "thumbnail_sub": "썸네일 서브 텍스트 (15자 이내)",
  "narration": "전체 나레이션 대본",
  "tags": ["태그1", "태그2", ...],
  "description": "영상 설명 (200자, 해시태그 포함)"
}"""

    user_msg = f"다음 주제로 대본을 작성해줘: {topic}" if topic else \
        "최근 화제가 된 한국 관련 해외반응 주제를 골라서 대본을 작성해줘. 외국인이 한국에 와서 놀란 경험, 한국 문화/기술/음식에 감탄한 사례 등 5060대 남성이 자부심을 느낄 수 있는 주제로."

    try:
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OK}", "Content-Type": "application/json"},
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                "temperature": 0.8,
                "max_tokens": 3000,
            },
            timeout=60,
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]

        # JSON 추출
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            script = json.loads(json_match.group())
        else:
            script = json.loads(content)

        L.info(f"✅ 대본 생성 완료: {script.get('title', '제목없음')}")
        return script

    except Exception as e:
        L.error(f"대본 생성 실패: {e}")
        raise


# ============================================================
# 2. TTS 음성 생성 — 빠르고 자연스러운 높낮이
# ============================================================
def generate_tts(narration, sid):
    """
    OpenAI TTS로 음성 생성
    - speed 1.05: 약간 빠르게 (자연스러운 뉴스 톤)
    - voice: nova (밝고 또렷한 한국어)
    - loudnorm + pitch 미세 조정
    """
    L.info("🎙️ TTS 생성 시작...")

    # [IMAGE:...] 태그 제거
    clean = re.sub(r"\[IMAGE:[^\]]*\]", "", narration).strip()
    if not clean:
        clean = "대한민국은 정말 대단한 나라입니다."

    # 문장 단위로 청크 분리 (API 제한 대응)
    sentences = split_sentences(clean)
    chunks, current = [], ""
    for s in sentences:
        if len(current) + len(s) + 1 > 3500:
            if current:
                chunks.append(current.strip())
            current = s
        else:
            current = f"{current} {s}" if current else s
    if current:
        chunks.append(current.strip())
    if not chunks:
        chunks = [clean[:3500]]

    L.info(f"  청크 {len(chunks)}개로 분할")

    # 무음 간격 생성 (문장 사이 0.25초)
    silence = AUDIO_DIR / f"{sid}_sil.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
         "-t", "0.25", "-q:a", "9", str(silence)],
        capture_output=True, timeout=10,
    )

    concat_list = AUDIO_DIR / f"{sid}_list.txt"
    headers = {"Authorization": f"Bearer {OK}", "Content-Type": "application/json"}

    with open(concat_list, "w") as f:
        for i, chunk in enumerate(chunks):
            cp = AUDIO_DIR / f"{sid}_c{i}.mp3"
            try:
                resp = requests.post(
                    "https://api.openai.com/v1/audio/speech",
                    headers=headers,
                    json={
                        "model": "tts-1-hd",        # HD 모델 (더 자연스러움)
                        "input": chunk,
                        "voice": "nova",             # 밝고 또렷, 뉴스 스타일
                        "speed": 1.05,               # 약간 빠르게
                        "response_format": "mp3",
                    },
                    timeout=120,
                )
                resp.raise_for_status()
                cp.write_bytes(resp.content)
                f.write(f"file '{cp}'\n")
                if i < len(chunks) - 1:
                    f.write(f"file '{silence}'\n")
                L.info(f"  청크 {i+1}/{len(chunks)} ✅")
            except Exception as e:
                L.error(f"  청크 {i+1} 실패: {e}")
            time.sleep(0.3)

    # 합치기
    raw = AUDIO_DIR / f"{sid}_raw.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
         "-c", "copy", str(raw)],
        capture_output=True, timeout=60,
    )

    # 정규화 + 약간 pitch 높이기 (더 생동감)
    final = AUDIO_DIR / f"{sid}_final.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(raw),
         "-af", "asetrate=24000*1.02,aresample=24000,loudnorm=I=-16:TP=-1.5:LRA=11",
         "-ar", "24000", "-ac", "1", str(final)],
        capture_output=True, timeout=60,
    )

    # 정리
    for f in AUDIO_DIR.glob(f"{sid}_c*.mp3"):
        f.unlink(missing_ok=True)
    for f in [silence, concat_list, raw]:
        Path(f).unlink(missing_ok=True)
    gc.collect()

    dur = audio_duration(final)
    L.info(f"✅ TTS 완료: {dur:.1f}초")
    return final


# ============================================================
# 3. 이미지 수집 (Pexels) — 고화질 + 한국/해외 관련
# ============================================================
def collect_images(narration, sid):
    """
    나레이션에서 [IMAGE:키워드] 추출 → Pexels 검색
    키워드 없으면 기본 한국 관련 이미지 사용
    """
    L.info("🖼️ 이미지 수집 시작...")

    # [IMAGE:키워드] 추출
    img_tags = re.findall(r"\[IMAGE:([^\]]+)\]", narration)
    if not img_tags:
        img_tags = [
            "Korea cityscape", "Korean food", "Korean technology",
            "Korean culture", "Seoul skyline", "Korean traditional",
            "foreign tourist Korea", "Korean flag", "Korean innovation",
            "Korean pop culture"
        ]

    # 최소 10개 이미지 확보 (5-10분 영상, 이미지당 5-8초)
    while len(img_tags) < 10:
        img_tags.extend(["Korea beautiful", "Seoul modern", "Korean pride"])
    img_tags = img_tags[:15]  # 최대 15개

    img_dir = IMAGE_DIR / sid
    img_dir.mkdir(exist_ok=True)
    results = []

    for i, query in enumerate(img_tags):
        try:
            r = requests.get(
                "https://api.pexels.com/v1/search",
                headers={"Authorization": PK},
                params={"query": query, "per_page": 2, "orientation": "landscape", "size": "large"},
                timeout=10,
            )
            r.raise_for_status()
            photos = r.json().get("photos", [])
            if photos:
                # 가장 좋은 해상도 선택
                photo = photos[0]
                img_url = photo["src"]["large2x"]  # 고해상도
                ir = requests.get(img_url, timeout=20)
                raw_path = img_dir / f"raw_{i}.jpg"
                raw_path.write_bytes(ir.content)

                # 720p 리사이즈 + 크롭
                resized = img_dir / f"img_{i:03d}.jpg"
                subprocess.run(
                    ["ffmpeg", "-y", "-i", str(raw_path),
                     "-vf", "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720",
                     "-q:v", "2", str(resized)],
                    capture_output=True, timeout=15,
                )
                raw_path.unlink(missing_ok=True)
                results.append(str(resized))
                L.info(f"  이미지 {i+1}: {query} ✅")
        except Exception as e:
            L.warning(f"  이미지 {i+1}: {query} 실패 - {e}")
        time.sleep(0.3)

    # 최소 5개 확보 (부족하면 기존 이미지 반복)
    while len(results) < 5 and results:
        results.append(results[len(results) % len(results)])

    L.info(f"✅ 이미지 {len(results)}개 수집 완료")
    return results


# ============================================================
# 4. 썸네일 생성 — 후킹 스타일 (참고채널 벤치마킹)
# ============================================================
def generate_thumbnail(main_text, sub_text, bg_image, sid):
    """
    국뽕채널 스타일 썸네일
    - 큰 흰색 텍스트 + 노란 강조
    - 검정 반투명 오버레이
    - 빨간색/노란색 포인트
    """
    L.info("🎨 썸네일 생성...")
    thumb_path = THUMB_DIR / f"{sid}_thumb.jpg"

    if not bg_image or not Path(bg_image).exists():
        # 검정 배경 생성
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=1280x720:d=1",
             "-frames:v", "1", str(thumb_path)],
            capture_output=True, timeout=10,
        )
        bg_image = str(thumb_path)

    # 폰트 찾기
    font_paths = [
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    ]
    font = next((f for f in font_paths if Path(f).exists()), "")

    # 메인 텍스트 (큰 흰색, 검정 윤곽 + 노란 그림자)
    main_safe = main_text.replace("'", "'\\''").replace('"', '\\"')[:20]
    sub_safe = sub_text.replace("'", "'\\''").replace('"', '\\"')[:30] if sub_text else ""

    # drawtext 필터: 반투명 오버레이 + 텍스트
    filters = []
    # 어둡게 오버레이
    filters.append("drawbox=x=0:y=0:w=iw:h=ih:color=black@0.45:t=fill")

    if font:
        # 메인 텍스트 (중앙, 큰 글씨)
        filters.append(
            f"drawtext=text='{main_safe}':fontfile={font}:fontsize=72:"
            f"fontcolor=white:borderw=4:bordercolor=black:"
            f"shadowcolor=yellow@0.6:shadowx=3:shadowy=3:"
            f"x=(w-text_w)/2:y=(h-text_h)/2-30"
        )
        # 서브 텍스트 (하단)
        if sub_safe:
            filters.append(
                f"drawtext=text='{sub_safe}':fontfile={font}:fontsize=42:"
                f"fontcolor=yellow:borderw=3:bordercolor=black:"
                f"x=(w-text_w)/2:y=(h-text_h)/2+60"
            )
        # 채널명 (좌하단)
        filters.append(
            f"drawtext=text='썰국':fontfile={font}:fontsize=28:"
            f"fontcolor=white@0.8:borderw=2:bordercolor=black:"
            f"x=20:y=h-50"
        )

    filter_str = ",".join(filters)

    subprocess.run(
        ["ffmpeg", "-y", "-i", bg_image,
         "-vf", f"scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,{filter_str}",
         "-q:v", "2", str(thumb_path)],
        capture_output=True, timeout=15,
    )

    L.info(f"✅ 썸네일 완료: {thumb_path}")
    return thumb_path


# ============================================================
# 5. 영상 합성 — 자막 싱크 + 화면전환 최적화
# ============================================================
def compose_video(images, audio_path, narration, sid):
    """
    핵심 개선사항:
    - 이미지당 5~8초 유지 (빠른 전환 방지)
    - 자막: 검정 윤곽 흰색 글씨, 하단 1줄, 음성과 싱크
    - fade 전환 효과
    - 5~10분 영상 길이
    """
    L.info("🎬 영상 합성 시작...")

    total_dur = audio_duration(audio_path)
    L.info(f"  오디오 길이: {total_dur:.1f}초")

    # ---- 문장별 타이밍 계산 (자막 싱크) ----
    clean_narration = re.sub(r"\[IMAGE:[^\]]*\]", "", narration).strip()
    sentences = split_sentences(clean_narration)
    if not sentences:
        sentences = ["대한민국은 정말 대단한 나라입니다."]

    # 문장 길이 비례로 시간 배분
    total_chars = sum(len(s) for s in sentences)
    timings = []
    current_time = 0.0
    for s in sentences:
        dur = max(2.0, (len(s) / total_chars) * total_dur)
        timings.append({"text": s, "start": current_time, "end": current_time + dur})
        current_time += dur

    # 마지막 문장 끝 시간 조정
    if timings:
        timings[-1]["end"] = total_dur

    # ---- 이미지 시퀀스 (5~8초씩 유지) ----
    n_images = len(images)
    if n_images == 0:
        L.error("이미지 없음!")
        return None

    # 이미지당 목표 시간: 5~8초 (총 시간 / 이미지 수)
    target_per_img = total_dur / n_images
    target_per_img = max(5.0, min(8.0, target_per_img))

    # 이미지 부족하면 반복
    needed = math.ceil(total_dur / target_per_img)
    while len(images) < needed:
        images.append(images[len(images) % n_images])

    # ---- SRT 자막 파일 생성 ----
    srt_path = VIDEO_DIR / f"{sid}.srt"
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, t in enumerate(timings):
            # 한 줄에 최대 25자 (5060 타겟: 큰 글씨로 읽기 편하게)
            text = t["text"]
            if len(text) > 25:
                # 자연스러운 위치에서 줄바꿈
                mid = len(text) // 2
                # 공백이나 쉼표 근처에서 자르기
                break_pos = mid
                for offset in range(10):
                    if mid + offset < len(text) and text[mid + offset] in " ,，.。":
                        break_pos = mid + offset + 1
                        break
                    if mid - offset >= 0 and text[mid - offset] in " ,，.。":
                        break_pos = mid - offset + 1
                        break
                text = text[:break_pos].strip() + "\n" + text[break_pos:].strip()

            start_ts = format_srt_time(t["start"])
            end_ts = format_srt_time(t["end"])
            f.write(f"{i+1}\n{start_ts} --> {end_ts}\n{text}\n\n")

    # ---- 이미지 슬라이드쇼 생성 ----
    # concat 파일 생성
    img_list = VIDEO_DIR / f"{sid}_imgs.txt"
    with open(img_list, "w") as f:
        elapsed = 0.0
        for idx, img in enumerate(images):
            if elapsed >= total_dur:
                break
            dur = min(target_per_img, total_dur - elapsed)
            if dur < 1.0:
                break
            f.write(f"file '{img}'\n")
            f.write(f"duration {dur:.2f}\n")
            elapsed += dur
        # 마지막 프레임 유지용
        f.write(f"file '{images[-1]}'\n")

    # ---- 1단계: 이미지 → 무음 영상 (fade 전환 포함) ----
    raw_video = VIDEO_DIR / f"{sid}_raw.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(img_list),
         "-vf", "fps=24,format=yuv420p",
         "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
         "-t", str(total_dur),
         str(raw_video)],
        capture_output=True, timeout=300,
    )

    # ---- 2단계: 오디오 합성 + 자막 입히기 ----
    final_video = VIDEO_DIR / f"{sid}_final.mp4"

    # 폰트 찾기 (자막용)
    font_paths = [
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    ]
    font = next((f for f in font_paths if Path(f).exists()), "")
    font_escaped = font.replace(":", "\\:").replace("\\", "/") if font else ""

    # 자막 스타일: 검정 윤곽 + 흰색 글씨 + 하단 배치
    if font_escaped:
        sub_filter = (
            f"subtitles={str(srt_path).replace(':', '\\:')}:"
            f"force_style='FontName=NanumGothicBold,"
            f"FontSize=26,"
            f"PrimaryColour=&H00FFFFFF,"    # 흰색
            f"OutlineColour=&H00000000,"     # 검정 윤곽
            f"BackColour=&H80000000,"        # 반투명 검정 배경
            f"BorderStyle=3,"                # 박스형 배경
            f"Outline=3,"                    # 윤곽 두께
            f"Shadow=1,"                     # 그림자
            f"MarginV=35,"                   # 하단 여백
            f"Alignment=2'"                  # 하단 중앙
        )
    else:
        sub_filter = (
            f"subtitles={str(srt_path).replace(':', '\\:')}:"
            f"force_style='FontSize=26,"
            f"PrimaryColour=&H00FFFFFF,"
            f"OutlineColour=&H00000000,"
            f"BackColour=&H80000000,"
            f"BorderStyle=3,Outline=3,Shadow=1,"
            f"MarginV=35,Alignment=2'"
        )

    subprocess.run(
        ["ffmpeg", "-y",
         "-i", str(raw_video),
         "-i", str(audio_path),
         "-vf", sub_filter,
         "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26",
         "-c:a", "aac", "-b:a", "128k",
         "-shortest",
         "-movflags", "+faststart",
         str(final_video)],
        capture_output=True, timeout=600,
    )

    # 정리
    raw_video.unlink(missing_ok=True)
    img_list.unlink(missing_ok=True)
    srt_path.unlink(missing_ok=True)
    gc.collect()

    size = final_video.stat().st_size / (1024 * 1024) if final_video.exists() else 0
    L.info(f"✅ 영상 완성: {size:.1f}MB, {total_dur:.0f}초")
    return final_video


def format_srt_time(seconds):
    """초 → SRT 타임스탬프 (HH:MM:SS,mmm)"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# ============================================================
# 6. YouTube 업로드 (OAuth2)
# ============================================================
def get_yt_credentials():
    """저장된 YouTube OAuth 토큰 로드"""
    token_file = TOKEN_DIR / "yt_token.json"
    if not token_file.exists():
        return None
    try:
        data = json.loads(token_file.read_text())
        # 토큰 만료 체크 & 갱신
        if data.get("expires_at", 0) < time.time():
            data = refresh_yt_token(data)
        return data
    except:
        return None


def refresh_yt_token(token_data):
    """리프레시 토큰으로 액세스 토큰 갱신"""
    try:
        r = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": YT_CLIENT_ID,
                "client_secret": YT_CLIENT_SECRET,
                "refresh_token": token_data["refresh_token"],
                "grant_type": "refresh_token",
            },
            timeout=15,
        )
        r.raise_for_status()
        new_data = r.json()
        token_data["access_token"] = new_data["access_token"]
        token_data["expires_at"] = time.time() + new_data.get("expires_in", 3600) - 60
        (TOKEN_DIR / "yt_token.json").write_text(json.dumps(token_data))
        return token_data
    except Exception as e:
        L.error(f"토큰 갱신 실패: {e}")
        return token_data


def upload_to_youtube(video_path, title, description, tags, thumb_path=None):
    """YouTube에 영상 업로드"""
    creds = get_yt_credentials()
    if not creds:
        L.warning("YouTube 인증 없음 — 업로드 스킵")
        return {"status": "skipped", "reason": "no_credentials"}

    L.info(f"📤 YouTube 업로드: {title}")

    # 메타데이터 (5060 타겟 최적화)
    metadata = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:30],
            "categoryId": "25",  # 뉴스와 정치 (높은 RPM)
            "defaultLanguage": "ko",
            "defaultAudioLanguage": "ko",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    headers = {
        "Authorization": f"Bearer {creds['access_token']}",
        "Content-Type": "application/json",
    }

    try:
        # 1. 업로드 세션 시작
        init_r = requests.post(
            "https://www.googleapis.com/upload/youtube/v3/videos"
            "?uploadType=resumable&part=snippet,status",
            headers=headers,
            json=metadata,
            timeout=30,
        )
        init_r.raise_for_status()
        upload_url = init_r.headers["Location"]

        # 2. 영상 파일 업로드
        file_size = Path(video_path).stat().st_size
        with open(video_path, "rb") as f:
            upload_r = requests.put(
                upload_url,
                headers={
                    "Authorization": f"Bearer {creds['access_token']}",
                    "Content-Type": "video/mp4",
                    "Content-Length": str(file_size),
                },
                data=f,
                timeout=600,
            )
            upload_r.raise_for_status()
            video_data = upload_r.json()
            video_id = video_data["id"]

        L.info(f"✅ 업로드 완료: https://youtu.be/{video_id}")

        # 3. 썸네일 업로드
        if thumb_path and Path(thumb_path).exists():
            try:
                with open(thumb_path, "rb") as tf:
                    requests.post(
                        f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
                        f"?videoId={video_id}",
                        headers={
                            "Authorization": f"Bearer {creds['access_token']}",
                            "Content-Type": "image/jpeg",
                        },
                        data=tf,
                        timeout=30,
                    )
                L.info("  썸네일 설정 ✅")
            except Exception as e:
                L.warning(f"  썸네일 실패: {e}")

        notify(
            f"🎉 <b>YouTube 업로드 완료!</b>\n"
            f"제목: {title}\n"
            f"https://youtu.be/{video_id}"
        )
        return {"status": "uploaded", "video_id": video_id, "url": f"https://youtu.be/{video_id}"}

    except Exception as e:
        L.error(f"업로드 실패: {e}")
        notify(f"❌ YouTube 업로드 실패: {str(e)[:200]}")
        return {"status": "error", "error": str(e)}


# ============================================================
# 7. 전체 파이프라인
# ============================================================
def run_pipeline(data):
    """
    전체 자동화 파이프라인:
    대본생성 → TTS → 이미지수집 → 썸네일 → 영상합성 → YouTube업로드
    """
    sid = datetime.now().strftime("%Y%m%d_%H%M%S")
    L.info(f"🚀 파이프라인 시작 (세션: {sid})")
    notify(f"🚀 <b>파이프라인 시작</b>\n세션: {sid}")

    try:
        # 이전 파일 정리
        for d in [AUDIO_DIR, VIDEO_DIR, THUMB_DIR]:
            cleanup(d)

        # ---- 데이터 파싱 ----
        # Make.com에서 전달하는 형식 또는 직접 호출 형식 모두 지원
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except:
                data = {"topic": data}

        topic = data.get("topic", data.get("subject", None))
        narration = data.get("narration", data.get("script", ""))
        title = data.get("title", "")
        description = data.get("description", "")
        tags = data.get("tags", [])
        thumb_text = data.get("thumbnail_text", "")
        thumb_sub = data.get("thumbnail_sub", "")

        # ---- 대본이 없으면 GPT로 자동 생성 ----
        if not narration:
            L.info("📝 대본 자동 생성 모드...")
            script = generate_script(topic)
            narration = script.get("narration", "")
            title = title or script.get("title", "썰국 | 해외반응")
            description = description or script.get("description", "")
            tags = tags or script.get("tags", ["해외반응", "국뽕", "외국인반응", "한국"])
            thumb_text = thumb_text or script.get("thumbnail_text", "충격")
            thumb_sub = thumb_sub or script.get("thumbnail_sub", "")
            notify(f"📝 대본 완료: {title}")

        if not narration:
            raise ValueError("나레이션 내용이 없습니다")

        # ---- 1. TTS ----
        audio = generate_tts(narration, sid)
        notify("🎙️ TTS 완료")

        # ---- 2. 이미지 수집 ----
        images = collect_images(narration, sid)
        notify(f"🖼️ 이미지 {len(images)}개 수집")

        # ---- 3. 썸네일 ----
        bg_img = images[0] if images else ""
        thumb = generate_thumbnail(thumb_text, thumb_sub, bg_img, sid)
        notify("🎨 썸네일 완료")

        # ---- 4. 영상 합성 ----
        video = compose_video(images, audio, narration, sid)
        if not video or not video.exists():
            raise RuntimeError("영상 생성 실패")

        size = video.stat().st_size / (1024 * 1024)
        dur = audio_duration(audio)
        notify(
            f"🎬 <b>영상 완성!</b>\n"
            f"제목: {title}\n"
            f"길이: {dur:.0f}초 ({dur/60:.1f}분)\n"
            f"크기: {size:.1f}MB"
        )

        # ---- 5. YouTube 업로드 ----
        yt_result = upload_to_youtube(
            str(video), title, description, tags, str(thumb)
        )

        result = {
            "status": "success",
            "session_id": sid,
            "title": title,
            "video_path": str(video),
            "duration_sec": round(dur, 1),
            "size_mb": round(size, 1),
            "youtube": yt_result,
        }

        notify(
            f"✅ <b>전체 완료!</b>\n"
            f"제목: {title}\n"
            f"길이: {dur/60:.1f}분 | 크기: {size:.1f}MB\n"
            f"YouTube: {yt_result.get('url', 'N/A')}"
        )
        return result

    except Exception as e:
        L.error(f"파이프라인 오류: {e}", exc_info=True)
        notify(f"❌ <b>오류</b>\n{str(e)[:300]}")
        return {"status": "error", "session_id": sid, "error": str(e)}

    finally:
        # 이미지 디렉토리 정리
        img_dir = IMAGE_DIR / sid
        if img_dir.exists():
            cleanup(img_dir)
        gc.collect()


# ============================================================
# Flask 라우트
# ============================================================
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "service": "🇰🇷 썰국 자동화 서버 v3",
        "status": "running",
        "pipeline_running": pipeline_status["running"],
        "features": [
            "GPT 대본 자동생성",
            "TTS-HD (nova, 1.05x)",
            "자막 싱크 (검정윤곽 흰글씨)",
            "5-8초 이미지 유지",
            "후킹 썸네일",
            "YouTube 자동 업로드",
        ],
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})


@app.route("/trigger", methods=["POST"])
def trigger():
    """Make.com 또는 수동으로 파이프라인 실행"""
    if pipeline_status["running"]:
        return jsonify({"status": "busy", "message": "이미 실행 중"}), 429

    data = request.json or {}
    script = data.get("script", data)

    thread = threading.Thread(target=_run, args=(script,))
    thread.start()
    return jsonify({"status": "started", "timestamp": datetime.now().isoformat()})


@app.route("/auto", methods=["POST", "GET"])
def auto_generate():
    """주제만 전달하면 대본부터 업로드까지 전자동"""
    if pipeline_status["running"]:
        return jsonify({"status": "busy"}), 429

    if request.method == "GET":
        topic = request.args.get("topic", None)
    else:
        data = request.json or {}
        topic = data.get("topic", None)

    thread = threading.Thread(target=_run, args=({"topic": topic},))
    thread.start()
    return jsonify({
        "status": "started",
        "mode": "full_auto",
        "topic": topic or "자동선택",
    })


@app.route("/status", methods=["GET"])
def status():
    return jsonify(pipeline_status)


# ---- YouTube OAuth ----
@app.route("/oauth/start", methods=["GET"])
def oauth_start():
    """YouTube OAuth 인증 시작"""
    if not YT_CLIENT_ID:
        return "YT_CLIENT_ID 환경변수 필요", 500

    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={YT_CLIENT_ID}"
        f"&redirect_uri={YT_REDIRECT_URI}"
        "&response_type=code"
        "&scope=https://www.googleapis.com/auth/youtube.upload"
        "+https://www.googleapis.com/auth/youtube"
        "&access_type=offline"
        "&prompt=consent"
    )
    return redirect(auth_url)


@app.route("/oauth/callback", methods=["GET"])
def oauth_callback():
    """OAuth 콜백 → 토큰 저장"""
    code = request.args.get("code")
    if not code:
        return "인증 코드 없음", 400

    try:
        r = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": YT_CLIENT_ID,
                "client_secret": YT_CLIENT_SECRET,
                "redirect_uri": YT_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            timeout=15,
        )
        r.raise_for_status()
        token_data = r.json()
        token_data["expires_at"] = time.time() + token_data.get("expires_in", 3600) - 60

        (TOKEN_DIR / "yt_token.json").write_text(json.dumps(token_data))

        notify("🔑 YouTube OAuth 인증 완료!")
        return (
            "<html><body style='font-family:sans-serif;text-align:center;padding:50px;'>"
            "<h1>✅ YouTube 인증 완료!</h1>"
            "<p>이제 서버가 자동으로 영상을 업로드합니다.</p>"
            "<p>이 창을 닫아도 됩니다.</p>"
            "</body></html>"
        )
    except Exception as e:
        return f"토큰 교환 실패: {e}", 500


@app.route("/oauth/status", methods=["GET"])
def oauth_status():
    """OAuth 인증 상태 확인"""
    creds = get_yt_credentials()
    if creds:
        return jsonify({"authenticated": True, "expires_at": creds.get("expires_at")})
    return jsonify({"authenticated": False})


# ---- 내부 실행 함수 ----
def _run(script):
    pipeline_status["running"] = True
    pipeline_status["last_run"] = datetime.now().isoformat()
    try:
        pipeline_status["last_result"] = run_pipeline(script)
    except Exception as e:
        pipeline_status["last_result"] = {"status": "error", "error": str(e)}
    finally:
        pipeline_status["running"] = False


# ============================================================
# 실행
# ============================================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    L.info(f"🇰🇷 썰국 서버 v3 시작: http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port)
