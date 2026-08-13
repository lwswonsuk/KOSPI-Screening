# 투자자별 종목 분석 말풍선 기능 설계

날짜: 2026-08-13

## 배경

현재 스크리닝 웹사이트는 상위 50종목을 표(PER/PBR/ROE/부채비율/배당수익률/배당성향/종합점수)로만 보여준다.
사용자는 종목명을 클릭했을 때, Peter Lynch·Warren Buffett·Bill Ackman 세 투자자의 관점에서 그 종목을
어떻게 평가할지 짧은 텍스트로 보고 싶어한다. 이 텍스트는 AI(Claude Haiku 4.5)가 매일 스크리닝 파이프라인
실행 시 종목별 재무 지표를 근거로 생성하며, 사용자가 사이트에서 클릭할 때는 이미 생성된 텍스트를 보여주기만
한다(그 시점에 API를 호출하지 않음).

## A. 데이터 생성 (Python, GitHub Actions 파이프라인 내부)

- `screening/commentary.py` 신규 파일: `anthropic` Python SDK로 Claude Haiku 4.5(`claude-haiku-4-5`)를 호출하는
  함수 `generate_commentary(row: dict, investor: str) -> str | None`을 제공한다.
- `INVESTORS = ["peter_lynch", "warren_buffett", "bill_ackman"]` 3명 고정, 각각 짧은 페르소나 시스템 프롬프트를
  하드코딩(예: Peter Lynch — "성장주 발굴과 PEG 비율을 중시하는 관점", Warren Buffett — "안전마진과 우량 비즈니스의
  장기 보유 관점", Bill Ackman — "행동주의 투자자로서 명확한 촉매와 확신도 높은 소수 종목 집중 관점").
- `ws_alpha.py`가 top 50 종목을 확정한 직후(`export_json` 작성 전), 50종목 × 3명 = 150회 호출을 순차 실행한다.
  각 호출의 사용자 프롬프트에는 종목명, PER, PBR, ROE(3년평균), 부채비율, 시가배당수익률, 배당성향, 종합점수를
  숫자로 포함시키고, "이 투자자라면 이 종목을 3~4문장으로 어떻게 평가할지"를 요청한다.
- `max_tokens`는 400 내외로 제한(출력 200~300 토큰 목표), `output_config.effort`는 별도 지정하지 않음(기본값).
- 종목·투자자 조합 하나가 실패(네트워크 오류, rate limit, API 오류)해도 예외를 삼키고 그 조합만 `None`으로
  기록, 전체 파이프라인은 중단 없이 계속 진행한다(150회 중 일부 실패를 감수).
- `ANTHROPIC_API_KEY`가 환경변수에 없으면(로컬 테스트 등) 이 단계 전체를 건너뛰고 모든 `commentary`를
  `None`으로 채운다 — 로컬 개발/CI 초기 세팅 시 이 기능이 없어도 파이프라인이 죽지 않도록.

## B. 저장 형식

- `results.json`의 각 종목 레코드(그리고 `filtered_full.json`은 대상 아님 — 말풍선은 상위 50종목에만 생성,
  비용 절감을 위해 필터통과 전체 종목까지는 생성하지 않는다)에 `commentary` 필드를 추가한다:
  ```json
  "commentary": {
    "peter_lynch": "...",
    "warren_buffett": "...",
    "bill_ackman": "..."
  }
  ```
- 실패한 조합은 해당 키의 값이 `null`.
- `ws_alpha.py`의 `run_real()`에서 `top`(상위 50) 데이터프레임을 대상으로만 커멘터리를 생성하고,
  `records` 딕셔너리 빌드 시 `commentary` 필드를 함께 채워 넣는다.

## C. 프런트 UI

- `web/app/ScreeningTable.tsx`: 종목명 셀을 버튼처럼 클릭 가능하게 변경(밑줄 스타일). 클릭 시 해당 행의
  `commentary` 데이터를 `web/app/StockCommentaryDialog.tsx`(신규)에 전달해 모달을 연다.
- `StockCommentaryDialog.tsx`: shadcn `Dialog` 기반, 상단에 `Tabs`(Peter Lynch / Warren Buffett / Bill Ackman)
  3개, 각 탭 콘텐츠는 말풍선 스타일 카드(둥근 모서리, 배경색 구분)로 해당 투자자의 코멘트 텍스트를 표시.
- 특정 투자자의 코멘트가 `null`이면 그 탭에서 "아직 분석이 준비되지 않았습니다" 안내 문구를 표시(에러로
  처리하지 않음).
- `results.json`이 아직 `commentary` 필드 자체가 없는 구버전인 경우(다음 자동 갱신 전)에도 종목명 클릭 시
  모달은 열리되 3개 탭 모두 "아직 분석이 준비되지 않았습니다"로 표시되어야 한다(타입은 옵셔널로 정의).

## D. 시크릿 및 비용

- GitHub Secrets에 `ANTHROPIC_API_KEY` 신규 등록 필요(사용자가 직접 발급 및 등록, 코드로 자동화 불가).
- `.github/workflows/daily-screen.yml`의 스크리닝 실행 스텝에 `ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}`
  환경변수 추가.
- 예상 비용: Haiku 4.5 기준 1일 150회 호출, 월 약 $6~16 (호출당 입력 800~1500 토큰, 출력 150~400 토큰 가정).

## 영향받는 파일

- `screening/commentary.py`(신규)
- `screening/ws_alpha.py`(top 50 확정 후 커멘터리 생성 호출 추가, `records` 빌드 시 `commentary` 필드 포함)
- `.github/workflows/daily-screen.yml`(`ANTHROPIC_API_KEY` 환경변수 추가)
- `web/app/ScreeningTable.tsx`(종목명 클릭 가능하게 변경)
- `web/app/StockCommentaryDialog.tsx`(신규)
- `web/app/page.tsx`(`ResultsPayload`/`ResultRow` 타입에 `commentary` 옵셔널 필드 반영 필요 시)

## 테스트/검증 방침

- `screening/commentary.py`의 프롬프트 조립 로직(종목 데이터 → 프롬프트 문자열)은 순수 함수로 분리해
  단위 테스트 가능하게 만든다. 실제 API 호출 자체는 네트워크 의존이라 유닛 테스트에서 mock 처리.
- 실패 처리 로직(예외 → `None` 반환, 파이프라인 계속)에 대한 단위 테스트 추가.
- 프런트: `npm run build` 통과 확인, `commentary` 필드가 없는/부분적으로 `null`인 더미 데이터로 모달이
  깨지지 않는지 로컬에서 확인.
