import { Cog, Copy, Image, LayoutDashboard, Route, type LucideIcon, Settings } from "lucide-react";
import { useLocation } from "react-router-dom";

import { NavLink } from "@/components/NavLink";
import {
  Sidebar as ShadcnSidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";
import { cn } from "@/lib/utils";

const mainNav = [
  { title: "Dashboard", url: "/", icon: LayoutDashboard },
  { title: "Library Actions", url: "/operations", icon: Cog },
  { title: "Organize Media", url: "/pipeline-wizard", icon: Route },
];

const mediaNav = [
  { title: "Gallery", url: "/gallery", icon: Image },
  { title: "Duplicates", url: "/duplicates", icon: Copy },
];

const systemNav = [
  { title: "Admin", url: "/admin", icon: Settings },
];

export function Sidebar() {
  const { state } = useSidebar();
  const collapsed = state === "collapsed";
  const location = useLocation();
  const currentPath = location.pathname;

  const renderGroup = (
    label: string,
    items: ReadonlyArray<{ title: string; url: string; icon: LucideIcon }>,
  ) => (
    <SidebarGroup>
      <SidebarGroupLabel className="text-sidebar-muted text-[10px] uppercase tracking-widest">
        {label}
      </SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {items.map((item) => {
            const isCurrent = item.url === "/" ? currentPath === "/" : currentPath.startsWith(item.url);

            return (
              <SidebarMenuItem key={item.title}>
                <SidebarMenuButton asChild isActive={isCurrent}>
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
            );
          })}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  );

  return (
    <ShadcnSidebar collapsible="icon" className="border-r border-sidebar-border">
      <SidebarHeader className="border-b border-sidebar-border px-4 py-4">
        {!collapsed ? (
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-sidebar-primary">
              <span className="text-xs font-bold text-sidebar-primary-foreground">MM</span>
            </div>
            <div>
              <p className="text-xs font-semibold text-sidebar-accent-foreground">Media Manager</p>
              <p className="text-[10px] text-sidebar-muted">Operator Console</p>
            </div>
          </div>
        ) : (
          <div className="mx-auto flex h-7 w-7 items-center justify-center rounded-md bg-sidebar-primary">
            <span className="text-xs font-bold text-sidebar-primary-foreground">M</span>
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
