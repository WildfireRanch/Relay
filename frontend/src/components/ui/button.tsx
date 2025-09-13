// File: components/ui/button.tsx
// Purpose: Production-ready Button with variants, sizes, loading state, and forwardRef.
// Notes:
// - Backwards-compatible with your existing props.
// - Adds `isLoading`, `fullWidth`, and a11y improvements.
// - Keeps `asChild` support for polymorphic usage (e.g., <Link>).

import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

export const buttonVariants = cva(
  [
    "inline-flex items-center justify-center gap-2 whitespace-nowrap",
    "rounded-md text-sm font-medium transition-all",
    "disabled:pointer-events-none disabled:opacity-50",
    // SVG defaults
    "[&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 [&_svg]:shrink-0",
    // Focus and validation rings (Tailwind v4-safe)
    "outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:border-ring",
    "aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive",
  ].join(" "),
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground shadow-xs hover:bg-primary/90",
        destructive:
          "bg-destructive text-white shadow-xs hover:bg-destructive/90 focus-visible:ring-destructive/20 dark:focus-visible:ring-destructive/40 dark:bg-destructive/60",
        outline:
          "border bg-background shadow-xs hover:bg-accent hover:text-accent-foreground dark:bg-input/30 dark:border-input dark:hover:bg-input/50",
        secondary: "bg-secondary text-secondary-foreground shadow-xs hover:bg-secondary/80",
        ghost: "hover:bg-accent hover:text-accent-foreground dark:hover:bg-accent/50",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 px-4 py-2 has-[>svg]:px-3",
        sm: "h-8 rounded-md gap-1.5 px-3 has-[>svg]:px-2.5",
        lg: "h-10 rounded-md px-6 has-[>svg]:px-4",
        xl: "h-11 rounded-lg px-7 has-[>svg]:px-5", // new
        xs: "h-7 rounded-md px-2.5 text-[13px] has-[>svg]:px-2", // new
        icon: "size-9", // square icon button
      },
      fullWidth: {
        true: "w-full",
        false: "",
      },
      // Optionally add a subtle "quiet" style later without breaking API
      // quiet: { true: "opacity-80 hover:opacity-100", false: "" },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
      fullWidth: false,
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  /** When true, shows a spinner and disables the button. */
  isLoading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, fullWidth, isLoading, asChild = false, children, disabled, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    const isDisabled = disabled || isLoading;

    return (
      <Comp
        // data-slot for testing/hooks
        data-slot="button"
        ref={ref}
        className={cn(buttonVariants({ variant, size, fullWidth, className }))}
        // a11y: mark busy when loading (announced to AT)
        aria-busy={isLoading || undefined}
        aria-live={isLoading ? "polite" : undefined}
        // prevent clicks while loading
        disabled={isDisabled}
        {...props}
      >
        {isLoading && (
          <Loader2
            aria-hidden="true"
            className="animate-spin"
          />
        )}
        {children}
      </Comp>
    );
  }
);

Button.displayName = "Button";
