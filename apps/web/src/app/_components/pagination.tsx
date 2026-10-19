import { ChevronLeftIcon, ChevronRightIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
export function Pagination({
  offset,
  count,
  change,
}: {
  offset: number;
  count: number;
  change: (value: number) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3 border-t px-4 py-3">
      <p className="text-xs text-muted-foreground">
        {count ? `${offset + 1}–${offset + count}` : "0 records"}
      </p>
      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={!offset}
          onClick={() => change(Math.max(0, offset - 25))}
        >
          <ChevronLeftIcon />
          Previous
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={count < 25}
          onClick={() => change(offset + 25)}
        >
          Next
          <ChevronRightIcon />
        </Button>
      </div>
    </div>
  );
}
