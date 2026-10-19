import { ArrowUpRightIcon, SearchIcon } from "lucide-react";
import { useState } from "react";
import { Badge, Empty, Feedback, labels, outcomeTone, time } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useReplyJobs } from "@/queries/devices";
import { useWorkspace } from "@/stores/workspace";
import { Pagination } from "../_components/pagination";
import { useDeviceWorkspace } from "../workspace-context";
export function JobsPage() {
  const { device } = useDeviceWorkspace();
  const selectRequest = useWorkspace((state) => state.selectRequest);
  const [offset, setOffset] = useState(0);
  const [lookup, setLookup] = useState("");
  const supported =
    device.adapter.capabilities.includes("sms.inbox.read") &&
    device.adapter.capabilities.includes("sms.send");
  const jobs = useReplyJobs(device.device_id, offset, supported);
  return (
    <div className="space-y-6">
      <Card className="gap-0 overflow-hidden">
        <CardHeader className="pb-5">
          <CardTitle role="heading" aria-level={2}>
            Reply workflow
          </CardTitle>
          <CardDescription>Follow replies from generation to device acceptance.</CardDescription>
        </CardHeader>
        {!supported ? (
          <Empty title="SMS replies not supported">
            Automatic SMS replies need both inbox and submission capabilities.
          </Empty>
        ) : (
          <>
            <CardContent>
              <Feedback resource={jobs} />
            </CardContent>
            {jobs.data?.length === 0 && (
              <Empty title="No reply jobs">
                Eligible incoming messages create jobs when automatic replies are enabled.
              </Empty>
            )}
            {!!jobs.data?.length && (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="ps-6">Request</TableHead>
                    <TableHead>Workflow state</TableHead>
                    <TableHead className="hidden lg:table-cell">Created</TableHead>
                    <TableHead>
                      <span className="sr-only">Actions</span>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {jobs.data.map((job) => (
                    <TableRow className="job" key={job.record_id}>
                      <TableCell className="ps-6">
                        <code className="text-xs">{job.request_id.slice(0, 8)}…</code>
                        {job.issue && (
                          <p className="mt-1 text-xs text-muted-foreground">
                            {job.issue.replaceAll("_", " ")}
                          </p>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge tone={outcomeTone(job.state)}>
                          {labels[job.state] || job.state}
                        </Badge>
                      </TableCell>
                      <TableCell className="hidden text-xs text-muted-foreground lg:table-cell">
                        {time(job.created_at)}
                      </TableCell>
                      <TableCell className="text-end pe-4">
                        {["submitting", "completed", "interrupted"].includes(job.state) && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => selectRequest(job.request_id)}
                          >
                            View submission
                            <ArrowUpRightIcon />
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
            {jobs.data && (
              <Pagination offset={offset} count={jobs.data.length} change={setOffset} />
            )}
          </>
        )}
      </Card>
      <Card>
        <CardHeader>
          <CardTitle role="heading" aria-level={2}>
            Find submission progress
          </CardTitle>
          <CardDescription>
            Inspect an existing request without sending another SMS.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="flex flex-col gap-2 sm:flex-row"
            onSubmit={(event) => {
              event.preventDefault();
              selectRequest(lookup);
            }}
          >
            <Input
              aria-label="Submission request ID"
              value={lookup}
              placeholder="Submission request UUID"
              pattern="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
              onChange={(event) => setLookup(event.target.value)}
              required
            />
            <Button
              type="submit"
              variant="outline"
              disabled={!device.adapter.capabilities.includes("sms.send")}
            >
              <SearchIcon />
              Look up
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
