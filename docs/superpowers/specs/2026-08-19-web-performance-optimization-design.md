# 웹앱 성능·번들·코드 품질 최적화 설계

날짜: 2026-08-19

## 목표

`web/` Next.js 15 App Router 애플리케이션의 초기 JavaScript 번들, 다운로드 경로,
클라이언트 컴포넌트 범위, 타입 안정성을 개선한다. 사용자에게 보이는 기능과 정적
배포 구조는 유지하며 `screening/` Python 파이프라인과 GitHub Actions 워크플로우는
변경하지 않는다.

## 기준선

`web/`에서 `npm run build`를 실행한 결과:

- `/` Route Size: 95 kB
- `/` First Load JS: 197 kB
- 공통 First Load JS: 102 kB
- 생성 CSS: 32,639 bytes
- `filtered_full.json`: 194,742 bytes, 545종목
- 동일 데이터를 압축 XLSX로 생성한 크기: 약 106,619 bytes

빌드는 통과하지만 저장소 바깥의 `C:\Users\lwswo\package-lock.json`을 workspace root로
오인해 `outputFileTracingRoot` 경고를 출력한다.

## 분석 결과 및 우선순위

### P0: Radix 루트 배럴 import 제거

현재 `radix-ui` 루트에서 `Dialog`, `Checkbox`, `Collapsible`, `Slot`을 가져온다.
Next.js client reference manifest에는 실제로 사용하지 않는 Accordion, Avatar, Select,
Tabs 등 Radix 모듈 전체가 초기 페이지 청크에 포함된다. `radix-ui/dialog`,
`radix-ui/checkbox`, `radix-ui/slot` 하위 경로를 직접 import한다.

`AlgorithmInfo`의 단순 열기/닫기는 네이티브 `<details>/<summary>`로 충분하다. 이를
서버 컴포넌트로 바꾸고 더 이상 필요 없는 `components/ui/collapsible.tsx`를 삭제한다.

### P0: XLSX를 정적 API 응답으로 사전 생성

현재 `FilteredDownloadButton`은 클릭 시 정적 JSON API에서 약 195 kB를 받고,
412.6 kB의 `xlsx` 비동기 청크를 내려받아 브라우저에서 545행을 변환한다. `xlsx`는
초기 번들에는 포함되지 않으므로 기존 코드 스플리팅은 정상이다. 다만 다운로드 사용자에게
필요한 네트워크와 CPU 비용은 남아 있다.

`/api/filtered`의 `force-static`은 현재 배포 모델에 적합하므로 유지한다. 대신 Route
Handler가 빌드 시 `filtered_full.json`을 XLSX 바이너리로 변환하고 다음 헤더로 응답한다.

- `Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- `Content-Disposition: attachment; filename*=UTF-8''...`
- `Cache-Control: public, max-age=0, s-maxage=31536000, immutable`

`FilteredDownloadButton`은 클라이언트 fetch, 상태, 오류 처리, dynamic import를 제거한
일반 다운로드 링크가 된다. 결과적으로 페이지와 다운로드 경로 모두에서 클라이언트용
`xlsx` 청크가 사라진다.

### P1: 저사용 UI 지연 로딩

관리자 인증 전에는 `UpdateControls`가 필요하지 않다. `AdminGate`가 인증 성공 후
`next/dynamic`으로 `UpdateControls`를 로드하도록 하며 `page.tsx`의 children 전달을
제거한다. 관리자 기능은 초기 페이지 청크에서 분리된다.

종목 프로필 Dialog도 종목을 클릭한 이후에만 필요하다. `ScreeningTable`에서
`StockProfileDialog`를 dynamic import하고 `dialogRow`가 있을 때만 렌더링한다.
첫 클릭에 작은 지연이 있을 수 있으나 초기 페이지 다운로드 감소를 우선한다.

### P1: 타입과 오류 처리 정리

공유 타입을 `web/lib/types.ts`로 옮긴다.

- `StockProfile`
- `ResultRow` (`stock_code`와 `name` 필수)
- `ResultsPayload`
- 가격 API 응답 타입

`web/lib/errors.ts`에 `getErrorMessage(error: unknown): string`을 두고 클라이언트 및
Route Handler의 `catch (e: any)`를 제거한다. KRX 응답은 필요한 필드만 갖는 타입으로
정의한다. `page.tsx`와 클라이언트 컴포넌트는 `import type`을 사용한다.

테이블 row key는 필수 `stock_code`만 사용한다. 정렬은 현재 `useMemo`를 유지한다.
50행 규모에서는 `React.memo`, 행 가상화, 추가 `useCallback`이 오히려 복잡성을
늘리므로 도입하지 않는다.

### P2: Next.js 설정 정리

`next.config.js`에 다음만 추가한다.

- `outputFileTracingRoot: __dirname`: workspace root 오인 경고 제거
- `poweredByHeader: false`: 불필요한 응답 헤더 제거

`compress`는 Next.js 기본값이 이미 `true`이므로 중복 설정하지 않는다. 현재 이미지가
없어 `images` 설정도 추가하지 않는다. `lucide-react` named import는 트리셰이킹되고 있어
변경하지 않는다.

### 유지할 선택

- Tailwind 4 생성 CSS 32.6 kB는 정상 범위이다.
- `tw-animate-css`는 Dialog 전환 애니메이션 클래스에 사용되므로 유지한다.
- `filtered_full.json`은 화면에 렌더링되지 않고 XLSX 생성 입력으로만 사용된다.
- 화면 테이블은 `results.json` 상위 50종목만 렌더링하므로 페이지네이션과 가상
  스크롤을 도입하지 않는다.
- `/api/filtered`는 정적 배포마다 새로 생성되므로 `force-static`을 유지한다.

## 데이터 흐름

### 초기 페이지

1. 빌드 시 `page.tsx`가 `results.json`을 읽는다.
2. 정적 HTML/RSC에 상위 50종목만 포함한다.
3. 서버 컴포넌트로 전환된 알고리즘 설명과 다운로드 링크는 별도 hydration이 없다.
4. 관리자 업데이트 UI와 종목 Dialog는 필요한 시점에 별도 청크로 로드한다.

### 전체 종목 XLSX 다운로드

1. 빌드 시 `/api/filtered` Route Handler가 `filtered_full.json`을 읽는다.
2. 한국어 컬럼명으로 행을 변환해 압축 XLSX 바이너리를 생성한다.
3. Vercel 정적 배포물에 API 응답이 포함된다.
4. 사용자는 링크 클릭 한 번으로 약 107 kB XLSX를 직접 내려받는다.

## 오류 처리

- `filtered_full.json`이 없으면 `/api/filtered`는 기존과 같이 404 JSON 응답을 반환한다.
- 파일이 존재하지만 잘못된 형식이면 빌드가 실패하게 해 손상된 다운로드가 배포되지
  않도록 한다.
- 클라이언트 fetch 오류는 `unknown`을 공통 함수로 안전하게 문자열화한다.
- dynamic import 중에는 짧은 텍스트 로딩 상태를 표시한다.

## 테스트 및 검증

행동 변경은 테스트 우선으로 진행한다.

- 정적 XLSX 생성 함수: ZIP/XLSX 시그니처, 한국어 헤더, 행 수 검증
- 오류 메시지 함수: `Error`, 문자열, 임의 값 검증
- 기존 문자열/배열 경쟁사 정규화가 유지되는지 검증
- `npm run build`로 TypeScript, 정적 Route 생성, 전체 프로덕션 빌드 검증
- `.next/server/app/api/filtered.body`가 XLSX 바이너리인지와 응답 헤더 검증
- 변경 전후 `/` Route Size와 First Load JS 비교
- 로컬 브라우저에서 정렬, 가격 새로고침, 종목 Dialog, 관리자 로그인 UI,
  XLSX 다운로드를 확인

## 영향 파일

- `web/app/page.tsx`
- `web/app/ScreeningTable.tsx`
- `web/app/FilteredDownloadButton.tsx`
- `web/app/StockProfileDialog.tsx`
- `web/app/AdminGate.tsx`
- `web/app/AlgorithmInfo.tsx`
- `web/app/UpdateControls.tsx`
- `web/app/api/filtered/route.ts`
- `web/app/api/prices/route.ts`
- `web/components/ui/badge.tsx`
- `web/components/ui/button.tsx`
- `web/components/ui/checkbox.tsx`
- `web/components/ui/dialog.tsx`
- `web/components/ui/collapsible.tsx` (삭제)
- `web/lib/types.ts` (신규)
- `web/lib/errors.ts` (신규)
- `web/lib/filtered-workbook.ts` (신규)
- `web/next.config.js`
- `web/package.json` 및 테스트 설정(필요한 최소 범위)

`screening/` 및 `.github/workflows/`는 변경하지 않는다.
