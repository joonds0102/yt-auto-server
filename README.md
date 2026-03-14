# 🎬 국뽕유튜브 자동화 서버

Make.com → 이 서버 → TTS/영상편집/업로드 자동화

## 배포 방법 (Render.com)

1. 이 repo를 GitHub에 push
2. Render.com에서 New > Web Service
3. GitHub repo 연결
4. Environment: Docker
5. 환경변수 설정:
   - `OPENAI_API_KEY`
   - `PEXELS_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `SPREADSHEET_ID`

## API 엔드포인트

- `GET /` - 서버 상태
- `GET /health` - 헬스체크
- `POST /trigger` - 파이프라인 실행
- `GET /status` - 실행 상태 확인
