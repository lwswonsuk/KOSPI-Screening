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
| `filtered_full.json` | 194,742 bytes | 다운로드 전용 | - |
| `/api/filtered` XLSX body | 예상 106,619 bytes | 106,619 bytes | JSON 대비 -88,123 bytes (-45.2%) |

`/api/filtered`의 생성 body는 `PK` 매직 바이트를 확인했다. 클라이언트 chunk의
`SheetJS`/`xlsx` 검색 결과와 page client-reference manifest의 `radix-ui` 검색 결과는
모두 0건이다.

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

- `npm.cmd test`: 4 files, 17 tests PASS
- `npx.cmd tsc --noEmit`: PASS
- `npm.cmd run build`: PASS
- 브라우저 동작 검증: 컨트롤러 검증 예정

## 이번에 보류한 항목

- 초기 표는 상위 50행만 렌더링하므로 페이지네이션·가상 스크롤을 추가하지 않았다.
  전체 545종목은 XLSX 다운로드 전용이다.
- 이미지가 없으므로 `next/image` 또는 `images` 설정을 추가하지 않았다.
- Next.js 기본값으로 충분하므로 `compress`를 명시하지 않았다.
- 생성 CSS 증가는 정상 범위이고 실제 애니메이션을 사용하므로 Tailwind 4와
  `tw-animate-css`를 유지했다.
- `lucide-react`는 named import가 tree-shaking되므로 유지했다.
