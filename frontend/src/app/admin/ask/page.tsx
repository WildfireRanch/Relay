//#region Admin Ask Page (server component, noindex)
// Purpose: Host the admin UI while keeping metadata server-side.
// Notes: Renders a client component for interactive behavior.

import AskConsole from "./Console"

export const metadata = { robots: { index: false, follow: false } }

export default function AskAdmin() {
  return <AskConsole />
}
//#endregion
