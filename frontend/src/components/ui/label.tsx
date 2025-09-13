"use client";

import * as React from "react";
import * as LabelPrimitive from "@radix-ui/react-label";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const labelVariants = cva(
  [
    "flex items-center gap-2 select-none font-medium leading-none",
    // respects disabled state from a wrapping .group or a peer input
    "group-data-[disabled=true]:pointer-events-none group-data-[disabled=true]:opacity-50",
    "peer-disabled:cursor-not-allowed peer-disabled:opacity-50",
  ].join(" "),
  {
    variants: {
      size: {
        sm: "text-xs",
        md: "text-sm",
        lg: "text-base",
      },
      muted: {
        true: "text-muted-foreground",
        false: "",
      },
    },
    defaultVariants: {
      size: "md",
      muted: false,
    },
  }
);

export interface LabelProps
  extends React.ComponentPropsWithoutRef<typeof LabelPrimitive.Root>,
    VariantProps<typeof labelVariants> {
  /** Visually mark the field as required (use `aria-required` on the input for a11y). */
  requiredMark?: boolean;
  /** Show an `(optional)` hint. Mutually exclusive with `requiredMark`. */
  optionalMark?: boolean;
}

export const Label = React.forwardRef<
  React.ElementRef<typeof LabelPrimitive.Root>,
  LabelProps
>(({ className, size, muted, requiredMark, optionalMark, children, ...props }, ref) => {
  return (
    <LabelPrimitive.Root
      ref={ref}
      data-slot="label"
      className={cn(labelVariants({ size, muted }), className)}
      {...props}
    >
      <span>{children}</span>

      {requiredMark && !optionalMark && (
        <span
          aria-hidden="true"
          className="text-destructive"
          title="Required"
        >
          *
        </span>
      )}

      {optionalMark && !requiredMark && (
        <span className="text-muted-foreground text-[0.8em]">(optional)</span>
      )}
    </LabelPrimitive.Root>
  );
});

Label.displayName = "Label";
