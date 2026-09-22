import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

/** The one elevation language every Command Center panel shares (direction contract
 * OWN-WORLD): a restrained lift off the dotted ground, never louder on one panel than
 * another. */
export function Panel({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "rounded-xl border border-white/[0.06] bg-card [box-shadow:var(--shadow-panel)]",
        className,
      )}
      {...props}
    />
  );
}
