// File: components/GmailOps/GmailOpsPanel.tsx
// Purpose: Panel to send and view emails, now with SafeMarkdown rendering for messages and snippets.

"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { API_ROOT } from "@/lib/api";
import SafeMarkdown from "@/components/SafeMarkdown";

// Explicitly type the Email shape
type Email = {
  from: string;
  subject: string;
  date: string;
  snippet: string;
};

export default function GmailOpsPanel() {
  const [to, setTo] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [emails, setEmails] = useState<Email[]>([]);

  async function send() {
    const res = await fetch(`${API_ROOT}/control/send_email`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": process.env.NEXT_PUBLIC_API_KEY || "" },
      body: JSON.stringify({ to_email: to, subject, body })
    });
    const data = await res.json();
    setMsg(data.status === "sent" ? "Email sent!" : `Failed: ${data.detail}`);
  }

  async function list() {
    const res = await fetch(`${API_ROOT}/control/list_email`, {
      headers: { "X-API-Key": process.env.NEXT_PUBLIC_API_KEY || "" }
    });
    const data = await res.json();
    setEmails((data.emails as Email[]) || []);
  }

  return (
    <div className="max-w-2xl mx-auto my-8 space-y-4">
      <div>
        <h3 className="font-bold mb-2">Send Email</h3>
        <input className="border rounded px-2 py-1 w-full mb-1" placeholder="To Email" value={to} onChange={e => setTo(e.target.value)} />
        <input className="border rounded px-2 py-1 w-full mb-1" placeholder="Subject" value={subject} onChange={e => setSubject(e.target.value)} />
        <textarea className="border rounded px-2 py-1 w-full mb-2" placeholder="Body" rows={4} value={body} onChange={e => setBody(e.target.value)} />
        <Button onClick={send}>Send Email</Button>
        {msg && (
          <div className="text-xs mt-2">
            <div className="prose prose-neutral dark:prose-invert max-w-none">
              <SafeMarkdown>{msg}</SafeMarkdown>
            </div>
          </div>
        )}
      </div>
      <div>
        <h3 className="font-bold mb-2">List Recent Emails</h3>
        <Button onClick={list}>Refresh Inbox</Button>
        <ul className="mt-2 space-y-1">
          {emails.map((em, i) => (
            <li key={i} className="bg-gray-100 rounded p-2 text-xs">
              <div><strong>From:</strong> {em.from}</div>
              <div><strong>Subject:</strong> {em.subject}</div>
              <div><strong>Date:</strong> {em.date}</div>
              <div className="text-gray-500">
                <div className="prose prose-neutral dark:prose-invert max-w-none">
                  <SafeMarkdown>{em.snippet}</SafeMarkdown>
                </div>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
