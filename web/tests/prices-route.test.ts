import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET } from "../app/api/prices/route";

const VALID_ROW = {
  ISU_CD: "005930",
  TDD_CLSPRC: "75,000",
  FLUC_RT: "-1.25",
};

function stubKrxRows(rows: unknown[]) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
    Response.json({ OutBlock_1: rows })
  );
}

async function requestPrices() {
  return GET(new NextRequest("http://localhost/api/prices"));
}

describe("GET /api/prices", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("유효한 KRX 숫자 문자열만 유한한 가격 숫자로 변환한다", async () => {
    vi.stubEnv("KRX_API_KEY", "test-key");
    stubKrxRows([VALID_ROW]);

    const response = await requestPrices();

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      as_of: expect.stringMatching(/^\d{8}$/),
      prices: {
        "005930": { close: 75000, fluc_rt: -1.25 },
      },
    });
  });

  it.each([
    ["숫자가 아닌 종목코드", { ...VALID_ROW, ISU_CD: "ABC123" }],
    ["빈 종목코드", { ...VALID_ROW, ISU_CD: "" }],
    ["숫자가 아닌 종가", { ...VALID_ROW, TDD_CLSPRC: "N/A" }],
    ["빈 종가", { ...VALID_ROW, TDD_CLSPRC: "" }],
    ["비유한 종가", { ...VALID_ROW, TDD_CLSPRC: "1e999" }],
    ["잘못된 쉼표 형식 종가", { ...VALID_ROW, TDD_CLSPRC: "1,2" }],
    ["숫자가 아닌 등락률", { ...VALID_ROW, FLUC_RT: "N/A" }],
  ])("%s 행을 가격 응답에서 거부한다", async (_label, row) => {
    vi.stubEnv("KRX_API_KEY", "test-key");
    stubKrxRows([row]);

    const response = await requestPrices();

    expect(response.status).toBe(502);
    expect(await response.json()).toEqual({
      error: "최근 7일 내 KRX 시세 데이터를 찾지 못했습니다.",
    });
  });
});
