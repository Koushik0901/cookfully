import { useState } from "react";
import { Cpu, Database, KeyRound, ListTodo, ShieldCheck, UserRound } from "lucide-react";

import { PageHeader, TabList } from "../../components";
import { AccountTab } from "./AccountTab";
import { AgentAccessPage } from "./AgentAccessPage";
import { SecurityTab } from "./SecurityTab";
import { NutritionDataTab } from "../referenceData/NutritionDataTab";
import { NutritionIntelligenceTab } from "./NutritionIntelligenceTab";
import { JobsTab } from "./JobsTab";

const TABS = [
  { id: "account", label: "Account", description: "Name and planning week", Icon: UserRound },
  { id: "security", label: "Security", description: "Password and sessions", Icon: ShieldCheck },
  { id: "api", label: "Connections", description: "Third-party apps and access keys", Icon: KeyRound },
  { id: "data", label: "Nutrition data", description: "USDA reference foods", Icon: Database },
  { id: "intelligence", label: "Intelligence", description: "Models and workload", Icon: Cpu },
  { id: "jobs", label: "Jobs", description: "Background processing", Icon: ListTodo },
] as const;

export function SettingsPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("account");
  return (
    <main className="page-shell settings-page">
      <PageHeader
        eyebrow="Owner settings"
        title="Settings"
        description="Keep your account, privacy, connections, and local nutrition system in one quieter place. Everyday cooking stays out of the way."
      />
      <div className="settings-workspace">
      <TabList className="settings-tabs" label="Settings sections">
        {TABS.map(({ id, label, description, Icon }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-label={label}
            id={`settings-tab-${id}`}
            aria-selected={tab === id}
            tabIndex={tab === id ? 0 : -1}
            aria-controls={`settings-panel-${id}`}
            className="settings-tab"
            onClick={() => setTab(id)}
          >
            <Icon aria-hidden="true" /><span><strong>{label}</strong><small>{description}</small></span>
          </button>
        ))}
      </TabList>
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
        {tab === "data" ? (
          <div id="settings-panel-data" role="tabpanel" aria-labelledby="settings-tab-data">
            <NutritionDataTab />
          </div>
        ) : null}
        {tab === "intelligence" ? (
          <div id="settings-panel-intelligence" role="tabpanel" aria-labelledby="settings-tab-intelligence">
            <NutritionIntelligenceTab />
          </div>
        ) : null}
        {tab === "jobs" ? (
          <div id="settings-panel-jobs" role="tabpanel" aria-labelledby="settings-tab-jobs">
            <JobsTab />
          </div>
        ) : null}
      </div>
      </div>
    </main>
  );
}
