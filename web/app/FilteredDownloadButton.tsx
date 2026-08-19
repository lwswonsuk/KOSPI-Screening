import { Download } from "lucide-react";
import { Badge } from "@/components/ui/badge";

interface Props {
  passed: number;
  total: number;
}

export default function FilteredDownloadButton({ passed, total }: Props) {
  return (
    <Badge asChild variant="secondary">
      <a href="/api/filtered">
        <Download className="mr-1 size-3" />
        필터 통과 {passed} / {total}
      </a>
    </Badge>
  );
}
