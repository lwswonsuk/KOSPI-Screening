"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, Info, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";

export default function AlgorithmInfo() {
  const [open, setOpen] = useState(false);

  return (
    <div className="mb-5 space-y-3">
      <Collapsible open={open} onOpenChange={setOpen}>
        <CollapsibleTrigger asChild>
          <Button variant="outline" size="sm">
            <Info className="size-3.5" />
            이 스크리닝은 어떤 기준으로 종목을 골랐나요?
            {open ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
          </Button>
        </CollapsibleTrigger>

        <CollapsibleContent>
          <Card className="mt-3 py-5">
            <CardContent className="space-y-4 text-sm leading-relaxed text-foreground/90">
              <p className="text-muted-foreground">
                핵심 아이디어:{" "}
                <b className="text-foreground">
                  실적·경쟁력은 괜찮은데 주가만 안 오른 종목을 찾아서 모아두고 기다린다.
                </b>
              </p>

              <div>
                <h4 className="mb-2 font-semibold text-foreground">1단계 — 하드 필터 (자동 제외 기준)</h4>
                <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
                  <li>시가총액 800억 원 이상 ~ 40조 원 이하</li>
                  <li>최근 거래대금 3억 원 이상 (유동성 필터)</li>
                  <li>부채비율 200% 초과 제외</li>
                  <li>ROE(3년 평균) 5% 미만 제외</li>
                  <li>최근 영업이익(TTM 기준) 적자 제외</li>
                  <li>최근 3개월 수익률 +60% 이상인 테마 급등 종목 제외</li>
                  <li>관리종목 제외</li>
                </ul>
              </div>

              <div>
                <h4 className="mb-2 font-semibold text-foreground">2단계 — 4대 팩터 종합 점수</h4>
                <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
                  <li><b className="text-foreground">체력 (30%)</b> — ROE 수준·안정성, 영업이익률, 부채비율, 매출 성장</li>
                  <li><b className="text-foreground">가격 (28%)</b> — PER·PBR 저평가 정도</li>
                  <li><b className="text-foreground">★괴리 (27%, 핵심 팩터)</b> — 실적은 개선되는데 주가는 빠진 정도</li>
                  <li><b className="text-foreground">환원여력 (15%)</b> — 배당 확대 여력 (낮은 배당성향 + 순현금 보유)</li>
                </ul>
                <p className="mt-2 text-muted-foreground">
                  각 팩터는 전체 종목 대비 백분위로 점수화되며, 위 가중치로 합산해{" "}
                  <b className="text-foreground">종합점수</b>를 만듭니다. 음식료·화장품·방산 등
                  특정 업종엔 가산점을, 테마성 업종엔 감점을 반영합니다.
                </p>
              </div>

              <div>
                <h4 className="mb-2 font-semibold text-foreground">데이터 기준</h4>
                <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
                  <li>가격/시가총액: KRX 공식 API, 표 상단에 표시된 기준일 종가</li>
                  <li>재무데이터: DART 공시자료, 최근 4분기(TTM) 누적 기준</li>
                  <li>대상: 코스피 전종목</li>
                </ul>
              </div>
            </CardContent>
          </Card>
        </CollapsibleContent>
      </Collapsible>

      <Alert className="border-muted-foreground/20 bg-transparent py-2.5">
        <ShieldAlert />
        <AlertDescription className="text-xs text-muted-foreground">
          이 페이지의 정보는 참고용 데이터이며 투자 조언이 아닙니다. 종목 선정 기준과 점수는
          특정 투자 전략을 기계적으로 구현한 것으로, 정확성이나 완전성을 보장하지 않습니다.
          투자 판단과 그에 따른 손익에 대한 책임은 전적으로 투자자 본인에게 있습니다.
        </AlertDescription>
      </Alert>
    </div>
  );
}

