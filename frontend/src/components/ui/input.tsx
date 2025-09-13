// File: components/ui/input.tsx
// Production-ready Input with forwardRef, size variants (fieldSize), and invalid state.
// Fixes: Avoids collision with native <input size> by renaming the variant.

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const inputVariants = cva(
  [
    // Base
    "block w-full min-w-0 rounded-md border bg-transparent",
    "text-base md:text-sm",
    "px-3 py-1 h-9", // default sizing (overridden by variants)
    "border-input dark:bg-input/30",
    "placeholder:text-muted-foreground file:text-foreground",
    "file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium",
    "selection:bg-primary selection:text-primary-foreground",
    "shadow-xs transition-[color,box-shadow] outline-none",
    "disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50",
    // Focus & validation rings
    "focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50",
    "aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive",
  ].join(" "),
  {
    variants: {
      // renamed from `size` -> `fieldSize` to avoid native prop collision
      fieldSize: {
        sm: "h-8 px-3 py-[3px] text-sm",
        md: "h-9 px-3 py-1 text-[0.95rem] md:text-sm",
        lg: "h-10 px-3.5 py-2 text-base",
      },
    },
    defaultVariants: {
      fieldSize: "md",
    },
  }
);

// Omit native 'size' to prevent conflicts with our variant
type NativeInputProps = Omit<React.InputHTMLAttributes<HTMLInputElement>, "size">;

export interface InputProps
  extends NativeInputProps,
    VariantProps<typeof inputVariants> {
  /** Sets aria-invalid for a11y + styles (optional). */
  invalid?: boolean;
  /** Visual size control for the component (sm|md|lg). */
  fieldSize?: "sm" | "md" | "lg";
}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type = "text", fieldSize, invalid, ...props }, ref) => {
    return (
      <input
        ref={ref}
        type={type}
        data-slot="input"
        aria-invalid={invalid || undefined}
        className={cn(inputVariants({ fieldSize }), className)}
        {...props}
      />
    );
  }
);

Input.displayName = "Input";

export { Input, inputVariants };
