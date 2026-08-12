# 주식 스크리닝 웹사이트

Stock Note 투자원칙 기반 코스피 스크리닝. GitHub Actions가 매일 자동으로
스크리닝을 돌려 `web/data/results.json`을 갱신하면, Vercel이 그 커밋을
감지해 자동으로 재배포한다. 별도 DB 없음.

웹사이트에서 할 수 있는 것:
- **스크리닝 업데이트 실행** 버튼 → GitHub Actions를 즉시 실행시켜 재계산
  (완료까지 2~10분, 완료되면 자동 재배포되어 반영됨)
- **최신 종가 새로고침** 버튼 → 그 자리에서 바로 최신 확정 종가를 다시 불러옴
  (KRX 데이터는 장마감 후 확정되는 일별 종가이며, 틱 단위 실시간 체결가는 아님)

## 구조

```
screening/          # 파이썬 스크리닝 엔진 (data_pipeline.py, ws_alpha.py)
web/                 # Next.js 웹사이트
  app/page.tsx           결과 표시 페이지 (빌드 시점 results.json을 읽음)
  app/ScreeningTable.tsx 정렬 가능한 표 + 최신 종가 새로고침
  app/UpdateControls.tsx 스크리닝 업데이트 버튼
  app/api/prices/        최신 종가 조회 API (서버에서 KRX 호출, 키 비노출)
  app/api/update-finance/ GitHub Actions 원격 실행 API
.github/workflows/   # 매일 자동 실행 스케줄 (workflow_dispatch로 수동/웹 실행도 가능)
```

## 최초 설정 (한 번만)

### 1. GitHub 저장소 만들기
이 폴더 전체를 새 GitHub 저장소에 push한다.

```bash
git init
git add .
git commit -m "init"
git branch -M main
git remote add origin <본인의 GitHub 저장소 URL>
git push -u origin main
```

### 2. GitHub Secrets 등록 (Actions가 쓰는 키)
저장소 페이지 → Settings → Secrets and variables → Actions → New repository secret

- `DART_API_KEY` : DART Open API 인증키
- `KRX_API_KEY` : KRX Open API 인증키

### 3. GitHub Personal Access Token 발급 (웹사이트가 Actions를 원격 실행시키기 위해 필요)
1. GitHub 우측 상단 프로필 → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate new token
2. Repository access: 이 저장소만 선택
3. Permissions → **Actions: Read and write** 로 설정
4. 생성된 토큰(ghp_로 시작하는 긴 문자열)을 복사해둔다 (다시 못 봄, 꼭 메모)

### 4. GitHub Actions 활성화 확인
저장소 페이지 → Actions 탭 → 워크플로우가 보이는지 확인. 처음엔 수동으로
한 번 실행해서 잘 도는지 확인 (Actions → 일일 스크리닝 → Run workflow).

### 5. Vercel 배포
1. https://vercel.com 가입 (GitHub 계정으로 로그인 추천)
2. "Add New… → Project" → 방금 만든 GitHub 저장소 선택
3. **Root Directory를 `web`으로 지정** (중요 — 안 하면 빌드 실패함)
4. Framework Preset은 Next.js가 자동 인식됨
5. **Environment Variables**에 아래 항목 추가 (Deploy 누르기 전에):
   - `KRX_API_KEY` : KRX Open API 인증키 (최신 종가 새로고침용)
   - `GH_PAT` : 3번에서 발급받은 GitHub 토큰
   - `GH_OWNER` : GitHub 사용자명
   - `GH_REPO` : 저장소 이름
6. Deploy 클릭

이후로는:
- GitHub Actions가 매일 `results.json`을 커밋할 때마다 Vercel이 자동 재배포
- 웹사이트의 "스크리닝 업데이트 실행" 버튼을 누르면 그 즉시 GitHub Actions가
  실행되고, 끝나면 자동으로 사이트가 갱신됨

## 로컬에서 테스트하기

```bash
cd web
npm install
npm run dev
```

http://localhost:3000 에서 확인. API 라우트(`/api/prices`, `/api/update-finance`)를
로컬에서 테스트하려면 `web/.env.local` 파일을 만들고 아래처럼 채워넣는다
(이 파일은 git에 올라가지 않음):

```
KRX_API_KEY=발급받은키
GH_PAT=발급받은토큰
GH_OWNER=본인깃헙아이디
GH_REPO=저장소이름
```

`results.json`을 직접 채워서 테스트하려면:

```bash
cd screening
pip install -r requirements.txt
python ws_alpha.py --run --date 20260807 --top 60 --export "" --export-json "../web/data/results.json"
```

