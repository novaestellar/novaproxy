import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Progress({
  value,
  className,
  indicatorClassName,
}: {
  value: number;
  className?: string;
  indicatorClassName?: string;
}) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div
      className={cn("h-1.5 w-full overflow-hidden rounded-full bg-elevated", className)}
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className={cn(
          "h-full rounded-full bg-gradient-to-r from-accent to-[#a78bfa] transition-[width] duration-500",
          indicatorClassName,
        )}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}

export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("animate-pulse rounded-md bg-elevated", className)} {...props} />;
}
