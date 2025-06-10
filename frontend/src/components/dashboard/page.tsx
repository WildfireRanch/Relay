// File: DashboardWizard.tsx
// Directory: frontend/src/components/dashboard
// Purpose: Multi-step, animated setup wizard for Command Center dashboard onboarding.
//   - Built with shadcn/ui components for consistent styling
//   - Uses Framer Motion for smooth step transitions
//   - Easy to customize steps/fields for your infra/ops flows

"use client";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { AnimatePresence, motion } from "framer-motion";

// ---- Wizard step definitions ----
// Each step defines a title and content (could use form logic, API calls, etc)
const steps = [
  {
    title: "Connect Infrastructure",
    content: (
      <>
        <p className="mb-4 text-sm text-muted-foreground">
          Connect your infrastructure to begin tracking data.
        </p>
        <Input placeholder="Enter node endpoint or IP" />
      </>
    ),
  },
  {
    title: "Add Notification Channel",
    content: (
      <>
        <p className="mb-4 text-sm text-muted-foreground">
          Add email or webhook to get alerts on events.
        </p>
        <Input placeholder="Email or webhook URL" />
      </>
    ),
  },
  {
    title: "Finish Setup",
    content: (
      <>
        <p className="mb-4 text-sm text-muted-foreground">
          You’re ready! Start using the Command Center.
        </p>
        <ul className="list-disc text-xs pl-5 text-muted-foreground">
          <li>Monitor live data</li>
          <li>Configure automations</li>
          <li>Access analytics & reports</li>
        </ul>
      </>
    ),
  },
];

export default function DashboardWizard() {
  // ---- State: Current wizard step ----
  const [step, setStep] = useState(0);

  // ---- Step navigation handlers ----
  const next = () => setStep((s) => Math.min(s + 1, steps.length - 1));
  const prev = () => setStep((s) => Math.max(s - 1, 0));

  return (
    <Card className="max-w-md mx-auto shadow-2xl">
      <CardHeader>
        <CardTitle>
          Setup Wizard
          <span className="ml-2 text-xs font-normal text-muted-foreground">
            Step {step + 1} of {steps.length}
          </span>
        </CardTitle>
        {/* Progress bar shows % complete */}
        <Progress value={((step + 1) / steps.length) * 100} className="h-2 mt-4" />
      </CardHeader>
      <CardContent>
        {/* Animated transition between steps */}
        <AnimatePresence mode="wait">
          <motion.div
            key={step}
            initial={{ opacity: 0, x: 24 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -24 }}
            transition={{ duration: 0.25 }}
            className="min-h-[110px]"
          >
            <h3 className="font-semibold mb-2">{steps[step].title}</h3>
            {steps[step].content}
          </motion.div>
        </AnimatePresence>
        {/* Navigation buttons */}
        <div className="flex justify-between mt-6">
          <Button variant="secondary" onClick={prev} disabled={step === 0}>
            Back
          </Button>
          <Button onClick={next} disabled={step === steps.length - 1}>
            {step === steps.length - 1 ? "Done" : "Next"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
