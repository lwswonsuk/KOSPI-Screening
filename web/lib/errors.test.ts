import { describe, expect, it } from "vitest";
import { getErrorMessage } from "./errors";

describe("getErrorMessage", () => {
  it("Error 메시지를 반환한다", () => {
    expect(getErrorMessage(new Error("실패"), "기본 오류")).toBe("실패");
  });

  it("비어 있지 않은 문자열 오류를 반환한다", () => {
    expect(getErrorMessage("문자열 오류", "기본 오류")).toBe("문자열 오류");
  });

  it("알 수 없는 값에는 fallback을 반환한다", () => {
    expect(getErrorMessage({ code: 500 }, "기본 오류")).toBe("기본 오류");
  });
});
