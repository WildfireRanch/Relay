// ─── Ops Hydration Canary (Playwright) ───────────────────────────────────────
// Verifies /ops loads without hydration errors in the console.

import { test, expect } from "@playwright/test"

test("ops page has no hydration errors", async ({ page }) => {
  const errors: string[] = []
  page.on("pageerror", (e) => errors.push(e.message))
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text())
  })

  await page.goto("/ops")
  await expect(page).toHaveURL(/\/ops$/)

  // Assert no hydration/did not match errors surfaced
  expect(errors.join("\n")).not.toMatch(/hydration|did not match/i)
})

