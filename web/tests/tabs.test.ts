import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

describe("components/ui/tabs.tsx", () => {
  it("radix-ui/tabs 서브모듈을 import하고 4개 컴포넌트를 export한다", () => {
    const source = fs.readFileSync(
      path.join(process.cwd(), "components/ui/tabs.tsx"),
      "utf8"
    );

    expect(source).toContain('from "radix-ui/tabs"');
    expect(source).not.toMatch(/from ["']radix-ui["']/);
    expect(source).toContain('"use client"');
    expect(source).toMatch(/export\s*\{\s*Tabs,\s*TabsList,\s*TabsTrigger,\s*TabsContent\s*\}/);
  });
});
