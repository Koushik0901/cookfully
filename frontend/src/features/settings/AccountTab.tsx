import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";

import { Button, ErrorRecovery, Field, SectionHeading, Select, Skeleton } from "../../components";
import { PwaInstallCard } from "../../app/MobileRuntime";
import { longDate, todayInTimezone, weekStartFor } from "../plans/dates";
import { planningApi } from "../plans/api";

const TIMEZONES = (() => {
  const supportedValuesOf = (Intl as typeof Intl & { supportedValuesOf?: (key: string) => string[] }).supportedValuesOf;
  return [...new Set(["UTC", ...(supportedValuesOf?.("timeZone") ?? ["America/Vancouver", "America/New_York", "Europe/London"])])].sort();
})();
const BROWSER_TIMEZONE = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

export function AccountTab() {
  const queryClient = useQueryClient();
  const preferences = useQuery({ queryKey: ["owner-preferences"], queryFn: planningApi.preferences });
  const [displayName, setDisplayName] = useState("");
  const [timezone, setTimezone] = useState(BROWSER_TIMEZONE);
  const [weekStartsOn, setWeekStartsOn] = useState("1");
  const [saved, setSaved] = useState(false);
  const [nameError, setNameError] = useState("");

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

  const timezoneChanged = Boolean(preferences.data && timezone !== preferences.data.timezone);
  const weekStartChanged = Boolean(preferences.data && Number(weekStartsOn) !== preferences.data.weekStartsOn);
  const previewToday = todayInTimezone(timezone);
  const previewWeekStart = weekStartFor(previewToday, Number(weekStartsOn));

  function submit(event: FormEvent) {
    event.preventDefault();
    setSaved(false);
    if (!displayName.trim()) {
      setNameError("Add a name so Cookfully knows how to address you.");
      return;
    }
    setNameError("");
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
    <>
      <form className="settings-section" onSubmit={submit}>
        <SectionHeading title="Account" description="How Cookfully refers to you and when your planning week begins." />
        <div className="form-grid">
          <Field label="Display name" error={nameError}>
            <input
              className="input"
              value={displayName}
              maxLength={80}
              onChange={(event) => { setDisplayName(event.target.value); setNameError(""); }}
            />
          </Field>
          <Field label="Timezone" hint="Search any IANA timezone, or use the timezone detected by this browser.">
            <div>
              <input className="input" list="cookfully-timezones" value={timezone} onChange={(event) => setTimezone(event.target.value)} />
              <datalist id="cookfully-timezones">{TIMEZONES.map((value) => <option key={value} value={value} />)}</datalist>
              {timezone !== BROWSER_TIMEZONE ? <button className="text-link" type="button" onClick={() => setTimezone(BROWSER_TIMEZONE)}>Use browser timezone ({BROWSER_TIMEZONE})</button> : null}
            </div>
          </Field>
          <Field label="Week starts on">
            <Select
              value={weekStartsOn}
              onChange={(event) => setWeekStartsOn(event.target.value)}
            >
              <option value="1">Monday</option>
              <option value="2">Tuesday</option>
              <option value="3">Wednesday</option>
              <option value="4">Thursday</option>
              <option value="5">Friday</option>
              <option value="6">Saturday</option>
              <option value="7">Sunday</option>
            </Select>
          </Field>
        </div>
        {timezoneChanged || weekStartChanged ? <div className="settings-impact" role="status">
          <strong>Before you save</strong>
          <p>{timezoneChanged ? `Today will be ${longDate(previewToday)} in ${timezone}.` : null}{timezoneChanged && weekStartChanged ? " " : null}{weekStartChanged ? `Your current planning week will begin on ${longDate(previewWeekStart)}.` : null}</p>
          <small>These settings change which days are locked as past, which week Home summarizes, and when grocery lists are generated.</small>
        </div> : null}
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
      <PwaInstallCard />
    </>
  );
}
