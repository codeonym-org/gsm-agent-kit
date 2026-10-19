import {
  BotIcon,
  CpuIcon,
  InboxIcon,
  LayoutDashboardIcon,
  MonitorIcon,
  MoonIcon,
  RadioIcon,
  Settings2Icon,
  SunIcon,
} from "lucide-react";
import { useTheme } from "next-themes";
import { Link, useLocation } from "react-router-dom";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar";

const navigation = [
  { to: "/overview", label: "Overview", icon: LayoutDashboardIcon },
  { to: "/inbox", label: "Inbox", icon: InboxIcon },
  { to: "/jobs", label: "Reply jobs", icon: BotIcon },
  { to: "/device", label: "Device & capabilities", icon: CpuIcon },
];
export function AppSidebar({ onConnection }: { onConnection: () => void }) {
  const { pathname } = useLocation();
  const { setOpenMobile } = useSidebar();
  const { setTheme, theme } = useTheme();
  return (
    <Sidebar variant="inset" collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild size="lg">
              <Link to="/overview">
                <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                  <RadioIcon className="size-4" />
                </span>
                <span className="grid text-start text-sm leading-tight">
                  <span className="font-semibold">GSM Agent Kit</span>
                  <span className="text-xs text-muted-foreground">Operator console</span>
                </span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Workspace</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {navigation.map(({ to, label, icon: Icon }) => (
                <SidebarMenuItem key={to}>
                  <SidebarMenuButton asChild isActive={pathname === to} tooltip={label}>
                    <Link to={to} onClick={() => setOpenMobile(false)}>
                      <Icon />
                      <span>{label}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <SidebarMenuButton tooltip="Appearance">
                  <SunIcon className="dark:hidden" />
                  <MoonIcon className="hidden dark:block" />
                  <span>Appearance</span>
                  <span className="ms-auto text-xs capitalize text-muted-foreground">{theme}</span>
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent side="top" align="start">
                <DropdownMenuItem onClick={() => setTheme("light")}>
                  <SunIcon />
                  Light
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => setTheme("dark")}>
                  <MoonIcon />
                  Dark
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => setTheme("system")}>
                  <MonitorIcon />
                  System
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton
              onClick={() => {
                onConnection();
                setOpenMobile(false);
              }}
              tooltip="API connection"
            >
              <Settings2Icon />
              <span>API connection</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
