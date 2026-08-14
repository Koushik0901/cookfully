import { ChevronDown } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Cookfully keeps the platform picker for dependable keyboard and mobile
 * behavior, while owning the trigger surface and interaction states.
 */
function Select({ className, children, ...props }: React.ComponentProps<"select">) {
  return (
    <span className="cf-select-shell">
      <select data-slot="select" className={cn("input cf-select", className)} {...props}>
        {children}
      </select>
      <ChevronDown className="cf-select__chevron" aria-hidden="true" />
    </span>
  );
}

export { Select };
