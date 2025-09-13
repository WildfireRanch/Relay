// File: components/ui/textarea.tsx
// Purpose: Textarea styled to match Input (same rings, invalid state, sizes).

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const textareaVariants = cva(
  [
    "block w-full min-w-0 rounded-md border bg-transparent",
    "text-base md:text-sm",
    "px-3 py-2",
    "border-input dark:bg-input/30",
    "placeholder:text-muted-foreground",
    "selection:bg-primary selection:text-primary-foreground",
    "shadow-xs transition-[color,box-shadow] outline-none",
    "disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50",
    "focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50",
    "aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive",
  ].join(" "),
  {
    variants: {
      size: {
        sm: "text-sm py-1.5",
        md: "text-[0.95rem] md:text-sm",
        lg: "text-base py-2.5",
      },
    },
    defaultVariants: {
      size: "md",
    },
  }
);

export interface TextareaProps
  extends React.TextareaHTMLAttributes<HTMLTextAreaElement>,
    VariantProps<typeof textareaVariants> {
  invalid?: boolean;
}

const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, size, invalid, rows = 4, ...props }, ref) => {
    return (
      <textarea
        ref={ref}
        rows={rows}
        data-slot="textarea"
        aria-invalid={invalid || undefined}
        className={cn(textareaVariants({ size }), className)}
        {...props}
      />
    );
  }
);

Textarea.displayName = "Textarea";

export { Textarea, textareaVariants };
