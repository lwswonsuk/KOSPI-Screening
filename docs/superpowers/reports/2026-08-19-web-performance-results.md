# 웹 성능 최적화 결과

측정일: 2026-08-19
대상: `web/` Next.js 15 production build (`npm.cmd run build`)

## 번들 및 산출물 비교

| 항목 | 기준선 | 최종 | 변화 |
| --- | ---: | ---: | ---: |
| `/` Route Size | 95 kB | 27.8 kB | -67.2 kB (-70.7%) |
| `/` First Load JS | 197 kB | 130 kB | -67 kB (-34.0%) |
| 공통 First Load JS | 102 kB | 103 kB | +1 kB |
| 생성 CSS | 32,639 bytes | 33,050 bytes | +411 bytes (+1.3%) |
| 전체 종목 다운로드 payload | JSON 194,742 bytes | XLSX 106,619 bytes | -88,123 bytes (-45.2%) |

`/api/filtered`의 생성 body는 `PK` 매직 바이트를 확인했다. 클라이언트 chunk의
`SheetJS`/`xlsx` 검색 결과와 page client-reference manifest의 `radix-ui` 검색 결과는
모두 0건이다.

측정은 `web/`에서 `npm.cmd run build`를 실행한 뒤 `.next/static/css/*.css`와
`.next/static/chunks/`를 검사하고, production server의 `/api/filtered` 응답 body를
`Invoke-WebRequest`로 측정했다. 원본 JSON 경로는 `web/data/filtered_full.json`이며,
XLSX는 정적 route 산출물 `.next/server/app/api/filtered.body`와 HTTP 응답에서 동일한
106,619 bytes였다.

## 적용한 변경과 이유

- `radix-ui` 루트 배럴 import를 각 하위 모듈 import로 바꿔 초기 클라이언트 번들에서
  사용하지 않는 Radix 컴포넌트를 제거했다.
- 단순한 스크리닝 설명 토글을 서버 렌더링 네이티브 `<details>`로 바꿔 hydration을 없앴다.
- 전체 필터 통과 종목은 빌드 시 XLSX로 생성해 정적 `/api/filtered`에서 내려주며,
  브라우저의 SheetJS 로딩과 JSON fetch waterfall을 제거했다.
- 종목 프로필 Dialog와 인증 후 관리자 도구를 조건부 dynamic import해 초기 경로에서
  분리했다.
- `outputFileTracingRoot: __dirname`으로 `web/`을 tracing 기준점으로 명시하고,
  `poweredByHeader: false`로 응답 헤더를 정리했다. 최종 build에서 workspace-root
  추론 경고는 나타나지 않았다.

## 검증

- `npm.cmd test`: 4 files, 18 tests PASS
- `npx.cmd tsc --noEmit`: PASS
- `npm.cmd run build`: PASS
- production HTTP smoke test: 메인 페이지 200, 종목 표 HTML 포함, XLSX route 200,
  `Content-Type`/`Content-Disposition`, 106,619 bytes 및 `PK` 매직 바이트 확인
- UI 브라우저 자동화: 실행 환경이 브라우저 런타임 시작 시 `EPERM`으로
  `C:\Users\lwswo\AppData` 접근을 거부해 수행하지 못했다. 따라서 정렬, Dialog 조작,
  관리자 인증 흐름은 이번 자동 검증에서 미확인 상태다.

## 이번에 보류한 항목

- 초기 표는 상위 50행만 렌더링하므로 페이지네이션·가상 스크롤을 추가하지 않았다.
  전체 545종목은 XLSX 다운로드 전용이다.
- 이미지가 없으므로 `next/image` 또는 `images` 설정을 추가하지 않았다.
- Next.js 기본값으로 충분하므로 `compress`를 명시하지 않았다.
- 생성 CSS 증가는 정상 범위이고 실제 애니메이션을 사용하므로 Tailwind 4와
  `tw-animate-css`를 유지했다.
- `lucide-react`는 named import가 tree-shaking되므로 유지했다.
