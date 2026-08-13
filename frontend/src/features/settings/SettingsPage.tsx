import { useState } from "react";

import { PageHeader } from "../../components";
import { AccountTab } from "./AccountTab";
import { AgentAccessPage } from "./AgentAccessPage";
import { SecurityTab } from "./SecurityTab";

const TABS = [
  { id: "account", label: "Account" },
  { id: "security", label: "Security" },
  { id: "api", label: "API access" },
] as const;

export function SettingsPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("account");
  return (
    <main className="page-shell">
      <PageHeader
        eyebrow="Owner settings"
        title="Settings"
        description="Manage your account, sign-in sessions, and agent access."
      />
      <div className="settings-tabs" role="tablist" aria-label="Settings sections">
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`settings-tab-${id}`}
            aria-selected={tab === id}
            aria-controls={`settings-panel-${id}`}
            className={`settings-tab ${tab === id ? "settings-tab--active" : ""}`}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="settings-panels">
        {tab === "account" ? (
          <div id="settings-panel-account" role="tabpanel" aria-labelledby="settings-tab-account">
            <AccountTab />
          </div>
        ) : null}
        {tab === "security" ? (
          <div id="settings-panel-security" role="tabpanel" aria-labelledby="settings-tab-security">
            <SecurityTab />
          </div>
        ) : null}
        {tab === "api" ? (
          <div id="settings-panel-api" role="tabpanel" aria-labelledby="settings-tab-api">
            <AgentAccessPage />
          </div>
        ) : null}
      </div>
    </main>
  );
}
