import { useEffect, useRef, useState } from "react";
import { ApiError, type Balance } from "@/api/client";
import { useApi } from "@/components/providers/api-provider";
import { Badge, time } from "@/components/shared";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
export function BalancePanel({ deviceId, supported }: { deviceId: string; supported: boolean }) {
  const api = useApi();
  const [balance, setBalance] = useState<Balance>();
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  async function consult() {
    const request = new AbortController();
    controller.current = request;
    setBusy(true);
    setError(undefined);
    setBalance(undefined);
    try {
      setBalance(await api.balance(deviceId, request.signal));
    } catch (error) {
      if (!request.signal.aborted)
        setError(error instanceof ApiError ? error.message : "Balance consultation failed.");
    } finally {
      if (!request.signal.aborted) setBusy(false);
    }
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle
          role="heading"
          aria-level={2}
          className="flex items-center justify-between gap-3"
        >
          Carrier balance{!supported && <Badge>Not supported</Badge>}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {!supported ? (
          <p className="text-sm text-muted-foreground">
            This device adapter does not offer balance consultation.
          </p>
        ) : (
          <>
            <p className="text-sm text-muted-foreground">
              Consult on demand using the configured carrier policy.
            </p>
            <Button variant="outline" disabled={busy} onClick={() => void consult()}>
              {busy ? "Consulting…" : "Consult balance"}
            </Button>
          </>
        )}
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        {balance && (
          <>
            <p className="whitespace-pre-wrap text-sm">{balance.raw_text}</p>
            <dl className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <dt className="text-muted-foreground">Credit</dt>
                <dd className="mt-1 font-medium">
                  {balance.credit
                    ? `${balance.credit.amount} ${balance.credit.currency}`
                    : "Not reported"}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">SMS allowance</dt>
                <dd className="mt-1 font-medium">
                  {balance.sms_allowance?.remaining ?? "Not reported"}
                </dd>
              </div>
            </dl>
            {balance.credit?.conditions && (
              <p className="text-sm text-muted-foreground">{balance.credit.conditions}</p>
            )}
            {balance.sms_allowance?.conditions && (
              <p className="text-sm text-muted-foreground">{balance.sms_allowance.conditions}</p>
            )}
            <p className="text-xs text-muted-foreground">Observed {time(balance.observed_at)}</p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
