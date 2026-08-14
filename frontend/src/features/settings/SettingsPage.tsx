import { useState } from "react";
import { KeyRound, ShieldCheck, UserRound } from "lucide-react";

import { PageHeader } from "../../components";
import { AccountTab } from "./AccountTab";
import { AgentAccessPage } from "./AgentAccessPage";
import { SecurityTab } from "./SecurityTab";

const TABS = [
  { id: "account", label: "Account", description: "Name and planning week", Icon: UserRound },
  { id: "security", label: "Security", description: "Password and sessions", Icon: ShieldCheck },
  { id: "api", label: "System access", description: "Apps and agents", Icon: KeyRound },
] as const;

export function SettingsPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("account");
  return (
    <main className="page-shell settings-page">
      <PageHeader
        eyebrow="Owner settings"
        title="Settings"
        description="Manage your account and sign-in sessions. System connections stay separate from everyday settings."
      />
      <div className="settings-workspace">
      <div className="settings-tabs" role="tablist" aria-label="Settings sections">
        {TABS.map(({ id, label, description, Icon }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-label={label}
            id={`settings-tab-${id}`}
            aria-selected={tab === id}
            aria-controls={`settings-panel-${id}`}
            className="settings-tab"
            onClick={() => setTab(id)}
          >
            <Icon aria-hidden="true" /><span><strong>{label}</strong><small>{description}</small></span>
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
            <AgentAccessPage embedded />
          </div>
        ) : null}
      </div>
      </div>
    </main>
  );
}
