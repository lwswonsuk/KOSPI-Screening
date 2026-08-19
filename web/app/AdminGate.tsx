"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import { ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { getErrorMessage } from "@/lib/errors";

const UpdateControls = dynamic(() => import("./UpdateControls"), {
  loading: () => <p className="mt-10 text-center text-xs text-muted-foreground">관리자 도구를 불러오는 중…</p>,
});

export default function AdminGate() {
  const [unlocked, setUnlocked] = useState(false);
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleLogin() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/admin-login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "로그인 실패");
      setUnlocked(true);
      setOpen(false);
      setPassword("");
    } catch (error: unknown) {
      setError(getErrorMessage(error, "로그인 실패"));
    } finally {
      setLoading(false);
    }
  }

  if (unlocked) {
    return <UpdateControls />;
  }

  return (
    <div className="mt-10 flex justify-center border-t pt-6">
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogTrigger asChild>
          <Button variant="ghost" size="sm" className="text-muted-foreground">
            <ShieldCheck className="size-3.5" />
            관리자
          </Button>
        </DialogTrigger>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>관리자 로그인</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-3">
            <Input
              type="password"
              placeholder="비밀번호"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleLogin()}
            />
            {error && <span className="text-xs text-destructive">{error}</span>}
            <Button onClick={handleLogin} disabled={loading || !password}>
              {loading ? "확인 중…" : "로그인"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
