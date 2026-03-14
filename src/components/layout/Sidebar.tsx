import {
  LayoutDashboard, Cog, PlayCircle, BookOpen, Copy, Shield, Settings, Image
} from "lucide-react";
import { NavLink } from "@/components/NavLink";
import { useLocation } from "react-router-dom";
import {
  Sidebar as ShadcnSidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarHeader,
  useSidebar,
} from "@/components/ui/sidebar";
import { cn } from "@/lib/utils";

const mainNav = [
  { title: "Dashboard", url: "/", icon: LayoutDashboard },
  { title: "Operations", url: "/operations", icon: Cog },
  { title: "Runs", url: "/runs", icon: PlayCircle },
  { title: "Ledger", url: "/ledger", icon: BookOpen },
];

const mediaNav = [
  { title: "Gallery", url: "/gallery", icon: Image },
  { title: "Duplicates", url: "/duplicates", icon: Copy },
];

const systemNav = [
  { title: "Policy", url: "/policy", icon: Shield },
  { title: "Admin", url: "/admin", icon: Settings },
];

export function Sidebar() {
  const { state } = useSidebar();
  const collapsed = state === "collapsed";
  const location = useLocation();
  const isActive = (path: string) => path === "/" ? location.pathname === "/" : location.pathname.startsWith(path);

  const renderGroup = (label: string, items: typeof mainNav) => (
    <SidebarGroup>
      <SidebarGroupLabel className="text-sidebar-muted text-[10px] uppercase tracking-widest">{label}</SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {items.map((item) => (
            <SidebarMenuItem key={item.title}>
              <SidebarMenuButton asChild>
                <NavLink
                  to={item.url}
                  end={item.url === "/"}
                  className={cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                    "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                  )}
                  activeClassName="bg-sidebar-accent text-sidebar-primary font-medium"
                >
                  <item.icon className="h-4 w-4 shrink-0" />
                  {!collapsed && <span>{item.title}</span>}
                </NavLink>
              </SidebarMenuButton>
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  );

  return (
    <ShadcnSidebar collapsible="icon" className="border-r border-sidebar-border">
      <SidebarHeader className="px-4 py-4 border-b border-sidebar-border">
        {!collapsed && (
          <div className="flex items-center gap-2">
            <div className="h-7 w-7 rounded-md bg-sidebar-primary flex items-center justify-center">
              <span className="text-sidebar-primary-foreground font-bold text-xs">MM</span>
            </div>
            <div>
              <p className="text-xs font-semibold text-sidebar-accent-foreground">Media Manager</p>
              <p className="text-[10px] text-sidebar-muted">Operator Console</p>
            </div>
          </div>
        )}
        {collapsed && (
          <div className="h-7 w-7 rounded-md bg-sidebar-primary flex items-center justify-center mx-auto">
            <span className="text-sidebar-primary-foreground font-bold text-xs">M</span>
          </div>
        )}
      </SidebarHeader>
      <SidebarContent className="py-2">
        {renderGroup("Operations", mainNav)}
        {renderGroup("Media", mediaNav)}
        {renderGroup("System", systemNav)}
      </SidebarContent>
    </ShadcnSidebar>
  );
}
