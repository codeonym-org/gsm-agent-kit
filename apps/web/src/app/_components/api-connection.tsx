import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
export function ApiConnection({
  open,
  onOpenChange,
  connected,
  connect,
  disconnect,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  connected: boolean;
  connect: (token: string) => void;
  disconnect: () => void;
}) {
  const [draft, setDraft] = useState("");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>API access</DialogTitle>
          <DialogDescription>
            Connect to your server. The access token stays in memory until you reload or disconnect.
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-5"
          onSubmit={(event) => {
            event.preventDefault();
            connect(draft.trim());
            setDraft("");
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="api-token">API access token</Label>
            <Input
              id="api-token"
              type="password"
              autoComplete="off"
              value={draft}
              placeholder="Server API token"
              onChange={(event) => setDraft(event.target.value)}
            />
          </div>
          <div className="flex justify-end gap-2">
            {connected && (
              <Button
                variant="outline"
                type="button"
                onClick={() => {
                  setDraft("");
                  disconnect();
                }}
              >
                Disconnect
              </Button>
            )}
            <Button type="submit">Connect</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
