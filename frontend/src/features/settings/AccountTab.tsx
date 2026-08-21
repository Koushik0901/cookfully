import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";

import { Button, ErrorRecovery, Field, SectionHeading, Select, Skeleton } from "../../components";
import { planningApi } from "../plans/api";

const TIMEZONES = ["UTC", "America/Vancouver", "America/New_York", "Europe/London"];

export function AccountTab() {
  const queryClient = useQueryClient();
  const preferences = useQuery({ queryKey: ["owner-preferences"], queryFn: planningApi.preferences });
  const [displayName, setDisplayName] = useState("");
  const [timezone, setTimezone] = useState("UTC");
  const [weekStartsOn, setWeekStartsOn] = useState("1");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!preferences.data) return;
    setDisplayName(preferences.data.displayName);
    setTimezone(preferences.data.timezone);
    setWeekStartsOn(String(preferences.data.weekStartsOn));
  }, [preferences.data]);

  const save = useMutation({
    mutationFn: () =>
      planningApi.updatePreferences({
        displayName: displayName.trim(),
        timezone,
        weekStartsOn: Number(weekStartsOn),
        version: preferences.data?.version ?? 1,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["owner-preferences"] });
      setSaved(true);
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setSaved(false);
    if (!displayName.trim()) return;
    save.mutate();
  }

  if (preferences.isPending) return <Skeleton label="Loading account details" lines={4} />;
  if (preferences.isError) {
    return (
      <ErrorRecovery
        title="Account details could not be loaded"
        onRetry={() => void preferences.refetch()}
      />
    );
  }

  return (
    <form className="settings-section" onSubmit={submit}>
      <SectionHeading title="Account" description="How Cookfully refers to you and when your planning week begins." />
      <div className="form-grid">
        <Field label="Display name">
          <input
            className="input"
            value={displayName}
            maxLength={80}
            onChange={(event) => setDisplayName(event.target.value)}
          />
        </Field>
        <Field label="Timezone">
          <Select
            value={timezone}
            onChange={(event) => setTimezone(event.target.value)}
          >
            {!TIMEZONES.includes(timezone) ? <option value={timezone}>{timezone}</option> : null}
            {TIMEZONES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Week starts on">
          <Select
            value={weekStartsOn}
            onChange={(event) => setWeekStartsOn(event.target.value)}
          >
            <option value="1">Monday</option>
            <option value="7">Sunday</option>
            <option value="6">Saturday</option>
          </Select>
        </Field>
      </div>
      {save.error instanceof Error ? (
        <p className="error-text" role="alert">
          {save.error.message}
        </p>
      ) : null}
      {saved ? (
        <p className="success-text" role="status">
          Account details saved.
        </p>
      ) : null}
      <div className="actions">
        <Button type="submit" disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save account"}
        </Button>
      </div>
    </form>
  );
}
