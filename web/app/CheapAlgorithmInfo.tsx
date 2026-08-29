import { ChevronDown, Info, ShieldAlert } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";

export default function CheapAlgorithmInfo() {
  return (
    <div className="mb-5 space-y-3">
      <details className="group">
        <summary className="inline-flex h-8 cursor-pointer list-none items-center justify-center gap-2 rounded-md border bg-background px-3 text-sm font-medium shadow-xs transition-all hover:bg-accent hover:text-accent-foreground [&::-webkit-details-marker]:hidden">
          <Info className="size-3.5" />
          이 스크리닝은 어떤 기준으로 종목을 골랐나요?
          <ChevronDown className="size-3.5 transition-transform group-open:rotate-180" />
        </summary>
        <Card className="mt-3 py-5">
          <CardContent className="space-y-4 text-sm leading-relaxed text-foreground/90">
            <p className="text-muted-foreground">
              핵심 아이디어: <b className="text-foreground">싸게 사서 기다린다.</b> 아래 3가지
              조건을 모두 만족하는 종목만 통과시키며, 시가총액·거래대금 하한선은 두지 않습니다.
            </p>
            <section>
              <h4 className="mb-2 font-semibold text-foreground">통과 조건 (3가지 모두 충족)</h4>
              <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
                <li>현재가가 52주 최저가의 10% 이내</li>
                <li>영업이익(TTM)이 5년 전 영업이익보다 큼 — 실적이 여전히 성장 중</li>
                <li>EV/EBIT 10배 미만 — EV(기업가치) = 시가총액 + 총부채 − 현금성자산(근사치)</li>
              </ul>
            </section>
            <section>
              <h4 className="mb-2 font-semibold text-foreground">정렬 기준</h4>
              <p className="text-muted-foreground">EV/EBIT이 낮은(가장 저평가된) 순으로 정렬합니다.</p>
            </section>
            <section>
              <h4 className="mb-2 font-semibold text-foreground">데이터 기준</h4>
              <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
                <li>가격/52주 최저가: KRX 공식 API 일별 시세 누적 캐시 기준</li>
                <li>재무데이터: DART 공시자료, 최근 4분기(TTM) 누적 및 5년 전 사업보고서 기준</li>
                <li>대상: 코스피 전종목</li>
              </ul>
            </section>
          </CardContent>
        </Card>
      </details>

      <Alert className="border-muted-foreground/20 bg-transparent py-2.5">
        <ShieldAlert />
        <AlertDescription className="text-xs text-muted-foreground">
          이 페이지의 정보는 참고용 데이터이며 투자 조언이 아닙니다. 종목 선정 기준은 특정
          조건을 기계적으로 구현한 것으로, 정확성이나 완전성을 보장하지 않습니다. 투자 판단과
          그에 따른 손익에 대한 책임은 전적으로 투자자 본인에게 있습니다.
        </AlertDescription>
      </Alert>
    </div>
  );
}
