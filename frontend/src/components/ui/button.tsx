import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "cf-button",
  {
    variants: {
      variant: {
        default: "cf-button--primary",
        outline: "cf-button--outline",
        secondary: "cf-button--secondary",
        ghost: "cf-button--ghost",
        destructive: "cf-button--destructive",
        link: "cf-button--link",
      },
      size: {
        default: "cf-button--md",
        xs: "cf-button--xs",
        sm: "cf-button--sm",
        lg: "cf-button--lg",
        icon: "cf-button--icon cf-button--md",
        "icon-xs": "cf-button--icon cf-button--xs",
        "icon-sm": "cf-button--icon cf-button--sm",
        "icon-lg": "cf-button--icon cf-button--lg",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button }
