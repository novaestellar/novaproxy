import { forwardRef } from "react";
import type { InputHTMLAttributes, SelectHTMLAttributes } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "h-9 w-full rounded-md border border-border bg-background/60 px-3 text-sm text-fg",
        "placeholder:text-faint focus-visible:border-accent/60 focus-visible:outline-none",
        "focus-visible:ring-2 focus-visible:ring-accent/20 disabled:opacity-50",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export const NativeSelect = forwardRef<
  HTMLSelectElement,
  SelectHTMLAttributes<HTMLSelectElement>
>(({ className, children, ...props }, ref) => (
  <div className="relative">
    <select
      ref={ref}
      className={cn(
        "h-9 w-full appearance-none rounded-md border border-border bg-background/60 pl-3 pr-8 text-sm text-fg",
        "focus-visible:border-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/20",
        className,
      )}
      {...props}
    >
      {children}
    </select>
    <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 size-4 -translate-y-1/2 text-faint" />
  </div>
));
NativeSelect.displayName = "NativeSelect";

export function Label({
  className,
  ...props
}: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn("mb-1.5 block text-xs font-medium text-muted", className)}
      {...props}
    />
  );
}
