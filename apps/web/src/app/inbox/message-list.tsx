import { ChevronRightIcon, MessageSquareIcon, SearchIcon } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Empty, Feedback, time } from "@/components/shared";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useMessages } from "@/queries/devices";
import { Pagination } from "../_components/pagination";
import { useDeviceWorkspace } from "../workspace-context";

export function MessageList({ preview = false }: { preview?: boolean }) {
  const { device } = useDeviceWorkspace();
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string>();
  const supported = device.adapter.capabilities.includes("sms.inbox.read");
  const inbox = useMessages(device.device_id, offset, supported);
  const rows = (inbox.data || []).filter((message) =>
    `${message.sender.value} ${message.body}`.toLowerCase().includes(search.toLowerCase()),
  );
  const selected = inbox.data?.find((message) => message.id === selectedId);
  return (
    <>
      <Card className="gap-0 overflow-hidden">
        <CardHeader className="pb-5">
          <CardTitle role="heading" aria-level={2}>
            {preview ? "Recent messages" : "Message inbox"}
          </CardTitle>
          <CardDescription>
            {preview
              ? "Latest messages received by this device."
              : "Browse the inbox stored on your server."}
          </CardDescription>
          {preview && (
            <CardAction>
              <Button asChild variant="ghost" size="sm">
                <Link to="/inbox">
                  View inbox
                  <ChevronRightIcon />
                </Link>
              </Button>
            </CardAction>
          )}
        </CardHeader>
        {!preview && supported && (
          <div className="px-6 pb-5">
            <div className="relative max-w-sm">
              <SearchIcon className="absolute start-2.5 top-2 size-4 text-muted-foreground" />
              <Input
                aria-label="Search messages on this page"
                placeholder="Search this page…"
                className="ps-9"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
          </div>
        )}
        {!supported ? (
          <Empty title="SMS inbox not supported">
            This cellular device does not declare an incoming SMS capability.
          </Empty>
        ) : (
          <>
            <CardContent className="px-6">
              <Feedback resource={inbox} />
            </CardContent>
            {inbox.data?.length === 0 && (
              <Empty title="No stored messages">
                Incoming messages appear after the server ingests the device inbox.
              </Empty>
            )}
            {inbox.data && inbox.data.length > 0 && !rows.length && (
              <Empty title="No matching messages">
                Try another sender or phrase. Search applies to this page.
              </Empty>
            )}
            {rows.length > 0 && (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="ps-6">Sender & message</TableHead>
                    <TableHead className="hidden sm:table-cell">State</TableHead>
                    <TableHead
                      className={`hidden text-end ${preview ? "2xl:table-cell" : "lg:table-cell"}`}
                    >
                      Received
                    </TableHead>
                    <TableHead className="w-12">
                      <span className="sr-only">Open message</span>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(preview ? rows.slice(0, 5) : rows).map((message) => (
                    <TableRow className="message" key={message.id}>
                      <TableCell className="max-w-0 py-4 ps-6">
                        <button
                          type="button"
                          className="flex w-full min-w-0 items-center gap-3 text-start outline-none focus-visible:ring-2 focus-visible:ring-ring"
                          onClick={() => setSelectedId(message.id)}
                        >
                          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg border bg-muted/40">
                            <MessageSquareIcon className="size-4 text-muted-foreground" />
                          </span>
                          <span className="min-w-0">
                            <span className="block truncate text-sm font-medium">
                              {message.sender.value}
                            </span>
                            <span className="mt-1 block truncate text-sm text-muted-foreground">
                              {message.body}
                            </span>
                          </span>
                        </button>
                      </TableCell>
                      <TableCell className="hidden sm:table-cell">
                        <Badge
                          tone={
                            !message.complete || message.subscription_uncertain
                              ? "warning"
                              : message.replyable
                                ? "success"
                                : "neutral"
                          }
                        >
                          {!message.complete
                            ? "Incomplete"
                            : message.subscription_uncertain
                              ? "SIM uncertain"
                              : message.baselined
                                ? "Existing at baseline"
                                : "Eligible for reply"}
                        </Badge>
                      </TableCell>
                      <TableCell
                        className={`hidden text-end text-xs text-muted-foreground ${preview ? "2xl:table-cell" : "lg:table-cell"}`}
                      >
                        <time dateTime={message.observed_at}>{time(message.observed_at)}</time>
                      </TableCell>
                      <TableCell className="pe-4">
                        <Button
                          size="icon-sm"
                          variant="ghost"
                          aria-label={`Read message from ${message.sender.value}`}
                          onClick={() => setSelectedId(message.id)}
                        >
                          <ChevronRightIcon />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
            {!preview && inbox.data && (
              <Pagination offset={offset} count={inbox.data.length} change={setOffset} />
            )}
          </>
        )}
      </Card>
      <Dialog
        open={!!selected}
        onOpenChange={(open) => {
          if (!open) setSelectedId(undefined);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{selected?.sender.value}</DialogTitle>
            <DialogDescription>Received {time(selected?.observed_at)}</DialogDescription>
          </DialogHeader>
          <p className="whitespace-pre-wrap wrap-anywhere text-sm leading-relaxed">
            {selected?.body}
          </p>
          <Badge tone={selected?.replyable ? "success" : "neutral"}>
            {selected?.replyable ? "Eligible for reply" : "Stored message"}
          </Badge>
        </DialogContent>
      </Dialog>
    </>
  );
}
