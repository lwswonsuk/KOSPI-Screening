# 투자자 코멘트 → 종목 프로필 카드 교체 설계

날짜: 2026-08-14

## 배경

현재 스크리닝 웹사이트는 종목명 클릭 시 Peter Lynch / Warren Buffett / Bill Ackman 세 투자자 관점의
AI 코멘트를 탭으로 보여준다([StockCommentaryDialog.tsx](../../../web/app/StockCommentaryDialog.tsx),
[commentary.py](../../../screening/commentary.py)). 사용자가 이 코멘트 품질이 만족스럽지 않다고 판단,
투자자 관점 평가 대신 종목의 사업 내용/섹터/대표 상품·브랜드/주요 경쟁사 정보로 대체하기로 했다.
모달을 열어 정보를 보여주는 상호작용 형식(종목명 클릭 → 모달)은 그대로 유지한다.

데이터 파이프라인에는 실제 업종 분류 데이터가 없다(`sector` 컬럼은 현재 `"미분류"` 고정,
[data_pipeline.py:373](../../../screening/data_pipeline.py)). 따라서 이번에도 기존과 동일하게
Claude Haiku 4.5를 사용해 생성한다.

## A. 데이터 생성 (`screening/profile.py`, `commentary.py` 대체)

- `screening/commentary.py`를 `screening/profile.py`로 교체한다. `INVESTORS`/`PERSONAS`/3인칭 페르소나
  로직은 전부 삭제.
- 종목당 1회만 Claude Haiku 4.5(`claude-haiku-4-5`)를 호출한다(상위 50종목 → 총 50회, 기존 150회 대비
  호출 수 감소).
- 시스템 프롬프트: "당신은 한국 주식시장에 정통한 애널리스트입니다. 종목명을 보고 알고 있는 사실에
  근거해 간결하게 설명합니다. 모르는 내용은 추측하지 말고 일반적인 수준에서만 설명하세요."
- 사용자 프롬프트: 종목명(및 참고용으로 PER/PBR 등 기존 지표를 계속 포함해도 무방)을 주고, 아래 4개
  필드를 **JSON으로만** 응답하도록 요청한다:
  ```json
  {"business": "사업 내용 2~3문장", "sector": "섹터/업종 (예: 반도체, 화장품, 2차전지 소재 등)",
   "products": "대표 상품 또는 브랜드", "competitors": "주요 경쟁사 (2~4곳)"}
  ```
- `generate_profile(row, client=None) -> dict | None`: 응답 텍스트를 `json.loads`로 파싱. 파싱 실패,
  4개 키 중 하나라도 없음, 네트워크/API 오류 — 모두 예외로 처리해 삼키고 `None` 반환(개별 필드 단위가
  아니라 종목 전체 단위로 성공/실패). 기존 `generate_commentary`의 "예외를 삼키고 None" 패턴을 그대로 계승.
- `generate_all_profiles(records) -> dict[str, dict | None]`: `ANTHROPIC_API_KEY` 없으면 전체 스킵하고
  모든 종목에 `None` (기존 `generate_all_commentary`와 동일 패턴). 클라이언트 초기화 실패 시에도 동일하게
  전체 `None` 처리.

## B. 저장 형식

- `results.json`의 각 상위 50종목 레코드에서 `commentary` 필드를 `profile` 필드로 교체:
  ```json
  "profile": {
    "business": "...", "sector": "...", "products": "...", "competitors": "..."
  }
  ```
- 생성 실패 시 `profile: null` (필드 단위 null이 아니라 레코드 전체가 null).
- `screening/ws_alpha.py`의 `run_real()`: 기존 코멘트 생성 호출부(`generate_all_commentary` 관련 코드,
  draft 저장 로직 포함)를 `generate_all_profiles` 기반으로 교체. 파이프라인 중단 시에도 유효한
  `results.json`을 남기기 위해 먼저 `profile: null`로 초안을 저장한 뒤 생성 결과로 갱신하는 기존 패턴
  (commit 43d622a) 유지.

## C. 프런트 UI

- `web/app/StockCommentaryDialog.tsx` → `web/app/StockProfileDialog.tsx`로 교체.
  - `Commentary` 타입 → `StockProfile` 타입: `{ business: string; sector: string; products: string; competitors: string }`.
  - 투자자 탭 버튼(3개) 제거. 모달 안에 탭 없이 하나의 카드(`rounded-2xl rounded-tl-none bg-muted p-4`
    스타일 유지)에 4개 소제목을 순서대로 표시:
    1. 사업 내용
    2. 섹터
    3. 대표 상품·브랜드
    4. 주요 경쟁사
  - `profile`이 `null`이거나 `undefined`이면 카드 전체에 "아직 분석이 준비되지 않았습니다" 문구 표시
    (기존 문구 재사용). 구버전 `results.json`(profile 필드 자체가 없는 경우)에도 동일하게 대응.
- `web/app/ScreeningTable.tsx`: `commentary` → `profile`로 필드명/타입/props 변경, import 대상 변경.
- `web/app/page.tsx`: `ResultRow`의 `commentary?: {...}` 타입을 `profile?: StockProfile | null`로 교체.

## D. 테스트

- `screening/tests/test_commentary.py` → `screening/tests/test_profile.py`로 교체.
  - 프롬프트 조립 함수(순수 함수)에 종목명이 포함되는지 테스트.
  - JSON 파싱 성공 시 4개 키가 모두 채워진 dict를 반환하는지 테스트.
  - JSON 파싱 실패(형식이 깨진 응답) 시 `None`을 반환하는지 테스트.
  - API 예외 발생 시 `None` 반환 테스트.
  - `ANTHROPIC_API_KEY` 없을 때 전체 `None` 처리 테스트.
- 프런트: `npm run build` 통과 확인, `profile`이 없는/`null`인 더미 데이터로 모달이 깨지지 않는지 로컬 확인.

## 영향받는 파일

- `screening/commentary.py` → `screening/profile.py` (교체)
- `screening/tests/test_commentary.py` → `screening/tests/test_profile.py` (교체)
- `screening/ws_alpha.py` (코멘트 생성 호출부를 프로필 생성 호출부로 교체)
- `web/app/StockCommentaryDialog.tsx` → `web/app/StockProfileDialog.tsx` (교체)
- `web/app/ScreeningTable.tsx` (필드명/타입/props 변경)
- `web/app/page.tsx` (`ResultRow` 타입 변경)

## 비용 참고

- 기존: 50종목 × 3명 = 150회/일. 신규: 50종목 × 1회 = 50회/일 (약 1/3로 감소, 비용도 비례 감소 예상).
