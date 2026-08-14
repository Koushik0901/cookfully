import * as Dialog from "@radix-ui/react-dialog";
import { useMutation } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button, Field } from "../../components";
import { recipesApi } from "./api";

export function RecipeImportDialog({ trigger, onImported }: { trigger: React.ReactNode; onImported?: () => void | Promise<unknown> }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState("");
  const [validation, setValidation] = useState("");
  const mutation = useMutation({
    mutationFn: recipesApi.import,
    onSuccess: async (accepted) => {
      try {
        await onImported?.();
      } catch {
        // The recipe already exists; optional onboarding persistence must not turn that into a failure.
      } finally {
        setOpen(false);
        if (accepted.resourceId) navigate(`/app/recipes/${accepted.resourceId}`, { state: { jobId: accepted.jobId, importUrl: url } });
      }
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    try {
      const parsed = new URL(url);
      if (!new Set(["http:", "https:"]).has(parsed.protocol)) throw new Error();
      setValidation("");
      mutation.mutate(url);
    } catch {
      setValidation("Enter a complete http or https recipe URL.");
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog" aria-describedby="import-description">
          <Dialog.Title>Import recipes</Dialog.Title>
          <Dialog.Description id="import-description">Paste a public recipe page or a structured cookbook PDF. A cookbook can add several recipes; import and nutrition processing continue in the background.</Dialog.Description>
          <form className="stack" onSubmit={submit}>
            <Field label="Recipe or cookbook URL" error={validation || (mutation.error instanceof Error ? mutation.error.message : undefined)}>
              <input className="input" type="url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://example.com/recipe-or-cookbook.pdf" required />
            </Field>
            <div className="actions"><Dialog.Close asChild><Button type="button" variant="secondary">Cancel</Button></Dialog.Close><Button type="submit" disabled={mutation.isPending}>{mutation.isPending ? "Starting…" : "Start import"}</Button></div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

